"""Source-capability reason fields for shared-source scope.

When selected source labels leave gold/unified empty or unpublished, tab APIs
must return available=false with a typed reason instead of silent empty/$0.
"""
import asyncio
from unittest.mock import patch

import pytest

from backend import db
from backend.db import (
    SourceScopeUnsupportedError,
    reset_source_labels,
    selected_sources_publish,
    set_source_labels,
    source_label_filter_clause,
    source_scope_unavailable,
)
from backend.routers import (
    ai_gateway,
    aiml,
    apps,
    genie_cost,
    tagging,
    users_groups,
    warehouse_health,
)


@pytest.fixture(autouse=True)
def _source_context(monkeypatch):
    monkeypatch.setattr(db, "get_local_source_label", lambda: "local")
    monkeypatch.setattr(
        db,
        "get_mv_sources",
        lambda: [{
            "label": "shared-west",
            "tables": ["daily_usage_summary"],
        }],
    )
    monkeypatch.setattr(db, "get_unified_view_tables", lambda: ["daily_usage_summary"])
    token = set_source_labels([])
    try:
        yield
    finally:
        reset_source_labels(token)


def test_unknown_share_label_does_not_publish():
    token = set_source_labels(["not-configured"])
    try:
        assert selected_sources_publish({"daily_usage_summary"}) is False
        assert source_scope_unavailable({"daily_usage_summary"}, "unused") is not None
    finally:
        reset_source_labels(token)


def test_empty_selection_is_always_supported():
    assert selected_sources_publish({"daily_sku_breakdown"}) is True
    assert source_scope_unavailable({"daily_sku_breakdown"}, "unused") is None


def test_shared_source_without_gold_emits_shared_scope_unsupported():
    token = set_source_labels(["shared-west"])
    try:
        payload = source_scope_unavailable(
            {"daily_sku_breakdown"},
            "The selected shared source does not publish AI/ML cost detail.",
        )
    finally:
        reset_source_labels(token)

    assert payload == {
        "available": False,
        "reason": "shared_scope_unsupported",
        "reason_detail": "The selected shared source does not publish AI/ML cost detail.",
        "error_code": "SOURCE_SCOPE_UNSUPPORTED",
    }


def test_missing_aiml_grain_does_not_block_sku_backed_tabs(monkeypatch):
    """Genie / Unity Gateway / AIML cost must not fail just because models grain is missing."""
    monkeypatch.setattr(
        db,
        "get_mv_sources",
        lambda: [{
            "label": "shared-west",
            "tables": ["daily_sku_breakdown", "daily_ai_gateway"],
        }],
    )
    monkeypatch.setattr(
        db,
        "get_unified_view_tables",
        lambda: ["daily_sku_breakdown", "daily_ai_gateway"],
    )
    token = set_source_labels(["shared-west"])
    try:
        assert selected_sources_publish({"daily_sku_breakdown"}) is True
        assert selected_sources_publish({"daily_ai_gateway"}) is True
        assert source_scope_unavailable({"daily_sku_breakdown"}, "unused") is None
        assert source_scope_unavailable({"daily_ai_gateway"}, "unused") is None
        assert source_scope_unavailable({"daily_aiml_models"}, "unused") is not None
    finally:
        reset_source_labels(token)


def test_source_label_filter_clause_raises_for_unpublished_template():
    token = set_source_labels(["shared-west"])
    try:
        with pytest.raises(SourceScopeUnsupportedError) as exc:
            source_label_filter_clause(
                "SELECT 1 FROM `{catalog}`.`{schema}`.`daily_sku_breakdown`"
            )
        assert exc.value.code == "SOURCE_SCOPE_UNSUPPORTED"
        clause = source_label_filter_clause()
        assert "source_label IN ('shared-west')" in clause
    finally:
        reset_source_labels(token)


def test_users_shared_only_scope_is_explicitly_unavailable():
    token = set_source_labels(["shared-west"])
    try:
        with (
            patch.object(users_groups, "get_local_source_label", return_value="local"),
            patch.object(users_groups, "execute_queries_parallel") as execute,
        ):
            result = asyncio.run(
                users_groups.get_users_groups_bundle(
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    workspace_ids=None,
                )
            )
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    assert result["reason"] == "identity_detail_unavailable_for_shared_sources"
    assert result["top_users"] == []
    execute.assert_not_called()


