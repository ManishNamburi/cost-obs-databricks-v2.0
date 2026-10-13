import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "setup" / "python"))

from shared_setup_lib import _gold_hard_errors, _gold_lookback_days, build_gold  # noqa: E402


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
