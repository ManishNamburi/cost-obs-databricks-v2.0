"""
AI Gateway Cost Intelligence Router

system.ai_gateway.usage is account-admin only — the app SP cannot query it directly.
An account admin must create and refresh a derived table:

    CREATE OR REPLACE TABLE <catalog>.<schema>.ai_gateway_usage_shared
    CLUSTER BY (CAST(timestamp AS DATE))
    AS SELECT * FROM system.ai_gateway.usage
    WHERE workspace_id IN (...);   -- optional workspace filter

Then grant the app SP SELECT on it:
    GRANT SELECT ON TABLE <catalog>.<schema>.ai_gateway_usage_shared TO `<sp_client_id>`;

Set the env var:
    AI_GATEWAY_USAGE_TABLE=<catalog>.<schema>.ai_gateway_usage_shared

Cost model:
- 1P models (Databricks-hosted): correlated with system.billing.usage via workspace_id + date
  at aggregate level (no 1:1 join — billing aggregates usage from all consumers).
- External models (OpenAI, Anthropic, Mistral, etc.): token-based estimation using
  per-model price constants below.  No DBU cost in ai_gateway.usage — this is an estimate.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query

from backend.db import (
    execute_query,
    execute_queries_parallel,
    bundle_cache_key,
    delta_cache_get,
    delta_cache_put,
    get_catalog_schema,
)
from backend import cache_ttls

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# External model pricing constants (USD per 1 000 tokens, input / output)
# These are estimates — update as model pricing changes.
# ---------------------------------------------------------------------------
_EXTERNAL_MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o":                  {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":             {"input": 0.00015,  "output": 0.0006},
    "gpt-4-turbo":             {"input": 0.01,    "output": 0.03},
    "gpt-3.5-turbo":           {"input": 0.0005,  "output": 0.0015},
    # Anthropic
    "claude-3-5-sonnet":       {"input": 0.003,   "output": 0.015},
    "claude-3-5-haiku":        {"input": 0.0008,  "output": 0.004},
    "claude-3-opus":           {"input": 0.015,   "output": 0.075},
    # Mistral
    "mistral-large":           {"input": 0.003,   "output": 0.009},
    "mistral-small":           {"input": 0.001,   "output": 0.003},
    # Gemini (Google)
    "gemini-1.5-pro":          {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":        {"input": 0.000075,"output": 0.0003},
    # Meta Llama (Databricks-hosted — 0 cost, DBU cost attributed via billing.usage)
    "databricks-meta-llama":   {"input": 0.0,     "output": 0.0},
    "meta-llama":              {"input": 0.0,     "output": 0.0},
}

_BUNDLE_TTL = cache_ttls.AIML_BUNDLE


def _get_usage_table() -> str:
    """Return the fully-qualified AI Gateway derived table path from env."""
    tbl = os.environ.get("AI_GATEWAY_USAGE_TABLE", "").strip()
    return tbl


def _defaults(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    if not end_date:
        end_date = date.today().isoformat()
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    return start_date, end_date


def _model_price(model_name: str) -> dict[str, float]:
    """Look up per-1K-token pricing for a model. Best-effort prefix match."""
    if not model_name:
        return {"input": 0.0, "output": 0.0}
    lower = model_name.lower()
    for key, prices in _EXTERNAL_MODEL_PRICING.items():
        if key in lower:
            return prices
    return {"input": 0.0, "output": 0.0}


# ---------------------------------------------------------------------------
# SQL Templates
# ---------------------------------------------------------------------------

_AI_GW_STATUS_SQL = """
SELECT
    MIN(CAST(timestamp AS DATE)) AS earliest_date,
    MAX(CAST(timestamp AS DATE)) AS latest_date,
    COUNT(*)                      AS total_rows,
    COUNT(DISTINCT workspace_id)  AS workspace_count
FROM {table}
"""

_AI_GW_SUMMARY_SQL = """
SELECT
    COUNT(*)                                         AS total_requests,
    COUNT(DISTINCT route_name)                       AS route_count,
    COUNT(DISTINCT model_name)                       AS model_count,
    COUNT(DISTINCT client_user)                      AS user_count,
    SUM(input_token_count)                           AS total_input_tokens,
    SUM(output_token_count)                          AS total_output_tokens,
    SUM(total_token_count)                           AS total_tokens,
    AVG(request_duration_ms)                         AS avg_latency_ms,
    SUM(CASE WHEN http_status_code >= 400 THEN 1 ELSE 0 END)  AS error_count,
    SUM(CASE WHEN http_status_code < 400 THEN 1 ELSE 0 END)   AS success_count
