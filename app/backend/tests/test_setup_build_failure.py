"""A failed table in the setup wizard's build must end the build, not keep it spinning."""

import pytest

from backend import materialized_views as mv
from backend.routers import setup


@pytest.fixture
def task_state(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "_TASK_STATE_FILE", str(tmp_path / "build_progress.json"))
    monkeypatch.setattr(setup, "_persist_task_state", lambda: None)
    state = {
        "status": "running", "error": None, "started_at": None, "elapsed_seconds": 0,
        "table_progress": {"daily_usage_summary": "pending"}, "table_errors": {},
    }
    monkeypatch.setattr(setup, "_create_task_state", state)
    return state


def test_first_failed_table_ends_the_build_with_its_reason(monkeypatch, task_state):
    seen = {}

    def fake_build(catalog, schema, on_table_event=None, on_table_error=None, stop_on_error=False):
        seen["stop_on_error"] = stop_on_error
        on_table_event("daily_usage_summary", "running")
        on_table_error("daily_usage_summary", "[INSUFFICIENT_PERMISSIONS] User does not have SELECT on system.billing.usage")
        on_table_event("daily_usage_summary", "error")
        return {"catalog": "exists", "schema": "exists", "daily_usage_summary": "error: [INSUFFICIENT_PERMISSIONS] ..."}

    monkeypatch.setattr(setup, "create_materialized_views", fake_build)
    setup._create_tables_task("cat", "sch", user_token="")

    assert seen["stop_on_error"] is True
    assert task_state["status"] == "error"
    assert task_state["table_progress"]["daily_usage_summary"] == "error"
    assert "Creating `daily_usage_summary` failed" in task_state["error"]
    assert "SELECT on system.billing.usage" in task_state["error"]
    assert "system.billing.usage" in task_state["table_errors"]["daily_usage_summary"]


def test_missing_catalog_is_reported_without_a_table_prefix(monkeypatch, task_state):
    monkeypatch.setattr(
        setup, "create_materialized_views",
        lambda *a, **k: {"catalog": "error: Catalog `cat` does not exist. Create it first."},
    )
    setup._create_tables_task("cat", "sch", user_token="")
    assert task_state["status"] == "error"
    assert task_state["error"] == "Catalog `cat` does not exist. Create it first."


def test_a_worker_that_did_not_build_still_sees_a_table_error(monkeypatch, tmp_path):
    import json

    state_file = tmp_path / "build_progress.json"
    state_file.write_text(json.dumps({
        "status": "running", "error": None,
        "table_progress": {"a": "done", "b": "error"}, "table_errors": {"b": "no access"},
    }))
    monkeypatch.setattr(setup, "_TASK_STATE_FILE", str(state_file))
    mem = {"status": "running", "error": None, "table_progress": {"a": "done", "b": "running"}, "table_errors": {}}
    monkeypatch.setattr(setup, "_create_task_state", mem)
    setup._reconcile_task_state_from_disk()
    assert mem["table_progress"]["b"] == "error"
    assert mem["table_errors"] == {"b": "no access"}


def test_build_errors_lists_only_failed_steps():
    assert mv._build_errors({"t1": "error: boom", "__mv_timings__": {}, "t2": "created"}) == {"t1": "error: boom"}
    assert mv._build_errors({"t1": "created", "schema": "exists"}) == {}
