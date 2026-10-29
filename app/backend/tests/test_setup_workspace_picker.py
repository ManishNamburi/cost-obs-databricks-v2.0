import asyncio
import json

from backend.routers import setup


def _fake_query(responses, calls):
    def _execute(sql, *args, **kwargs):
        calls.append(sql)
        for needle, result in responses:
            if needle in sql:
                if isinstance(result, Exception):
                    raise result
                return result
        return []
    return _execute


def test_list_workspaces_falls_back_to_billing_when_mv_empty(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.db.get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr("backend.db.execute_query", _fake_query([
        ("daily_workspace_breakdown", []),
        ("system.billing.usage", [
            {"workspace_id": "111", "workspace_name": "prod"},
            {"workspace_id": "222", "workspace_name": None},
        ]),
    ], calls))
    out = asyncio.run(setup.list_workspaces())
    assert out["workspaces"] == [
        {"id": "111", "name": "prod", "historical": False},
        {"id": "222", "name": "222", "historical": True},
    ]
    assert any("system.billing.usage" in c for c in calls)


def test_list_workspaces_falls_back_to_ids_when_names_unavailable(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.db.get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr("backend.db.execute_query", _fake_query([
        ("daily_workspace_breakdown", RuntimeError("TABLE_OR_VIEW_NOT_FOUND")),
        ("workspaces_latest", RuntimeError("PERMISSION_DENIED")),
        ("system.billing.usage", [{"workspace_id": "333", "workspace_name": None}]),
    ], calls))
    out = asyncio.run(setup.list_workspaces())
    assert out["workspaces"] == [{"id": "333", "name": "333", "historical": True}]


def test_empty_saved_filter_is_not_locked(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "SETTINGS_DIR", str(tmp_path))
    monkeypatch.setattr("backend.db.get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr("backend.db.execute_query", lambda *a, **k: [{"workspace_ids": ""}])
    assert asyncio.run(setup.get_workspace_filter()) == {"workspace_ids": [], "locked": False}

    monkeypatch.setattr("backend.db.execute_query", lambda *a, **k: [{"workspace_ids": "111,222"}])
    assert asyncio.run(setup.get_workspace_filter()) == {"workspace_ids": ["111", "222"], "locked": True}


def test_saving_all_workspaces_does_not_write_lock_row(monkeypatch, tmp_path):
    calls = []

    class _Req:
        headers = {"X-Forwarded-Email": "admin@example.com"}

        async def json(self):
            return {"workspace_ids": []}

    async def _admin(_email):
        return "admin"

    monkeypatch.setattr(setup, "SETTINGS_DIR", str(tmp_path))
    monkeypatch.setattr("backend.routers.user._get_user_role", _admin)
    monkeypatch.setattr("backend.db.get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr("backend.db.execute_query", _fake_query([("COUNT(*)", [{"cnt": 0}])], calls))

    assert asyncio.run(setup.save_workspace_filter(_Req())) == {"saved": []}
    assert json.loads((tmp_path / "workspace_filter.json").read_text()) == {"workspace_ids": []}
    assert not any("MERGE" in c or "CREATE TABLE" in c for c in calls)
