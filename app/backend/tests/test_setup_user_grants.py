"""Create Tables grants the installing user USE + MANAGE on the app catalog and reports it."""

from backend.routers import setup


def _exec(monkeypatch, refuse=()):
    ran = []

    def _query(sql, *args, **kwargs):
        ran.append(sql)
        if any(r in sql for r in refuse):
            raise RuntimeError("PERMISSION_DENIED: User does not have MANAGE on Catalog 'cat'")
        return []
    monkeypatch.setattr("backend.db.execute_query", _query)
    return ran


def test_grants_use_and_manage_on_catalog_and_schema(monkeypatch):
    ran = _exec(monkeypatch)
    out = setup._grant_user_catalog_visibility("cat", "sch", "", "admin@example.com")
    assert out["ok"] and out["grantee"] == "admin@example.com" and out["manual_sql"] == ""
    assert ran == [
        "GRANT USE CATALOG ON CATALOG `cat` TO `admin@example.com`",
        "GRANT USE SCHEMA ON CATALOG `cat` TO `admin@example.com`",
        "GRANT MANAGE ON CATALOG `cat` TO `admin@example.com`",
        "GRANT USE SCHEMA ON SCHEMA `cat`.`sch` TO `admin@example.com`",
        "GRANT SELECT ON SCHEMA `cat`.`sch` TO `admin@example.com`",
        "GRANT MANAGE ON SCHEMA `cat`.`sch` TO `admin@example.com`",
    ]


def test_one_refused_grant_does_not_skip_the_rest(monkeypatch):
    ran = _exec(monkeypatch, refuse=("MANAGE ON CATALOG",))
    out = setup._grant_user_catalog_visibility("cat", "sch", "", "admin@example.com")
    assert not out["ok"]
    assert len(ran) == 6 and len(out["applied"]) == 5
    assert out["failed"][0]["sql"] == "GRANT MANAGE ON CATALOG `cat` TO `admin@example.com`"
    assert out["manual_sql"] == "GRANT MANAGE ON CATALOG `cat` TO `admin@example.com`;"


def test_no_identity_is_reported_not_silent(monkeypatch):
    ran = _exec(monkeypatch)
    out = setup._grant_user_catalog_visibility("cat", "sch", "", "")
    assert not out["ok"] and out["error"] and ran == []


def test_created_tables_lists_gold_and_config_tables(monkeypatch):
    import asyncio
    monkeypatch.setattr(setup, "get_catalog_schema", lambda: ("cat", "sch"))
    monkeypatch.setattr(
        setup, "check_materialized_views_exist",
        lambda catalog, schema, names: {n: n != "daily_sku_breakdown" for n in names},
    )
    out = asyncio.run(setup.get_created_tables())
    assert (out["catalog"], out["schema"]) == ("cat", "sch")
    by_name = {t["name"]: t["exists"] for t in out["tables"]}
    assert by_name["daily_sku_breakdown"] is False
    assert by_name["daily_usage_summary"] is True
    assert by_name["app_workspace_filter"] is True
