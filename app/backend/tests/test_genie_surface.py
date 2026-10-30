"""Genie surfaces come from usage_metadata.genie.surface, and the gold table rebuilds once."""

from backend import lakebase_sync, materialized_views
from backend.materialized_views_extra import (
    CREATE_DAILY_SKU_BREAKDOWN,
    EXTRA_TABLE_REFRESH,
    MERGE_DAILY_SKU_BREAKDOWN,
)
from backend.routers import genie_cost

SURFACE = "get_json_object(to_json(u.usage_metadata), '$.genie.surface')"


def test_live_queries_classify_by_usage_metadata_surface():
    for sql in (genie_cost._GENIE_BY_WORKSPACE_SQL, genie_cost._GENIE_TIMESERIES_SQL):
        assert f"{SURFACE} AS genie_surface_raw" in sql
        for raw, bucket in (("GENIE_CODE", "genie_code"), ("GENIE_ONE", "genie_one"), ("GENIE_AGENTS", "genie_agents")):
            assert f"genie_surface_raw = '{raw}'" in sql
            assert f"THEN '{bucket}'" in sql
    assert f"{SURFACE} AS genie_surface" in genie_cost._GENIE_DIAGNOSTICS_SQL


def test_gold_table_uses_the_same_signal_for_build_and_merge():
    for sql in (CREATE_DAILY_SKU_BREAKDOWN, MERGE_DAILY_SKU_BREAKDOWN):
        assert f"{SURFACE} = 'GENIE_CODE'" in sql
        assert f"{SURFACE} = 'GENIE_ONE'" in sql
        assert f"{SURFACE} = 'GENIE_AGENTS'" in sql
    assert EXTRA_TABLE_REFRESH["daily_sku_breakdown"]["definition_version"] == 2


def _props(monkeypatch, value):
    calls = []

    def _query(sql, *args, **kwargs):
        calls.append(sql)
        if isinstance(value, Exception):
            raise value
        return [{"key": materialized_views._DEFINITION_VERSION_PROP, "value": value}]
    monkeypatch.setattr(materialized_views, "execute_query", _query)
    return calls


def test_table_without_the_version_property_is_outdated(monkeypatch):
    _props(monkeypatch, "Table c.s.t does not have property: cost_obs.definition_version")
    assert materialized_views._definition_outdated("c", "s", "t", {"definition_version": 2})


def test_table_at_the_current_version_is_not_outdated(monkeypatch):
    _props(monkeypatch, "2")
    assert not materialized_views._definition_outdated("c", "s", "t", {"definition_version": 2})


def test_unversioned_tables_never_query_properties(monkeypatch):
    calls = _props(monkeypatch, "1")
    assert not materialized_views._definition_outdated("c", "s", "t", {})
    assert calls == []


def test_unreadable_properties_leave_the_normal_path_alone(monkeypatch):
    _props(monkeypatch, RuntimeError("TABLE_OR_VIEW_NOT_FOUND"))
    assert not materialized_views._definition_outdated("c", "s", "t", {"definition_version": 2})


def test_stamp_records_the_version(monkeypatch):
    calls = _props(monkeypatch, "")
    materialized_views._stamp_definition_version("c", "s", "t", {"definition_version": 2})
    assert calls == ["ALTER TABLE `c`.`s`.`t` SET TBLPROPERTIES ('cost_obs.definition_version' = '2')"]


def test_rebuilt_tables_get_a_full_lakebase_copy(monkeypatch):
    seen = {}
    monkeypatch.setattr("backend.db.lakebase_available", lambda: True)
    monkeypatch.setattr("backend.db.get_pg_conn", lambda: (_ for _ in ()).throw(RuntimeError("no pg")))
    monkeypatch.setattr(
        lakebase_sync, "sync_one_aggregate",
        lambda catalog, schema, table, cfg, *, full=False: seen.setdefault(table, full),
    )
    lakebase_sync.sync_all_aggregates("c", "s", full_tables={"daily_sku_breakdown"})
    assert seen["daily_sku_breakdown"] is True
    assert seen["daily_usage_summary"] is False
