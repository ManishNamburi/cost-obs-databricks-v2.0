import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "setup" / "python"))

from shared_setup_lib import (  # noqa: E402
    _gold_hard_errors,
    _gold_lookback_days,
    _grant_app_sp_uc_privileges,
    _require_successful_lakebase_sync,
    _verify_lakebase_has_gold,
    _verify_sp_can_read_gold,
    build_gold,
)


@pytest.fixture
def gold_env(monkeypatch):
    monkeypatch.setenv("COST_OBS_CATALOG", "acme_catalog")
    monkeypatch.setenv("COST_OBS_SCHEMA", "cost_obs")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "abc123")
    monkeypatch.setenv("ENDPOINT_NAME", "projects/cost-obs-db/branches/production/endpoints/primary")
    monkeypatch.setenv("DEPLOYMENT_MODE", "fresh")
    monkeypatch.setenv("LOOKBACK_DAYS", "180")

    conn = MagicMock()
    monkeypatch.setattr("shared_setup_lib._resolve_lakebase_env", lambda: None)
    monkeypatch.setattr("shared_setup_lib._is_step_done", lambda *_a, **_k: False)
    monkeypatch.setattr("shared_setup_lib._mark_step_done", lambda *_a, **_k: None)

    class _Ctx:
        def __enter__(self):
            return conn

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("shared_setup_lib.pg_conn", lambda: _Ctx())
    return conn


def test_lookback_clamps(monkeypatch):
    monkeypatch.setenv("LOOKBACK_DAYS", "not-a-number")
    assert _gold_lookback_days() == 180
    monkeypatch.setenv("LOOKBACK_DAYS", "9000")
    assert _gold_lookback_days() == 730
    monkeypatch.setenv("LOOKBACK_DAYS", "90")
    assert _gold_lookback_days() == 90


def test_optional_skips_are_not_hard_errors():
    assert _gold_hard_errors({
        "daily_usage_summary": "created",
        "daily_cloud_actuals": "skipped: optional source not connected",
        "__mv_timings__": {"daily_usage_summary": 1.2},
        "error": None,
    }) == []


def test_fresh_forces_full_rebuild(gold_env, monkeypatch):
    seen = {}

    def create_mvs(**kwargs):
        seen["create"] = kwargs
        return {
            "daily_usage_summary": "created",
            "lakebase_sync": {"ok": 8, "total": 8},
        }

    def sync_all(*_a, **_k):
        raise AssertionError("fresh path should not re-run a full sync when create already synced")

    monkeypatch.setenv("DEPLOYMENT_MODE", "fresh")
    build_gold(_create_mvs=create_mvs, _sync_all=sync_all)
    assert seen["create"]["force_full_rebuild"] is True
    assert seen["create"]["catalog"] == "acme_catalog"
    assert seen["create"]["lookback_days"] == 180


def test_migrate_reuses_mvs_and_full_syncs_lakebase(gold_env, monkeypatch):
    seen = {}

    def create_mvs(**kwargs):
        seen["create"] = kwargs
        return {
            "daily_usage_summary": "refreshed",
            "lakebase_sync": {"ok": 2, "total": 8},
        }

    def sync_all(catalog, schema, full=False):
        seen["sync"] = {"catalog": catalog, "schema": schema, "full": full}
        return {"ok": 8, "total": 8}

    monkeypatch.setenv("DEPLOYMENT_MODE", "migrate")
    build_gold(_create_mvs=create_mvs, _sync_all=sync_all)
    assert seen["create"]["force_full_rebuild"] is False
    assert seen["sync"] == {"catalog": "acme_catalog", "schema": "cost_obs", "full": True}


def test_required_table_error_raises(gold_env, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "fresh")
    with pytest.raises(RuntimeError, match="daily_usage_summary"):
        build_gold(
            _create_mvs=lambda **_k: {"daily_usage_summary": "error: warehouse timeout"},
            _sync_all=lambda *_a, **_k: {"skipped": True},
        )


def test_fresh_fails_when_lakebase_copy_is_empty(gold_env, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "fresh")
    with pytest.raises(RuntimeError, match="Lakebase gold copy"):
        build_gold(
            _create_mvs=lambda **_k: {
                "daily_usage_summary": "created",
                "lakebase_sync": {"ok": 0, "total": 8, "skipped": False},
            },
            _sync_all=lambda *_a, **_k: {"ok": 0, "total": 8, "skipped": False},
        )


def test_require_lakebase_sync_rejects_skipped_and_required_errors():
    with pytest.raises(RuntimeError, match="skipped"):
        _require_successful_lakebase_sync({"skipped": True, "reason": "lakebase_unavailable"})
    with pytest.raises(RuntimeError, match="daily_usage_summary"):
        _require_successful_lakebase_sync({
            "skipped": False,
            "ok": 0,
            "total": 2,
            "tables": {
                "daily_usage_summary": {"error": "no postgres API"},
                "daily_cloud_actuals": {"error": "optional"},
            },
        })
    _require_successful_lakebase_sync({
        "skipped": False,
        "ok": 1,
        "total": 2,
        "tables": {
            "daily_usage_summary": {"table": "daily_usage_summary", "rows": 10},
            "daily_cloud_actuals": {"error": "optional source missing"},
        },
    })


def test_verify_fails_when_lakebase_gold_is_empty(monkeypatch):
    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            return None

        def fetchone(self):
            return (0,)

    class _Conn:
        def cursor(self):
            return _Cur()

    class _Pg:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("shared_setup_lib.pg_conn", lambda: _Pg())
    with pytest.raises(RuntimeError, match="no rows"):
        _verify_lakebase_has_gold()


def test_verify_fails_when_sp_lacks_catalog_access(monkeypatch):
    monkeypatch.setattr("shared_setup_lib._get_app_sp_uuid", lambda: "sp-uuid")
    monkeypatch.setattr("shared_setup_lib._warehouse_query", lambda *_a, **_k: [])
    with pytest.raises(RuntimeError, match="missing"):
        _verify_sp_can_read_gold("acme_catalog", "cost_obs")


def test_verify_passes_when_sp_has_required_privileges(monkeypatch):
    monkeypatch.setattr("shared_setup_lib._get_app_sp_uuid", lambda: "sp-uuid")

    def query(sql, **_k):
        if "catalog_privileges" in sql:
            return [["USE_CATALOG"]]
        return [["USE_SCHEMA"], ["SELECT"]]

    monkeypatch.setattr("shared_setup_lib._warehouse_query", query)
    _verify_sp_can_read_gold("acme_catalog", "cost_obs")


def test_uc_grants_cover_catalog_schema_and_table_write(monkeypatch):
    monkeypatch.setenv("COST_OBS_CATALOG", "acme_catalog")
    monkeypatch.setenv("COST_OBS_SCHEMA", "cost_obs")
    monkeypatch.setattr("shared_setup_lib._get_app_sp_uuid", lambda: "sp-uuid")
    seen = []
    monkeypatch.setattr("shared_setup_lib._warehouse_query", lambda sql, **_k: seen.append(sql) or [])
    _grant_app_sp_uc_privileges()
    joined = "\n".join(seen)
    assert "GRANT USE CATALOG ON CATALOG `acme_catalog` TO `sp-uuid`" in joined
    assert "GRANT USE SCHEMA ON SCHEMA `acme_catalog`.`cost_obs` TO `sp-uuid`" in joined
    assert "GRANT SELECT, MODIFY, CREATE TABLE ON SCHEMA `acme_catalog`.`cost_obs`" in joined
