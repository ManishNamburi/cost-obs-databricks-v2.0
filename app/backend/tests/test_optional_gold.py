from backend.materialized_views import gold_refresh_status


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
