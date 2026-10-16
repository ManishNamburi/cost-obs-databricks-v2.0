import re
from pathlib import Path

import yaml

from backend import materialized_views
from backend.materialized_views import gold_refresh_status
from backend.materialized_views_remaining import CREATE_WAREHOUSE_OPTIMIZER_FINDINGS

JOBS_YML = Path(__file__).resolve().parents[3] / "bundle" / "resources" / "jobs.yml"


def test_dashboard_objects_missing_system_dashboards_is_skip_not_error():
    exc = Exception("[TABLE_OR_VIEW_NOT_FOUND] The table or view `system`.`dashboards` cannot be found.")
    assert gold_refresh_status("use_case_dashboard_objects", exc).startswith("skipped:")


def test_optimizer_concurrency_reads_the_subquery_column_not_the_struct():
    cte = CREATE_WAREHOUSE_OPTIMIZER_FINDINGS.split("max_concurrency AS (", 1)[1].split("over_scaled AS", 1)[0]
    outer_select = cte.split("FROM (", 1)[0]
    assert "compute.warehouse_id" not in outer_select
    assert re.search(r"compute\.warehouse_id AS warehouse_id,\s*DATE_TRUNC", cte)


def test_setup_job_environment_installs_gold_build_python_deps():
    jobs = yaml.safe_load(JOBS_YML.read_text())
    deps = jobs["resources"]["jobs"]["cost_obs_setup"]["environments"][0]["spec"]["dependencies"]
    assert any(d.startswith("databricks-sql-connector") for d in deps)
    assert any(d.startswith("cachetools") for d in deps)


def test_mv_lock_falls_back_to_a_per_user_path_when_shared_file_is_unwritable(tmp_path, monkeypatch):
    blocked = tmp_path / "shared.lock"
    blocked.write_text("")
    blocked.chmod(0o400)
    monkeypatch.setattr(materialized_views, "_MV_LOCK_PATH", str(blocked))
    monkeypatch.setattr(materialized_views.tempfile, "gettempdir", lambda: str(tmp_path))

    with materialized_views._mv_write_guard():
        pass

    assert (tmp_path / f"cost-obs-mv-refresh-{materialized_views.os.getuid()}.lock").exists()


def test_optional_actuals_missing_is_skip_not_error():
    exc = Exception(
        "[TABLE_OR_VIEW_NOT_FOUND] The table or view "
        "`cmegdemos_catalog`.`cost_obs_2_1`.`actuals_gold` cannot be found. SQLSTATE: 42P01"
    )
    assert gold_refresh_status("daily_cloud_actuals", exc).startswith("skipped:")
    assert gold_refresh_status("daily_azure_actuals", exc).startswith("skipped:")
    assert gold_refresh_status("daily_gcp_actuals", exc).startswith("skipped:")


def test_required_table_missing_is_still_error():
    exc = Exception("[TABLE_OR_VIEW_NOT_FOUND] daily_aiml_models cannot be found")
    status = gold_refresh_status("daily_aiml_models", exc)
    assert status.startswith("error:")


def test_success_passthrough():
    assert gold_refresh_status("daily_cloud_actuals", None, ok="created") == "created"
    assert gold_refresh_status("daily_usage_summary", None, ok="refreshed") == "refreshed"
