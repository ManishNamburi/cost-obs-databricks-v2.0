"""
Budget & Usage Policy Router (Feature 3)

Exposes two Databricks account-level APIs:
  - BudgetsAPI        (/api/2.1/accounts/{id}/budgets)         — dollar-based spend budgets
  - BudgetPolicyAPI   (/api/2.1/accounts/{id}/budget-policies) — serverless usage policies

Requires:
  DATABRICKS_ACCOUNT_ID   — account UUID (auto-injected by DAB in most environments)
  SP must have account_admin or budget_admin role for write operations;
  read operations work with any account-level role.

Spend correlation:
  Budget configurations define alert thresholds for a time period but the SDK does
  not return current-period actuals.  We correlate against system.billing.usage for
  the current calendar month and add estimated_spend_mtd to each configuration.
  This is a best-effort estimate — if system.billing.usage is unavailable the field
  will be null and the UI degrades gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.db import (
    get_account_client,
    execute_query,
    delta_cache_get,
    delta_cache_put,
    bundle_cache_key,
)
from backend import cache_ttls

router = APIRouter()
logger = logging.getLogger(__name__)

_BUNDLE_TTL = cache_ttls.BILLING_BUNDLE  # 5 min TTL — account-level data changes rarely

# ── spend correlation query (current calendar month) ─────────────────────────
_MTD_SPEND_SQL = """
SELECT
  SUM(list_cost) AS total_spend_mtd,
  workspace_id
FROM system.billing.usage u
JOIN system.billing.list_prices lp
  ON u.sku_name = lp.sku_name
  AND u.cloud = lp.cloud
  AND lp.price_start_time <= u.usage_start_time
  AND (lp.price_end_time IS NULL OR lp.price_end_time > u.usage_start_time)
WHERE DATE(u.usage_start_time) >= DATE_TRUNC('month', CURRENT_DATE())
  AND DATE(u.usage_start_time) < CURRENT_DATE()
