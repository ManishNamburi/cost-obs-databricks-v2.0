"""Lakebase-first persistence for leftover app state (prefs, MV sources, catalog)."""
from unittest.mock import patch

import backend.db as db
from backend.routers import settings as settings_mod


def test_get_catalog_schema_env_beats_lakebase(monkeypatch):
    monkeypatch.setenv("COST_OBS_CATALOG", "env_cat")
    monkeypatch.setenv("COST_OBS_SCHEMA", "env_sch")
    with patch.object(db, "lb_get_config", return_value={"catalog": "lb_cat", "schema": "lb_sch"}):
        assert db.get_catalog_schema() == ("env_cat", "env_sch")


def test_get_catalog_schema_uses_lakebase_when_env_absent(monkeypatch):
    monkeypatch.delenv("COST_OBS_CATALOG", raising=False)
    monkeypatch.delenv("COST_OBS_SCHEMA", raising=False)
    monkeypatch.setattr(db, "lakebase_available", lambda: True)
    db._lb_catalog_schema_cache.clear()
    with patch.object(db, "lb_get_config", return_value={"catalog": "lb_cat", "schema": "lb_sch"}):
        with patch.object(db, "_read_dbfs_catalog_override", return_value=("", "")):
            with patch("os.path.exists", return_value=False):
                assert db.get_catalog_schema() == ("lb_cat", "lb_sch")


def test_save_catalog_schema_writes_lakebase(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_CATALOG_OVERRIDE_FILE", str(tmp_path / "catalog.json"))
    with patch.object(db, "lb_set_config") as set_cfg:
        with patch.object(db, "_write_dbfs_catalog_override"):
            db.save_catalog_schema("my_cat", "my_sch")
    set_cfg.assert_called_once_with("catalog_schema", {"catalog": "my_cat", "schema": "my_sch"})


def test_get_mv_sources_prefers_lakebase_including_empty(monkeypatch):
    db._reset_mv_source_cache()
    with patch.object(db, "lb_get_config", return_value=[]):
        with patch.object(db, "read_delta_mv_sources", return_value=[
            {"label": "stale", "catalog": "c", "schema": "s"},
        ]):
            assert db.get_mv_sources() == []
    db._reset_mv_source_cache()


def test_get_mv_sources_reads_lakebase_rows():
    db._reset_mv_source_cache()
    src = {"label": "share-a", "catalog": "other_cat", "schema": "other_sch"}
    with patch.object(db, "lb_get_config", return_value=[src]):
        assert db.get_mv_sources() == [src]
    db._reset_mv_source_cache()


def test_save_mv_sources_writes_lakebase(tmp_path, monkeypatch):
    db._reset_mv_source_cache()
    monkeypatch.setattr(db, "_MV_SOURCES_FILE", str(tmp_path / "mv_sources.json"))
    src = {"label": "share-a", "catalog": "other_cat", "schema": "other_sch"}
    with patch.object(db, "lb_set_config") as set_cfg:
        with patch.object(db, "write_delta_mv_sources"):
            with patch.object(db, "write_dbfs_mv_sources"):
                db.save_mv_sources([src])
    set_cfg.assert_called_once()
    assert set_cfg.call_args[0][0] == "mv_sources"
    assert set_cfg.call_args[0][1] == [src]
    db._reset_mv_source_cache()


def test_get_app_settings_prefers_lakebase():
    with patch.object(settings_mod, "_config_table", return_value="ignored"):
        with patch("backend.db.lb_get_config", return_value={"company_name": "Acme", "theme": "dark"}):
            got = settings_mod.get_app_settings()
    assert got["company_name"] == "Acme"
    assert got["theme"] == "dark"
    assert got["default_date_range_days"] == 30  # default filled in


def test_save_app_settings_writes_lakebase(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "APP_SETTINGS_FILE", str(tmp_path / "app_settings.json"))
    monkeypatch.setattr(settings_mod, "SETTINGS_DIR", str(tmp_path))
    with patch("backend.db.lb_get_config", return_value=None):
        with patch("backend.db.execute_query", side_effect=Exception("TABLE_OR_VIEW_NOT_FOUND")):
            with patch("backend.db.lb_set_config") as set_cfg:
                with patch("backend.db.execute_write"):
                    with patch.object(settings_mod, "_ensure_app_settings_table"):
                        with patch.object(settings_mod, "_config_table", return_value="`c`.`s`.`app_settings`"):
                            settings_mod.save_app_settings({"company_name": "Acme"})
    assert set_cfg.call_args[0][0] == "app_settings"
    assert set_cfg.call_args[0][1]["company_name"] == "Acme"
