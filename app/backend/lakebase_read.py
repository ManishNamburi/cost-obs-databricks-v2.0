"""Phase B — dual-read cutover for dashboard aggregate reads (serve Delta, shadow Lakebase).

This is the reader half of Phase B (docs/LAKEBASE_MIGRATION_DESIGN.md §13/§14). The
headline dashboard reads the `daily_*` aggregates through billing._exec_mv; this module
lets that choke point ALSO run the Postgres-dialect equivalent against Lakebase and log a
parity verdict — WITHOUT changing what the app serves — so the §13 burn-in accumulates
during real usage before any cutover.

Modes (env `COST_OBS_LAKEBASE_READ`):
  - off    (default) — serve Delta only. Zero behavior change, zero extra load.
  - shadow           — serve Delta; fire-and-forget the Lakebase read + parity log.
  - on               — serve Lakebase (post-cutover), falling back to Delta on any error.

Dialect notes (Databricks SQL → Postgres) for these specific aggregate queries:
  - backtick `{catalog}`.`{schema}`.`t` → unqualified `t` (the pool sets search_path).
  - `:named` params → psycopg `%(named)s`.
  - `CAST(workspace_id AS STRING)` (Delta) → `workspace_id` (already text in Lakebase).
  - workspace_id NULL (account-level) was stored as the '__account__' sentinel by the
    sync, so reads map it back with NULLIF to match Delta's NULL semantics (COUNT DISTINCT
    and the workspace grain).
The templates are hand-written (not auto-translated) so parity can't be faked by a lossy
translator — §14.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

_WS_SENTINEL = "__account__"

# Small pool for fire-and-forget shadow reads so they never block the served Delta path.
_shadow_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lb-shadow")


def lakebase_read_mode() -> str:
    """'off' | 'shadow' | 'on' — default 'off'."""
    m = os.getenv("COST_OBS_LAKEBASE_READ", "off").strip().lower()
    return m if m in ("off", "shadow", "on") else "off"


def pg_ws_filter(delta_ws_filter: str) -> str:
    """Translate the Delta workspace-filter clause to Postgres.

    The Delta clause is `AND CAST(workspace_id AS STRING) IN ('a','b')`; workspace_id is
    already text in Lakebase, so drop the CAST. Values are pre-validated + quoted upstream.
    """
    if not delta_ws_filter:
        return ""
    return re.sub(r"CAST\(\s*(?:\w+\.)?workspace_id\s+AS\s+STRING\s*\)", "workspace_id",
                  delta_ws_filter, flags=re.IGNORECASE)


# ── Postgres-dialect templates for the dashboard-bundle headline reads ────────────
# `{ws_filter}` is the pg_ws_filter() output. Params: %(start_date)s / %(end_date)s.

PG_BILLING_SUMMARY = """
SELECT
  SUM(total_dbus) AS total_dbus,
  SUM(total_spend) AS total_spend,
  COUNT(DISTINCT NULLIF(workspace_id, '__account__')) AS workspace_count,
  COUNT(DISTINCT usage_date) AS days_in_range,
  MIN(usage_date) AS first_date,
  MAX(usage_date) AS last_date
FROM daily_usage_summary
WHERE usage_date BETWEEN %(start_date)s AND %(end_date)s
  {ws_filter}
"""

PG_BILLING_BY_PRODUCT = """
SELECT
  product_category,
  SUM(total_dbus) AS total_dbus,
  SUM(total_spend) AS total_spend,
  COUNT(DISTINCT NULLIF(workspace_id, '__account__')) AS workspace_count
FROM daily_product_breakdown
WHERE usage_date BETWEEN %(start_date)s AND %(end_date)s
  {ws_filter}
GROUP BY product_category
ORDER BY total_spend DESC
"""

PG_BILLING_TIMESERIES = """
SELECT
  usage_date,
  product_category,
  SUM(total_dbus) AS total_dbus,
  SUM(total_spend) AS total_spend
FROM daily_product_breakdown
WHERE usage_date BETWEEN %(start_date)s AND %(end_date)s
  {ws_filter}
GROUP BY usage_date, product_category
ORDER BY usage_date, product_category
"""

PG_BILLING_BY_WORKSPACE = """
SELECT
  NULLIF(workspace_id, '__account__') AS workspace_id,
  MAX(workspace_name) AS workspace_name,
  SUM(total_dbus) AS total_dbus,
  SUM(total_spend) AS total_spend
FROM daily_workspace_breakdown
WHERE usage_date BETWEEN %(start_date)s AND %(end_date)s
  {ws_filter}