FROM {table}
WHERE CAST(timestamp AS DATE) BETWEEN :start_date AND :end_date
  {workspace_filter}
"""

_AI_GW_BY_MODEL_SQL = """
SELECT
    model_name,
    COUNT(*)                 AS request_count,
    SUM(input_token_count)   AS input_tokens,
    SUM(output_token_count)  AS output_tokens,
    SUM(total_token_count)   AS total_tokens,
    AVG(request_duration_ms) AS avg_latency_ms,
    SUM(CASE WHEN http_status_code >= 400 THEN 1 ELSE 0 END) AS error_count
FROM {table}
WHERE CAST(timestamp AS DATE) BETWEEN :start_date AND :end_date
  {workspace_filter}
GROUP BY model_name
ORDER BY request_count DESC
LIMIT 50
"""

_AI_GW_BY_ROUTE_SQL = """
SELECT
    route_name,
    model_name,
    COUNT(*)                 AS request_count,
    SUM(input_token_count)   AS input_tokens,
    SUM(output_token_count)  AS output_tokens,
    SUM(total_token_count)   AS total_tokens,
    AVG(request_duration_ms) AS avg_latency_ms,
    SUM(CASE WHEN http_status_code >= 400 THEN 1 ELSE 0 END) AS error_count
FROM {table}
WHERE CAST(timestamp AS DATE) BETWEEN :start_date AND :end_date
  {workspace_filter}
GROUP BY route_name, model_name
ORDER BY request_count DESC
LIMIT 100
"""

_AI_GW_BY_USER_SQL = """
SELECT
    COALESCE(client_user, '(unknown)')  AS client_user,
    COUNT(*)                            AS request_count,
    COUNT(DISTINCT route_name)          AS routes_used,
    SUM(input_token_count)              AS input_tokens,
    SUM(output_token_count)             AS output_tokens,
    SUM(total_token_count)              AS total_tokens,
    AVG(request_duration_ms)            AS avg_latency_ms
FROM {table}
WHERE CAST(timestamp AS DATE) BETWEEN :start_date AND :end_date
  {workspace_filter}
GROUP BY client_user
ORDER BY request_count DESC
LIMIT 100
"""

_AI_GW_TIMESERIES_SQL = """
SELECT
    CAST(timestamp AS DATE)  AS usage_date,
    model_name,
    COUNT(*)                 AS request_count,
    SUM(input_token_count)   AS input_tokens,
    SUM(output_token_count)  AS output_tokens,
    SUM(total_token_count)   AS total_tokens,
    AVG(request_duration_ms) AS avg_latency_ms
FROM {table}
WHERE CAST(timestamp AS DATE) BETWEEN :start_date AND :end_date
  {workspace_filter}
GROUP BY CAST(timestamp AS DATE), model_name
ORDER BY usage_date, model_name
"""

_AI_GW_BILLING_CORRELATE_SQL = """
SELECT
    u.usage_date,
    u.workspace_id,
    SUM(COALESCE(p.pricing.default, 0) * u.usage_quantity) AS estimated_cost_usd,
    SUM(u.usage_quantity)                                   AS dbu_quantity
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
    AND u.cloud = p.cloud
    AND p.price_end_time IS NULL
WHERE u.usage_date BETWEEN :start_date AND :end_date
  AND (
    u.sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%'
    OR u.billing_origin_product = 'MODEL_SERVING'
    OR u.sku_name LIKE '%ANTHROPIC%'
    OR u.sku_name LIKE '%OPENAI%'
    OR u.sku_name LIKE '%GEMINI%'
    OR u.sku_name LIKE '%LLAMA%'
    OR u.sku_name LIKE '%FOUNDATION_MODEL%'
  )
  {workspace_filter}
