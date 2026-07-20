"""Unit tests for the pure logic in backend.lakebase_read (Phase B reader cutover).

Covers the dialect translation (Databricks ws-filter → Postgres), the mode flag, and the
shape of the hand-written PG templates (sentinel NULLIF, psycopg params, no backticks).
The registry + I/O need the SDK/live Lakebase and are exercised in the shadow deploy.
"""
import os

from backend.lakebase_read import (
    PG_BILLING_BY_WORKSPACE,
    PG_BILLING_SUMMARY,
    lakebase_read_mode,
    pg_ws_filter,
)


def test_mode_defaults_off(monkeypatch=None):
    os.environ.pop("COST_OBS_LAKEBASE_READ", None)
    assert lakebase_read_mode() == "off"


def test_mode_reads_env():
    for val, exp in [("shadow", "shadow"), ("on", "on"), ("OFF", "off"), ("bogus", "off"), ("", "off")]:
        os.environ["COST_OBS_LAKEBASE_READ"] = val
        assert lakebase_read_mode() == exp
    os.environ.pop("COST_OBS_LAKEBASE_READ", None)


def test_pg_ws_filter_drops_cast():
    assert pg_ws_filter("AND CAST(workspace_id AS STRING) IN ('1','2')") == "AND workspace_id IN ('1','2')"


def test_pg_ws_filter_handles_alias_and_case():
    assert pg_ws_filter("AND cast(u.workspace_id as string) IN ('1')") == "AND workspace_id IN ('1')"


def test_pg_ws_filter_empty():
    assert pg_ws_filter("") == ""


def test_summary_template_is_postgres():
    sql = PG_BILLING_SUMMARY.format(ws_filter="AND workspace_id IN ('1')")
    assert "`" not in sql                                   # no Databricks backticks
    assert "%(start_date)s" in sql and "%(end_date)s" in sql  # psycopg named params
    assert "FROM daily_usage_summary" in sql                # unqualified (search_path)
    # account-level sentinel mapped back to NULL so COUNT(DISTINCT) matches Delta
    assert "COUNT(DISTINCT NULLIF(workspace_id, '__account__'))" in sql


def test_by_workspace_maps_sentinel_back_to_null():
    sql = PG_BILLING_BY_WORKSPACE.format(ws_filter="")
    # the served workspace_id must be NULL for account-level rows, not the sentinel
    assert "NULLIF(workspace_id, '__account__') AS workspace_id" in sql
    assert "GROUP BY NULLIF(workspace_id, '__account__')" in sql