GROUP BY NULLIF(workspace_id, '__account__')
ORDER BY total_spend DESC
"""

PG_ETL_BREAKDOWN = """
SELECT
  CASE
    WHEN product_category = 'ETL - Streaming' THEN 'Streaming (SDP)'
    WHEN product_category = 'ETL - Batch' THEN 'Batch Jobs'
  END AS etl_type,
  SUM(total_dbus) AS total_dbus,
  SUM(total_spend) AS total_spend
FROM daily_product_breakdown
WHERE usage_date BETWEEN %(start_date)s AND %(end_date)s
  {ws_filter}
  AND product_category IN ('ETL - Streaming', 'ETL - Batch')
GROUP BY product_category
ORDER BY total_spend DESC
"""

# Registry: maps a Databricks MV template (by identity) → (parity name, PG template, key cols).
# Built lazily to avoid an import cycle with materialized_views.
_REGISTRY: dict[str, tuple[str, str, list[str]]] | None = None


def _registry() -> dict[str, tuple[str, str, list[str]]]:
    global _REGISTRY
    if _REGISTRY is None:
        from backend.materialized_views import (
            MV_BILLING_BY_PRODUCT, MV_BILLING_BY_WORKSPACE, MV_BILLING_SUMMARY,
            MV_BILLING_TIMESERIES, MV_ETL_BREAKDOWN,
        )
        _REGISTRY = {
            MV_BILLING_SUMMARY:     ("billing_summary",  PG_BILLING_SUMMARY,     []),
            MV_BILLING_BY_PRODUCT:  ("billing_products", PG_BILLING_BY_PRODUCT,  ["product_category"]),
            MV_BILLING_TIMESERIES:  ("billing_timeseries", PG_BILLING_TIMESERIES, ["usage_date", "product_category"]),
            MV_BILLING_BY_WORKSPACE: ("billing_workspaces", PG_BILLING_BY_WORKSPACE, ["workspace_id"]),
            MV_ETL_BREAKDOWN:       ("billing_etl",      PG_ETL_BREAKDOWN,       ["etl_type"]),
        }
    return _REGISTRY


def dual_read_mv(
    mv_template: str, params: dict[str, Any], delta_ws_filter: str, delta_result: list[dict]
) -> list[dict]:
    """Cutover choke point. Returns the Delta result in off/shadow modes; in 'on' mode
    returns the Lakebase result (falling back to Delta on error). Never raises.

    In shadow mode a background task reads Lakebase, compares to `delta_result`, and logs a
    parity verdict — the served result is unaffected.
    """
    mode = lakebase_read_mode()
    if mode == "off":
        return delta_result
    try:
        from backend.db import lakebase_available
        if not lakebase_available():
            return delta_result
        reg = _registry().get(mv_template)
        if reg is None:  # no PG template for this query yet — serve Delta unchanged
            return delta_result
        name, pg_tmpl, key_cols = reg
        pg_sql = pg_tmpl.format(ws_filter=pg_ws_filter(delta_ws_filter))
        pg_params = {"start_date": params.get("start_date"), "end_date": params.get("end_date")}

        if mode == "on":
            from backend.db import lakebase_query
            try:
                return lakebase_query(pg_sql, pg_params)
            except Exception as e:
                logger.warning("lakebase_read[%s]: 'on' read failed, falling back to Delta: %s", name, e)
                return delta_result

        # shadow — fire-and-forget compare; serve Delta.
        _shadow_pool.submit(_run_shadow, name, pg_sql, pg_params, key_cols, delta_result)
        return delta_result
    except Exception as e:
        logger.debug("dual_read_mv error (non-fatal, serving Delta): %s", e)
        return delta_result


def _run_shadow(name: str, pg_sql: str, pg_params: dict, key_cols: list[str], delta_result: list[dict]) -> None:
    """Background: read Lakebase, compare to the served Delta rows, log the verdict."""
    try:
        from backend.db import lakebase_query
        from backend.lakebase_parity import compare_result_sets, _write_parity_log
        lb_rows = lakebase_query(pg_sql, pg_params)
        report = compare_result_sets(delta_result, lb_rows, key_cols=key_cols)
        report["name"] = name
        report["checked_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        level = logging.INFO if report["verdict"] == "PASS" else logging.WARNING
        logger.log(level, "lakebase_read shadow[%s]: %s delta=%d lakebase=%d hard=%d miss=%d extra=%d",
                   name, report["verdict"], report["delta_rows"], report["lakebase_rows"],
                   report["hard_mismatches"], report["missing_in_lakebase"], report["extra_in_lakebase"])
        _write_parity_log(f"read:{name}", report)
    except Exception as e:
        logger.debug("lakebase_read shadow[%s] failed (non-fatal): %s", name, e)