GROUP BY u.usage_date, u.workspace_id
ORDER BY u.usage_date
"""


def _apply_workspace_filter(sql: str, workspace_ids: list[str] | None, table_alias: str = "") -> tuple[str, dict]:
    """Inject workspace filter and return (sql, extra_params)."""
    prefix = f"{table_alias}." if table_alias else ""
    if workspace_ids:
        placeholders = ", ".join(f":ws_{i}" for i in range(len(workspace_ids)))
        clause = f"AND {prefix}workspace_id IN ({placeholders})"
        params = {f"ws_{i}": int(wid) for i, wid in enumerate(workspace_ids)}
        return sql.replace("{workspace_filter}", clause), params
    return sql.replace("{workspace_filter}", ""), {}


def _annotate_costs(rows: list[dict], billing_by_date: dict) -> list[dict]:
    """Attach estimated_cost_usd to timeseries rows from billing correlation + token pricing."""
    for row in rows:
        date_str = str(row.get("usage_date", ""))
        model = str(row.get("model_name", "")).lower()
        billing_cost = billing_by_date.get(date_str, 0.0)
        prices = _model_price(model)
        input_k = (row.get("input_tokens") or 0) / 1000.0
        output_k = (row.get("output_tokens") or 0) / 1000.0
        token_est = input_k * prices["input"] + output_k * prices["output"]
        # If billing data is available use it; if token pricing is > 0 add it for external models
        if billing_cost > 0:
            row["estimated_cost_usd"] = round(billing_cost, 4)
            row["cost_source"] = "billing"
        elif token_est > 0:
            row["estimated_cost_usd"] = round(token_est, 4)
            row["cost_source"] = "token_estimate"
        else:
            row["estimated_cost_usd"] = 0.0
            row["cost_source"] = "unavailable"
    return rows


def _enrich_model_costs(rows: list[dict]) -> list[dict]:
    """Add estimated cost to per-model rows using token pricing."""
    for row in rows:
        model = str(row.get("model_name", "")).lower()
        prices = _model_price(model)
        input_k = (row.get("input_tokens") or 0) / 1000.0
        output_k = (row.get("output_tokens") or 0) / 1000.0
        token_est = input_k * prices["input"] + output_k * prices["output"]
        row["estimated_cost_usd"] = round(token_est, 4)
        row["cost_source"] = "token_estimate" if token_est > 0 else "unavailable"
    return rows


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_ai_gateway_status() -> dict[str, Any]:
    """Check whether the AI Gateway usage table is configured and accessible."""
    tbl = _get_usage_table()
    if not tbl:
        return {
            "configured": False,
            "table": None,
            "message": (
                "AI_GATEWAY_USAGE_TABLE env var not set. "
                "An account admin must create and share a derived table from system.ai_gateway.usage."
            ),
        }
    import asyncio
    loop = asyncio.get_running_loop()

    def _probe():
        try:
            rows = execute_query(
                _AI_GW_STATUS_SQL.format(table=tbl),
                no_cache=True,
            )
            if rows:
                r = rows[0]
                return {
                    "configured": True,
                    "accessible": True,
                    "table": tbl,
                    "earliest_date": str(r.get("earliest_date") or ""),
                    "latest_date": str(r.get("latest_date") or ""),
                    "total_rows": r.get("total_rows") or 0,
                    "workspace_count": r.get("workspace_count") or 0,
                }
            return {"configured": True, "accessible": True, "table": tbl, "total_rows": 0}
        except Exception as e:
            return {
                "configured": True,
                "accessible": False,
                "table": tbl,
                "error": str(e),
                "message": (
                    "Table configured but not accessible. Check that the app SP has SELECT grant on the table, "
                    "and that the table has been populated by the admin refresh job."
                ),
            }

    return await loop.run_in_executor(None, _probe)


@router.get("/summary")
async def get_ai_gateway_summary(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> dict[str, Any]:
    """Overall request counts, token consumption, and latency for the period."""
    tbl = _get_usage_table()
    if not tbl:
        return {"error": "AI_GATEWAY_USAGE_TABLE not configured"}

    start_date, end_date = _defaults(start_date, end_date)
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}

    sql, ws_params = _apply_workspace_filter(_AI_GW_SUMMARY_SQL.format(table=tbl), workspace_ids)
    params.update(ws_params)

    import asyncio
    loop = asyncio.get_running_loop()

    def _run():
        rows = execute_query(sql, params)
        if not rows:
            return {}
        r = rows[0]
        total = r.get("total_tokens") or 0
        errors = r.get("error_count") or 0
        successes = r.get("success_count") or 0
        total_req = r.get("total_requests") or 0
        return {
            "total_requests": total_req,
            "success_count": successes,
            "error_count": errors,
            "error_rate_pct": round(errors / total_req * 100, 1) if total_req else 0.0,
            "route_count": r.get("route_count") or 0,
            "model_count": r.get("model_count") or 0,
            "user_count": r.get("user_count") or 0,
            "total_input_tokens": r.get("total_input_tokens") or 0,
            "total_output_tokens": r.get("total_output_tokens") or 0,
            "total_tokens": total,
            "avg_latency_ms": round(float(r.get("avg_latency_ms") or 0), 1),
            "start_date": start_date,
            "end_date": end_date,
        }

    return await loop.run_in_executor(None, _run)


@router.get("/by-model")
async def get_ai_gateway_by_model(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> list[dict[str, Any]]:
    """Token consumption and request counts broken down by model."""
    tbl = _get_usage_table()
    if not tbl:
        return []

    start_date, end_date = _defaults(start_date, end_date)
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    sql, ws_params = _apply_workspace_filter(_AI_GW_BY_MODEL_SQL.format(table=tbl), workspace_ids)
    params.update(ws_params)

    import asyncio
    loop = asyncio.get_running_loop()

    def _run():
        rows = execute_query(sql, params)
        return _enrich_model_costs(rows)

    return await loop.run_in_executor(None, _run)


@router.get("/by-route")
async def get_ai_gateway_by_route(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> list[dict[str, Any]]:
    """Token consumption and request counts broken down by AI Gateway route."""
    tbl = _get_usage_table()
    if not tbl:
        return []

    start_date, end_date = _defaults(start_date, end_date)
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    sql, ws_params = _apply_workspace_filter(_AI_GW_BY_ROUTE_SQL.format(table=tbl), workspace_ids)
    params.update(ws_params)

    import asyncio
    loop = asyncio.get_running_loop()

    def _run():
        rows = execute_query(sql, params)
        return _enrich_model_costs(rows)

    return await loop.run_in_executor(None, _run)


@router.get("/by-user")
async def get_ai_gateway_by_user(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> list[dict[str, Any]]:
    """Token consumption and request counts broken down by calling user/service principal."""
    tbl = _get_usage_table()
    if not tbl:
        return []

    start_date, end_date = _defaults(start_date, end_date)
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    sql, ws_params = _apply_workspace_filter(_AI_GW_BY_USER_SQL.format(table=tbl), workspace_ids)
    params.update(ws_params)

    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: execute_query(sql, params))


@router.get("/timeseries")
async def get_ai_gateway_timeseries(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> list[dict[str, Any]]:
    """Daily token usage and request counts by model for the time series chart."""
    tbl = _get_usage_table()
    if not tbl:
        return []

    start_date, end_date = _defaults(start_date, end_date)
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    sql, ws_params = _apply_workspace_filter(_AI_GW_TIMESERIES_SQL.format(table=tbl), workspace_ids)
    params.update(ws_params)

    billing_sql, billing_ws = _apply_workspace_filter(
        _AI_GW_BILLING_CORRELATE_SQL, workspace_ids, table_alias="u"
    )
    billing_params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    billing_params.update(billing_ws)

    import asyncio
    loop = asyncio.get_running_loop()

    def _run():
        results = execute_queries_parallel([
            ("usage", lambda: execute_query(sql, params)),
            ("billing", lambda: execute_query(billing_sql, billing_params)),
        ], timeout=60)
        usage_rows = results.get("usage") or []
        billing_rows = results.get("billing") or []
        billing_by_date = {
            str(r["usage_date"]): float(r.get("estimated_cost_usd") or 0)
            for r in billing_rows
        }
        return _annotate_costs(usage_rows, billing_by_date)

    return await loop.run_in_executor(None, _run)


@router.get("/dashboard-bundle")
async def get_ai_gateway_dashboard_bundle(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    workspace_ids: list[str] | None = Query(None, alias="workspace_id"),
) -> dict[str, Any]:
    """All AI Gateway data in one call for the dashboard tab.

    Returns: status, summary, by_model, by_route, top_users, timeseries.
    """
    tbl = _get_usage_table()
    if not tbl:
        return {
            "configured": False,
            "message": (
                "AI_GATEWAY_USAGE_TABLE not configured. "
                "Set this env var in your Databricks App to the admin-managed derived table."
            ),
        }

    start_date, end_date = _defaults(start_date, end_date)

    # Delta cache check
    ws_list = sorted(workspace_ids) if workspace_ids else []
    cache_key = bundle_cache_key("ai-gateway-bundle", start_date, end_date, ws_list or None)
    cached = delta_cache_get(cache_key)
    if cached is not None:
        logger.info("ai-gateway-bundle: Delta cache hit")
        return cached

    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}

    def _make_sql(template: str) -> tuple[str, dict]:
        sql, ws_p = _apply_workspace_filter(template.format(table=tbl), workspace_ids)
        p = {**params, **ws_p}
        return sql, p

    summary_sql, summary_p = _make_sql(_AI_GW_SUMMARY_SQL)
    model_sql, model_p = _make_sql(_AI_GW_BY_MODEL_SQL)
    route_sql, route_p = _make_sql(_AI_GW_BY_ROUTE_SQL)
    user_sql, user_p = _make_sql(_AI_GW_BY_USER_SQL)
    ts_sql, ts_p = _make_sql(_AI_GW_TIMESERIES_SQL)

    billing_sql, billing_ws = _apply_workspace_filter(
        _AI_GW_BILLING_CORRELATE_SQL, workspace_ids, table_alias="u"
    )
    billing_p: dict[str, Any] = {"start_date": start_date, "end_date": end_date, **billing_ws}

    import asyncio
    loop = asyncio.get_running_loop()

    def _run():
        results = execute_queries_parallel([
            ("summary",  lambda: execute_query(summary_sql, summary_p)),
            ("by_model", lambda: execute_query(model_sql, model_p)),
            ("by_route", lambda: execute_query(route_sql, route_p)),
            ("by_user",  lambda: execute_query(user_sql, user_p)),
            ("timeseries", lambda: execute_query(ts_sql, ts_p)),
            ("billing",  lambda: execute_query(billing_sql, billing_p)),
        ], timeout=90)

        summary_rows = results.get("summary") or []
        model_rows = _enrich_model_costs(results.get("by_model") or [])
        route_rows = _enrich_model_costs(results.get("by_route") or [])
        user_rows = results.get("by_user") or []
        billing_rows = results.get("billing") or []
        billing_by_date = {
            str(r["usage_date"]): float(r.get("estimated_cost_usd") or 0)
            for r in billing_rows
        }
        ts_rows = _annotate_costs(results.get("timeseries") or [], billing_by_date)

        # Build summary dict
        s = summary_rows[0] if summary_rows else {}
        total_req = s.get("total_requests") or 0
        errors = s.get("error_count") or 0
        summary = {
            "total_requests": total_req,
            "success_count": s.get("success_count") or 0,
            "error_count": errors,
            "error_rate_pct": round(errors / total_req * 100, 1) if total_req else 0.0,
            "route_count": s.get("route_count") or 0,
            "model_count": s.get("model_count") or 0,
            "user_count": s.get("user_count") or 0,
            "total_input_tokens": s.get("total_input_tokens") or 0,
            "total_output_tokens": s.get("total_output_tokens") or 0,
            "total_tokens": s.get("total_tokens") or 0,
            "avg_latency_ms": round(float(s.get("avg_latency_ms") or 0), 1),
            "total_estimated_cost_usd": round(sum(r.get("estimated_cost_usd", 0) for r in model_rows), 2),
        }

        bundle = {
            "configured": True,
            "table": tbl,
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
            "by_model": model_rows,
            "by_route": route_rows,
            "top_users": user_rows[:25],
            "timeseries": ts_rows,
        }
        delta_cache_put(cache_key, "ai-gateway-bundle", bundle, ttl_seconds=_BUNDLE_TTL)
        return bundle

    return await loop.run_in_executor(None, _run)
