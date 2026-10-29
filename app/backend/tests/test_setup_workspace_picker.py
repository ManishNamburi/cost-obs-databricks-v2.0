import asyncio
import json

import pytest
from fastapi import HTTPException

from backend.routers import setup


@pytest.fixture
def fake_db(monkeypatch, tmp_path):
    """Route execute_query/execute_write through a recorder; `row` is the stored filter row."""
    state = {"cols": ["workspace_ids_json", "updated_at"], "row": None, "writes": [], "mv": []}

    def _query(sql, *args, **kwargs):
        if "daily_workspace_breakdown" in sql:
            return state["mv"]
        if sql.startswith("DESCRIBE"):
            return [{"col_name": c} for c in state["cols"]]
        if "app_workspace_filter" in sql:
            return [state["row"]] if state["row"] is not None else []
        return []

    def _write(sql, params=None):
        state["writes"].append((sql, params))
        return 1

    monkeypatch.setattr(setup, "SETTINGS_DIR", str(tmp_path))
    monkeypatch.setattr("backend.db.get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr("backend.db.execute_query", _query)
    monkeypatch.setattr("backend.db.execute_write", _write)
    monkeypatch.setattr("backend.routers.settings._ensure_workspace_filter_table", lambda: None)
    return state


class _Req:
    headers = {"X-Forwarded-Email": "admin@example.com"}

    def __init__(self, ids):
        self._ids = ids

    async def json(self):
        return {"workspace_ids": self._ids}


@pytest.fixture
def admin(monkeypatch):
    async def _role(_email):
        return "admin"
    monkeypatch.setattr("backend.routers.user._get_user_role", _role)


def test_list_workspaces_falls_back_to_top_nav_list_when_mv_empty(fake_db, monkeypatch):
    async def _top_nav(start_date=None, end_date=None):
        return {"workspaces": [
            {"id": "111", "name": "prod", "historical": False},
            {"id": "222", "name": None, "historical": True},
        ]}
    monkeypatch.setattr("backend.routers.billing.get_workspace_list", _top_nav)
    out = asyncio.run(setup.list_workspaces())
    assert out["workspaces"] == [
        {"id": "111", "name": "prod", "historical": False},
        {"id": "222", "name": "222", "historical": True},
    ]


def test_list_workspaces_prefers_mv_when_built(fake_db, monkeypatch):
    fake_db["mv"] = [{"workspace_id": "111", "workspace_name": "prod"}]

    async def _top_nav(**kwargs):
        raise AssertionError("fallback should not run")
    monkeypatch.setattr("backend.routers.billing.get_workspace_list", _top_nav)
    assert asyncio.run(setup.list_workspaces())["workspaces"] == [{"id": "111", "name": "prod", "historical": False}]


@pytest.mark.parametrize("row, ids", [
    ({"workspace_ids_json": '["111", "222"]'}, ["111", "222"]),
    ({"workspace_ids_json": "[]"}, []),
    ({"workspace_ids": "111,222"}, ["111", "222"]),
    ({"workspace_ids": ""}, []),
    ({"workspace_ids": "  "}, []),
    ({"workspace_ids_json": "not json"}, []),
])
def test_parse_saved_ids_reads_both_schemas(row, ids):
    assert setup._parse_saved_workspace_ids(row) == ids


def test_lock_follows_saved_pool_in_either_schema(fake_db):
    fake_db["row"] = {"workspace_ids": ""}
    assert asyncio.run(setup.get_workspace_filter()) == {"workspace_ids": [], "locked": False}
    fake_db["row"] = {"workspace_ids_json": '["111"]', "updated_at": None}
    assert asyncio.run(setup.get_workspace_filter()) == {"workspace_ids": ["111"], "locked": True}


def test_save_writes_json_column_created_by_create_tables(fake_db, admin):
    assert asyncio.run(setup.save_workspace_filter(_Req(["111", "222"]))) == {"saved": ["111", "222"]}
    sql, params = fake_db["writes"][-1]
    assert "workspace_ids_json" in sql and json.loads(params["v"]) == ["111", "222"]


def test_save_writes_legacy_csv_column(fake_db, admin):
    fake_db["cols"] = ["workspace_ids"]
    asyncio.run(setup.save_workspace_filter(_Req(["111", "222"])))
    sql, params = fake_db["writes"][-1]
    assert "(workspace_ids)" in sql and params == {"v": "111,222"}


def test_saving_all_workspaces_clears_pool_without_locking(fake_db, admin, tmp_path):
    fake_db["row"] = {"workspace_ids": ""}
    assert asyncio.run(setup.save_workspace_filter(_Req([]))) == {"saved": []}
    assert json.loads((tmp_path / "workspace_filter.json").read_text()) == {"workspace_ids": []}
    assert [w[0].split()[0] for w in fake_db["writes"]] == ["DELETE"]


def test_save_rejected_once_a_pool_is_locked(fake_db, admin):
    fake_db["row"] = {"workspace_ids_json": '["111"]'}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(setup.save_workspace_filter(_Req(["222"])))
    assert exc.value.status_code == 409
    assert fake_db["writes"] == []
