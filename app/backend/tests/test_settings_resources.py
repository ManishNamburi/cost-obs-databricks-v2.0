"""Ported Settings coverage for owner persona, SP object ID, and resources inventory."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.routers import settings


def test_resource_inventory_is_bounded_and_redacts_connection_credentials(monkeypatch):
    from backend import db
    from backend.materialized_views import _MV_TABLES

    connection_row = {
        "id": "connection-1",
        "name": "AWS CUR",
        "provider": "aws",
        "secret_access_key": "do-not-return",
        "access_key_id": "also-do-not-return",
    }
    monkeypatch.setattr(
        settings,
        "_load_connections",
        lambda: [connection_row],
    )
    monkeypatch.setattr(settings, "_resource_shared_source_metadata", lambda: [{
        "label": "west",
        "catalog": "west_share",
        "schema": "cost_obs",
        "tables": ["daily_usage_summary"],
    }])
    monkeypatch.setattr(settings, "_resource_unified_views", lambda: ["daily_usage_summary"])
    monkeypatch.setattr(
        "backend.workspace_filter.get_configured_workspace_ids",
        lambda: ["100", "200"],
    )
    settings._tables_cache = None

    result = settings._resource_inventory_snapshot()

    assert result["inventory"]["aggregates"]["count"] == len(_MV_TABLES)
    assert result["inventory"]["cache"]["process_max_entries"] == db._CACHE_MAX_SIZE
    assert result["workspace_filter"] == {
        "mode": "restricted",
        "count": 2,
    }
    assert result["cloud_cost_connections"] == [{
        "id": "connection-1",
        "name": "AWS CUR",
        "provider": "aws",
    }]
    assert "do-not-return" not in repr(result)
    assert "access_key_id" not in repr(result)


def test_resource_unified_views_use_lakebase_registry_not_warehouse(monkeypatch):
    from backend import db

    queries = []
    monkeypatch.setattr(
        db,
        "execute_query",
        lambda query, *_args, **_kwargs: queries.append(query) or [],
    )
    monkeypatch.setattr(db, "get_unified_view_tables", lambda: ["daily_usage_summary", "daily_query_stats"])
    monkeypatch.setattr(
        db,
        "get_mv_sources",
        lambda: [{"label": "west", "catalog": "west_share", "schema": "cost_obs"}],
    )

    assert settings._resource_unified_views() == ["daily_usage_summary", "daily_query_stats"]
    assert settings._resource_shared_source_metadata()[0]["label"] == "west"
    assert queries == []


def test_resources_returns_other_sections_when_apps_api_times_out(monkeypatch):
    async def slow_links():
        time.sleep(0.08)
        return {"app_name": "too-late"}

    monkeypatch.setattr(settings, "_RESOURCES_SUBSECTION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(settings, "_RESOURCES_ENDPOINT_DEADLINE_SECONDS", 1.0)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "cost-obs")
    monkeypatch.setattr(settings, "get_app_config", AsyncMock(return_value={
        "storage_location": {"catalog": "catalog", "schema": "schema"},
        "warehouse": None,
        "version": {},
    }))
    monkeypatch.setattr(settings, "get_auth_status_endpoint", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "get_app_links", slow_links)
    monkeypatch.setattr(settings, "_resource_shared_source_metadata", lambda: [])
    monkeypatch.setattr(settings, "_resource_connection_metadata", lambda: [])
    monkeypatch.setattr(settings, "_resource_unified_views", lambda: [])
    monkeypatch.setattr(
        "backend.workspace_filter.get_configured_workspace_ids",
        lambda: [],
    )
    monkeypatch.setattr(settings, "_resource_refresh_snapshot", lambda: {
        "schedule": {
            "enabled": True,
            "frequency": "nightly",
            "hour_utc": 5,
            "lookback_days": 180,
        },
        "status": {"status": "success"},
    })
    with patch(
        "backend.routers.health.deployment_metadata",
        new=AsyncMock(return_value={
            "deployed_at": "2026-08-31T17:00:00Z",
            "deployer": "owner@example.com",
            "commit_sha": "abc123",
            "available": True,
            "source": "databricks_apps_api",
        }),
    ):
        result = asyncio.run(settings.get_resources())

    assert settings._RESOURCES_SUBSECTION_TIMEOUT_SECONDS <= 3
    assert settings._RESOURCES_ENDPOINT_DEADLINE_SECONDS <= 10
    assert result["subsections"]["app_links"] == {
        "available": False,
        "reason": "temporarily_unavailable",
    }
    assert result["subsections"]["config"] == {"available": True}
    assert result["storage"]["catalog"] == "catalog"
    assert result["app"]["name"] == "cost-obs"
    assert "lakebase" in result


def test_resources_keeps_fast_inventory_when_one_sql_subsection_times_out(
    monkeypatch,
):
    def slow_sources():
        time.sleep(0.2)
        return [{"label": "too-late"}]

    monkeypatch.setattr(settings, "_RESOURCES_SUBSECTION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(settings, "_RESOURCES_ENDPOINT_DEADLINE_SECONDS", 0.15)
    monkeypatch.setattr(settings, "get_app_config", AsyncMock(return_value={
        "storage_location": {},
        "warehouse": None,
        "version": {},
    }))
    monkeypatch.setattr(settings, "get_auth_status_endpoint", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "get_app_links", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "_resource_shared_source_metadata", slow_sources)
    monkeypatch.setattr(
        settings,
        "_resource_connection_metadata",
        lambda: [{"name": "AWS CUR", "provider": "aws"}],
    )
    monkeypatch.setattr(settings, "_resource_unified_views", lambda: ["daily_usage_summary"])
    monkeypatch.setattr(
        "backend.workspace_filter.get_configured_workspace_ids",
        lambda: ["100"],
    )
    monkeypatch.setattr(settings, "_resource_refresh_snapshot", lambda: {
        "schedule": {
            "enabled": False,
            "frequency": "nightly",
            "hour_utc": 5,
            "lookback_days": 180,
        },
        "status": None,
    })
    with patch(
        "backend.routers.health.deployment_metadata",
        new=AsyncMock(return_value={
            "deployed_at": "2026-08-31T17:00:00Z",
            "deployer": None,
            "commit_sha": None,
            "available": True,
            "source": "process_start_approximate_restart",
        }),
    ):
        result = asyncio.run(settings.get_resources())

    assert result["subsections"]["shared_data_sources"] == {
        "available": False,
        "reason": "temporarily_unavailable",
    }
    assert result["subsections"]["cloud_cost_connections"] == {"available": True}
    assert result["shared_data_sources"] == []
    assert result["cloud_cost_connections"] == [{"name": "AWS CUR", "provider": "aws"}]
    assert result["inventory"]["unified_views"]["names"] == ["daily_usage_summary"]
    assert result["workspace_filter"] == {"mode": "restricted", "count": 1}


def test_auth_status_exposes_safe_authoritative_identity_link(monkeypatch):
    me = SimpleNamespace(
        id="sp-object-123",
        user_name="client-123",
        display_name="app-cost-obs",
    )
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc.example.com")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "client-123")
    with (
        patch("backend.db.get_auth_status", return_value={}),
        patch(
            "backend.db.get_workspace_client",
            return_value=SimpleNamespace(
                current_user=SimpleNamespace(me=lambda: me)
            ),
        ),
        patch("backend.db.get_catalog_schema", return_value=("main", "cost_obs")),
    ):
        result = asyncio.run(settings.get_auth_status_endpoint())

    assert result["sp_object_id"] == "sp-object-123"
    assert result["sp_client_id"] == "client-123"
    assert result["effective_oauth_scopes"] == []
    assert result["oauth_scope_source"] == "not_inspected"
    assert result["sp_identity_url"] == (
        "https://dbc.example.com/api/2.0/preview/scim/v2/"
        "ServicePrincipals/sp-object-123"
    )
    assert "secret" not in result


def test_resource_links_reject_credentials_and_strip_token_queries():
    assert settings._safe_resource_link(
        "https://user:secret@github.com/example/repo"
    ) == ""
    assert settings._safe_resource_link(
        "https://github.com/example/repo?access_token=secret#fragment"
    ) == "https://github.com/example/repo"
    assert settings._safe_resource_link(
        "https://dbc.example.com/apps-v2/app/cost-obs/overview?o=12345"
    ).endswith("?o=12345")


def test_owner_cannot_be_demoted_when_other_admins_remain():
    request = SimpleNamespace(headers={"X-Forwarded-Email": "backup@example.com"})
    current = {
        "admins": ["owner@example.com", "backup@example.com"],
        "consumers": [],
        "owner": "owner@example.com",
    }
    with (
        patch.object(
            settings,
            "_require_admin",
            return_value="backup@example.com",
        ),
        patch.object(settings, "_load_user_permissions", return_value=current),
        patch(
            "backend.routers.health.deployment_metadata",
            new=AsyncMock(return_value={
                "deployer": "owner@example.com",
                "source": "databricks_apps_api",
                "available": True,
            }),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(settings.save_user_permissions(
                request,
                settings.UserPermissionsModel(
                    admins=["backup@example.com"],
                    consumers=["owner@example.com"],
                ),
            ))

    assert exc.value.status_code == 400
    assert "Owner" in str(exc.value.detail)


def test_permission_owner_has_stable_store_fallback():
    with patch(
        "backend.routers.health.deployment_metadata",
        new=AsyncMock(return_value={
            "deployer": None,
            "source": "unavailable",
            "available": False,
        }),
    ):
        owner = asyncio.run(settings._permission_owner({
            "admins": ["stored-owner@example.com", "backup@example.com"],
            "consumers": [],
            "owner": "stored-owner@example.com",
        }))

    assert owner == {
        "email": "stored-owner@example.com",
        "source": "permission_store",
        "verified": False,
        "deployment_creator": None,
    }


def test_safe_identity_url_requires_https_service_principals_path():
    assert settings._safe_identity_url("https://dbc.example.com", "abc") == (
        "https://dbc.example.com/api/2.0/preview/scim/v2/ServicePrincipals/abc"
    )
    assert settings._safe_identity_url("http://dbc.example.com", "abc") == ""
    assert settings._safe_identity_url("https://user:pass@dbc.example.com", "abc") == ""
    assert settings._safe_identity_url("https://dbc.example.com", "") == ""
