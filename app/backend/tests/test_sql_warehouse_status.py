"""REST-only SQL warehouse health poll — size metadata, no SQL probe."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.routers import health


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "cluster_size", "serverless", "expected_status", "expected_type"),
    [
        ("RUNNING", "Small", True, "warm", "SERVERLESS"),
        ("STOPPED", "X-Small", False, "warming_up", "CLASSIC"),
        ("DELETED", "Small", False, "unavailable", "CLASSIC"),
    ],
)
async def test_sql_warehouse_status_includes_bound_size_and_type(
    state,
    cluster_size,
    serverless,
    expected_status,
    expected_type,
):
    warehouse = SimpleNamespace(
        state=SimpleNamespace(value=state),
        name="Cost Observability",
        cluster_size=cluster_size,
        warehouse_type=SimpleNamespace(value="PRO"),
        enable_serverless_compute=serverless,
    )
    workspace_client = MagicMock()
    workspace_client.warehouses.get.return_value = warehouse

    with (
        patch.dict("os.environ", {"DATABRICKS_WAREHOUSE_ID": "warehouse-123"}),
        patch("backend.db.get_workspace_client", return_value=workspace_client),
    ):
        result = await health.get_sql_warehouse_status()

    assert result["status"] == expected_status
    assert result["warehouse_id"] == "warehouse-123"
    assert result["warehouse_name"] == "Cost Observability"
    assert result["warehouse_size"] == cluster_size
    assert result["warehouse_type"] == expected_type
    assert result["latency_ms"] is None


@pytest.mark.asyncio
async def test_sql_warehouse_status_marks_missing_binding_unavailable():
    with patch.dict(
        "os.environ",
        {"DATABRICKS_WAREHOUSE_ID": "", "DATABRICKS_HTTP_PATH": ""},
        clear=False,
    ):
        result = await health.get_sql_warehouse_status()

    assert result["status"] == "unavailable"
    assert result["state"] == "NOT_CONFIGURED"
    assert result["warehouse_id"] is None
    assert result["warehouse_name"] is None
    assert result["warehouse_size"] is None
    assert result["warehouse_type"] is None


@pytest.mark.asyncio
async def test_sql_warehouse_status_leaves_size_null_on_sdk_failure():
    workspace_client = MagicMock()
    workspace_client.warehouses.get.side_effect = RuntimeError("temporary API failure")

    with (
        patch.dict("os.environ", {"DATABRICKS_WAREHOUSE_ID": "warehouse-123"}),
        patch("backend.db.get_workspace_client", return_value=workspace_client),
        patch("backend.db.execute_query") as execute,
    ):
        result = await health.get_sql_warehouse_status()

    assert result["status"] == "warming_up"
    assert result["state"] == "REST_UNVERIFIED"
    assert result["warehouse_id"] == "warehouse-123"
    assert result["warehouse_name"] is None
    assert result["warehouse_size"] is None
    assert result["warehouse_type"] is None
    execute.assert_not_called()


@pytest.mark.asyncio
async def test_sql_warehouse_status_never_issues_sql_on_the_poll():
    warehouse = SimpleNamespace(
        state=SimpleNamespace(value="RUNNING"),
        name="Cost Observability",
        cluster_size="Medium",
        enable_serverless_compute=True,
    )
    workspace_client = MagicMock()
    workspace_client.warehouses.get.return_value = warehouse

    with (
        patch.dict("os.environ", {"DATABRICKS_WAREHOUSE_ID": "warehouse-123"}),
        patch("backend.db.get_workspace_client", return_value=workspace_client),
        patch("backend.db.execute_query") as execute,
    ):
        result = await health.get_sql_warehouse_status()

    assert result["status"] == "warm"
    assert result["warehouse_size"] == "Medium"
    execute.assert_not_called()
