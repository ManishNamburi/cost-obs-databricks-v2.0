from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.routers import billing


@pytest.mark.asyncio
async def test_cloud_costs_bundle_keeps_infra_when_an_invoice_source_fails():
    infra = {
        "infra_costs": {"clusters": [], "error": None},
        "infra_timeseries": {"timeseries": []},
    }
    with (
        patch.object(billing, "get_infra_bundle", new=AsyncMock(return_value=infra)),
        patch(
            "backend.routers.aws_actual.get_aws_actual_dashboard_bundle",
            new=AsyncMock(return_value={"available": True}),
        ),
        patch(
            "backend.routers.azure_actual.get_azure_actual_dashboard_bundle",
            new=AsyncMock(side_effect=RuntimeError("warehouse busy")),
        ),
        patch(
            "backend.routers.gcp_actual.get_gcp_actual_dashboard_bundle",
            new=AsyncMock(return_value={"available": False}),
        ),
    ):
        payload = await billing._compute_cloud_costs_bundle("2026-01-01", "2026-01-31", None)

    assert payload["availability"] == "partial"
    assert payload["partial_reasons"]["azure_actual"] == "QUERY_FAILED"
    assert payload["aws_actual"]["available"] is True
    assert payload["infra_bundle"] is infra


@pytest.mark.asyncio
async def test_cloud_costs_bundle_fails_when_required_infra_fails():
    with patch.object(
        billing,
        "get_infra_bundle",
        new=AsyncMock(return_value={"infra_costs": {"error": "SQL capacity is full"}}),
    ):
        with pytest.raises(HTTPException) as exc:
            await billing._compute_cloud_costs_bundle("2026-01-01", "2026-01-31", None)
    assert exc.value.status_code == 503
    assert "SQL capacity is full" in str(exc.value.detail)