GROUP BY workspace_id
"""


def _serialize_budget_policy(p: Any) -> dict:
    return {
        "policy_id": p.policy_id,
        "policy_name": p.policy_name,
        "binding_workspace_ids": list(p.binding_workspace_ids or []),
        "custom_tags": [
            {"key": t.key, "value": t.value}
            for t in (p.custom_tags or [])
        ],
    }


def _serialize_alert(a: Any) -> dict:
    return {
        "alert_configuration_id": a.alert_configuration_id,
        "quantity_threshold": a.quantity_threshold,
        "quantity_type": a.quantity_type.value if a.quantity_type else None,
        "time_period": a.time_period.value if a.time_period else None,
        "trigger_type": a.trigger_type.value if a.trigger_type else None,
    }


def _serialize_budget_filter(f: Any) -> dict | None:
    if f is None:
        return None
    result: dict = {}
    if getattr(f, "workspace_id", None):
        result["workspace_id"] = {
            "operator": f.workspace_id.operator.value if f.workspace_id.operator else None,
            "values": list(f.workspace_id.values or []),
        }
    if getattr(f, "tags", None):
        result["tags"] = [
            {
                "key": t.key,
                "value": {"operator": t.value.operator.value if t.value and t.value.operator else None,
                           "values": list(t.value.values or [])} if t.value else None,
            }
            for t in f.tags
        ]
    return result or None


def _serialize_budget_config(b: Any) -> dict:
    return {
        "budget_configuration_id": b.budget_configuration_id,
        "account_id": b.account_id,
        "display_name": b.display_name,
        "create_time": b.create_time,
        "update_time": getattr(b, "update_time", None),
        "alert_configurations": [_serialize_alert(a) for a in (b.alert_configurations or [])],
        "filter": _serialize_budget_filter(b.filter),
    }


async def _get_mtd_spend_by_workspace() -> dict[str, float]:
    """Query system.billing.usage for current-month spend, keyed by workspace_id."""
    try:
        rows = await asyncio.to_thread(execute_query, _MTD_SPEND_SQL, {})
        return {str(r["workspace_id"]): float(r["total_spend_mtd"] or 0) for r in (rows or [])}
    except Exception as e:
        logger.debug("MTD spend query failed (non-fatal): %s", e)
        return {}


def _annotate_with_spend(configs: list[dict], spend_by_ws: dict[str, float]) -> list[dict]:
    """Add estimated_spend_mtd to each budget config by summing spend for filtered workspaces."""
    for cfg in configs:
        f = cfg.get("filter")
        workspace_ids = None
        if f and "workspace_id" in f:
            workspace_ids = [str(v) for v in f["workspace_id"].get("values", [])]

        if workspace_ids:
            cfg["estimated_spend_mtd"] = sum(
                spend_by_ws.get(ws, 0.0) for ws in workspace_ids
            )
        elif not workspace_ids and spend_by_ws:
            # No workspace filter → budget covers all workspaces
            cfg["estimated_spend_mtd"] = sum(spend_by_ws.values())
        else:
            cfg["estimated_spend_mtd"] = None
    return configs


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_budget_dashboard(request: Request):
    """Combined bundle: budget policies + budget configurations + MTD spend correlation."""
    cache_key = bundle_cache_key("/api/budget/dashboard", {})
    cached = delta_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        a = get_account_client()
    except ValueError as e:
        return {
            "available": False,
            "error": str(e),
            "policies": [],
            "configurations": [],
            "total_policies": 0,
            "total_configurations": 0,
        }

    # Fetch policies and configurations
    policies: list[dict] = []
    configurations: list[dict] = []
    errors: list[str] = []

    try:
        policies = [_serialize_budget_policy(p) for p in a.budget_policies.list()]
    except Exception as e:
        logger.warning("Failed to list budget policies: %s", e)
        errors.append(f"policies: {e}")

    try:
        configurations = [_serialize_budget_config(b) for b in a.budgets.list()]
    except Exception as e:
        logger.warning("Failed to list budget configurations: %s", e)
        errors.append(f"configurations: {e}")

    # Annotate with current-month actual spend (best-effort)
    if configurations:
        spend_by_ws = await _get_mtd_spend_by_workspace()
        configurations = _annotate_with_spend(configurations, spend_by_ws)

    result = {
        "available": True,
        "policies": policies,
        "configurations": configurations,
        "total_policies": len(policies),
        "total_configurations": len(configurations),
        "errors": errors or None,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    delta_cache_put(cache_key, "budget:dashboard", result, ttl_seconds=_BUNDLE_TTL)
    return result


@router.get("/policies")
async def list_budget_policies():
    """List all serverless usage policies (budget policies) for the account."""
    try:
        a = get_account_client()
        return {"policies": [_serialize_budget_policy(p) for p in a.budget_policies.list()]}
    except ValueError as e:
        return {"policies": [], "error": str(e)}
    except Exception as e:
        logger.exception("list_budget_policies failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/{policy_id}")
async def get_budget_policy(policy_id: str):
    try:
        a = get_account_client()
        p = a.budget_policies.get(policy_id)
        return _serialize_budget_policy(p)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/configurations")
async def list_budget_configurations():
    """List all account budgets (spend-based configurations with alert thresholds)."""
    try:
        a = get_account_client()
        configs = [_serialize_budget_config(b) for b in a.budgets.list()]
        if configs:
            spend_by_ws = await _get_mtd_spend_by_workspace()
            configs = _annotate_with_spend(configs, spend_by_ws)
        return {"configurations": configs}
    except ValueError as e:
        return {"configurations": [], "error": str(e)}
    except Exception as e:
        logger.exception("list_budget_configurations failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations/{config_id}")
async def get_budget_configuration(config_id: str):
    try:
        a = get_account_client()
        b = a.budgets.get(config_id)
        result = _serialize_budget_config(b)
        spend_by_ws = await _get_mtd_spend_by_workspace()
        result = _annotate_with_spend([result], spend_by_ws)[0]
        return result
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