def test_users_mixed_scope_keeps_local_identity_and_notes_omission():
    token = set_source_labels(["local", "shared-west"])
    try:
        with (
            patch.object(users_groups, "get_local_source_label", return_value="local"),
            patch.object(users_groups, "delta_cache_get", return_value=None),
            patch.object(users_groups, "delta_cache_put"),
            patch.object(
                users_groups,
                "execute_queries_parallel",
                return_value={
                    "summary": [{
                        "user_count": 1,
                        "workspace_count": 1,
                        "total_spend": 10,
                        "total_dbus": 2,
                        "avg_spend_per_user": 10,
                    }],
                    "top_users": [{
                        "user_email": "local@example.com",
                        "total_spend": 10,
                        "total_dbus": 2,
                        "active_days": 1,
                        "workspace_count": 1,
                    }],
                    "product_breakdown": [],
                    "timeseries": [],
                    "by_workspace": [],
                    "spend_growth": [],
                    "user_growth": [],
                },
            ),
        ):
            result = asyncio.run(
                users_groups.get_users_groups_bundle(
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    workspace_ids=None,
                )
            )
    finally:
        reset_source_labels(token)

    assert result["available"] is True
    assert result["reason"] == "shared_identity_detail_omitted"
    assert [row["user_email"] for row in result["top_users"]] == ["local@example.com"]


def test_genie_bundle_unsupported_when_sku_gold_unpublished():
    token = set_source_labels(["shared-west"])
    try:
        with patch("backend.unity_gateway.list_genie_space_inventory", return_value={"spaces": []}):
            result = genie_cost.get_genie_dashboard_bundle(
                start_date="2026-08-01",
                end_date="2026-08-28",
                workspace_ids=None,
            )
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    assert result["reason"] == "shared_scope_unsupported"
    assert result["workspaces"] == []
    assert "Genie" in result["reason_detail"]


def test_aiml_bundle_uses_sku_gold_not_aiml_grain(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_mv_sources",
        lambda: [{"label": "shared-west", "tables": ["daily_sku_breakdown"]}],
    )
    monkeypatch.setattr(db, "get_unified_view_tables", lambda: ["daily_sku_breakdown"])
    token = set_source_labels(["shared-west"])
    try:
        with (
            patch.object(aiml, "delta_cache_get", return_value={"summary": {"total_spend": 1}}),
        ):
            result = asyncio.run(
                aiml.get_aiml_dashboard_bundle(
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    workspace_ids=None,
                )
            )
    finally:
        reset_source_labels(token)

    assert result["summary"]["total_spend"] == 1
    assert result.get("reason") != "shared_scope_unsupported"


def test_ai_gateway_bundle_unsupported_only_for_ai_gateway_gold():
    token = set_source_labels(["shared-west"])
    try:
        with (
            patch.object(ai_gateway, "_get_usage_table", return_value="main.cost.ai_gateway"),
            patch("backend.unity_gateway.list_unity_gateway_inventory", return_value={"model_services": []}),
            patch("backend.unity_gateway.usage_schema_label", return_value="unity"),
        ):
            result = ai_gateway.get_ai_gateway_dashboard_bundle(
                start_date="2026-08-01",
                end_date="2026-08-28",
                workspace_ids=None,
                workspace_id=None,
            )
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    assert result["reason"] == "shared_scope_unsupported"
    assert "Unity Gateway" in result["reason_detail"]
    assert result["by_model"] == []


def test_apps_and_tagging_bundles_emit_shared_scope_unsupported():
    token = set_source_labels(["shared-west"])
    try:
        apps_result = asyncio.run(
            apps.get_apps_dashboard_bundle(
                start_date="2026-08-01",
                end_date="2026-08-28",
                active_only=False,
                workspace_ids=None,
            )
        )
        tagging_result = asyncio.run(
            tagging.get_tagging_dashboard_bundle(
                start_date="2026-08-01",
                end_date="2026-08-28",
                workspace_ids=None,
            )
        )
    finally:
        reset_source_labels(token)

    assert apps_result["available"] is False
    assert apps_result["reason"] == "shared_scope_unsupported"
    assert tagging_result["available"] is False
    assert tagging_result["reason"] == "shared_scope_unsupported"


def test_warehouse_health_blocked_for_shared_only_without_idle_gold():
    token = set_source_labels(["shared-west"])
    try:
        result = asyncio.run(warehouse_health.get_warehouse_health())
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    assert result["reason"] == "shared_scope_unsupported"
    assert result["recommendations"] == []


def test_warehouse_health_stays_blocked_even_when_share_lists_idle_gold(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_mv_sources",
        lambda: [{"label": "shared-west", "tables": ["daily_warehouse_idle"]}],
    )
    monkeypatch.setattr(db, "get_unified_view_tables", lambda: ["daily_warehouse_idle"])
    token = set_source_labels(["shared-west"])
    try:
        with patch.object(warehouse_health, "execute_queries_parallel") as execute:
            result = asyncio.run(warehouse_health.get_warehouse_health())
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    execute.assert_not_called()


def test_fast_dbu_bundle_is_typed_unavailable_for_unpublished_usage():
    from backend.routers import billing

    token = set_source_labels(["shared-west"])
    try:
        with patch.object(billing, "delta_cache_get", return_value=None):
            result = asyncio.run(
                billing.get_dashboard_bundle_fast(
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    workspace_ids=None,
                )
            )
    finally:
        reset_source_labels(token)

    assert result["available"] is False
    assert result["error_code"] == "SOURCE_SCOPE_UNSUPPORTED"
    assert result["products"]["total_spend"] == 0
    assert result["summary"].get("available") is False
