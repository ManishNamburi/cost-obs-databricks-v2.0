"""Unity Gateway usage-schema mapping and SDK inventory.

`system.ai_gateway.usage` (and the admin-shared derived table) moved from the
legacy Mosaic AI Gateway columns (`timestamp`, `route_name`, `model_name`,
`client_user`, `*_token_count`, `http_status_code`) to Unity Gateway columns
(`event_time`, `service_name`/`endpoint_name`, `destination_model`,
`requester`, `input_tokens`, `status_code`). Gold `daily_ai_gateway` still
stores the stable grain names (`route_name`, `model_name`, `client_user`) so
Lakebase copies keep working.

Inventory uses `WorkspaceClient.ai_gateway` (databricks-sdk >= 0.136). Older
SDKs fall back to the Unity Catalog REST paths.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from cachetools import TTLCache

from backend.db import execute_query, get_catalog_schema, get_workspace_client

logger = logging.getLogger(__name__)

_columns_cache: TTLCache = TTLCache(maxsize=8, ttl=3600)
_inventory_cache: TTLCache = TTLCache(maxsize=8, ttl=300)
_inventory_lock = threading.Lock()
INVENTORY_TIMEOUT_S = 5.0


def cached_inventory(
    key: str, fetch: Callable[[], dict[str, Any]], empty: dict[str, Any],
) -> dict[str, Any]:
    """Return a cached SDK inventory, fetching it with a hard time limit.

    Inventory is decoration on the cost tabs; a slow or hung SDK call must not
    hold the tab's response.
    """
    with _inventory_lock:
        hit = _inventory_cache.get(key)
    if hit is not None:
        return hit
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["result"] = fetch()
        except Exception as exc:  # noqa: BLE001
            box["error"] = str(exc)

    # Daemon thread: a hung SDK call must not block worker shutdown.
    worker = threading.Thread(target=_run, name=f"inventory-{key}", daemon=True)
    worker.start()
    worker.join(INVENTORY_TIMEOUT_S)
    if worker.is_alive():
        return {**empty, "available": False, "error": "Inventory lookup timed out; showing cost data only."}
    if "error" in box:
        return {**empty, "available": False, "error": box["error"]}
    result = box["result"]
    with _inventory_lock:
        _inventory_cache[key] = result
    return result

# Logical field -> preferred physical columns (new schema first).
_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "event_ts": ("event_time", "timestamp"),
    "service": ("service_name", "endpoint_name", "route_name"),
    "model": ("destination_model", "model_name"),
    "requester": ("requester", "client_user"),
    "input_tokens": ("input_tokens", "input_token_count"),
    "output_tokens": ("output_tokens", "output_token_count"),
    "total_tokens": ("total_tokens", "total_token_count"),
    "latency": ("request_duration_ms", "latency_ms"),
    "status_code": ("status_code", "http_status_code"),
    "service_type": ("service_type",),
}

_NEW_DEFAULTS: dict[str, str] = {
    "event_ts": "event_time",
    "service": "COALESCE(service_name, endpoint_name)",
    "model": "destination_model",
    "requester": "requester",
    "input_tokens": "COALESCE(input_tokens, 0)",
    "output_tokens": "COALESCE(output_tokens, 0)",
    "total_tokens": "COALESCE(total_tokens, COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))",
    "latency": "CAST(NULL AS DOUBLE)",
    "status_code": "COALESCE(status_code, 0)",
    "service_type": "service_type",
}


def _column_names(table: str) -> set[str]:
    if not table:
        return set()
    if table in _columns_cache:
        return _columns_cache[table]
    try:
        rows = execute_query(f"SHOW COLUMNS IN {table}", None)
    except Exception as exc:  # noqa: BLE001 — fall back to Unity Gateway names
        logger.info("Unity Gateway SHOW COLUMNS on %s failed (%s); using current schema", table, exc)
        return set()
    names: set[str] = set()
    for row in rows or []:
        name = (
            row.get("col_name")
            or row.get("column_name")
            or row.get("colName")
            or row.get("colname")
            or ""
        )
        if name:
            names.add(str(name).lower())
    if names:
        _columns_cache[table] = names
    return names


def pick_usage_columns(table: str) -> dict[str, str]:
    """Return SQL expressions for each logical usage field."""
    cols = _column_names(table)
    if not cols:
        return dict(_NEW_DEFAULTS)
    picked: dict[str, str] = {}
    for logical, candidates in _COLUMN_CANDIDATES.items():
        match = next((c for c in candidates if c.lower() in cols), None)
        if match:
            picked[logical] = match
        else:
            picked[logical] = _NEW_DEFAULTS[logical]
    if "total_tokens" not in cols and "total_token_count" not in cols:
        picked["total_tokens"] = (
            f"COALESCE({picked['input_tokens']}, 0) + COALESCE({picked['output_tokens']}, 0)"
        )
    if picked.get("latency") == _NEW_DEFAULTS["latency"]:
        picked["latency"] = "CAST(NULL AS DOUBLE)"
    if "service_type" not in cols:
        picked["service_type"] = "CAST(NULL AS STRING)"
    return picked


def usage_schema_label(table: str) -> str:
    cols = _column_names(table)
    if "event_time" in cols or "service_name" in cols or "requester" in cols:
        return "unity"
    if "timestamp" in cols or "route_name" in cols or "client_user" in cols:
        return "legacy"
    return "unity"


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    as_dict = getattr(obj, "as_dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _service_row(obj: Any) -> dict[str, Any]:
    data = _as_dict(obj)
    name = data.get("name") or getattr(obj, "name", None) or ""
    comment = data.get("comment") or getattr(obj, "comment", None) or ""
    owner = data.get("effective_owner") or data.get("created_by") or ""
    destinations: list[str] = []
    config = data.get("config") or {}
    routing = config.get("routing") if isinstance(config, dict) else {}
    dests = routing.get("destinations") if isinstance(routing, dict) else None
    for dest in dests or []:
        if not isinstance(dest, dict):
            continue
        ppt = dest.get("pay_per_token_config") or {}
        model = ppt.get("model") if isinstance(ppt, dict) else None
        destinations.append(str(model or dest.get("name") or dest.get("destination_type") or ""))
    return {
        "name": str(name),
        "comment": str(comment or ""),
        "owner": str(owner or ""),
        "destinations": [d for d in destinations if d],
        "kind": "model_service",
    }


def _list_with_sdk(api: Any, method_name: str, parent: str) -> list[Any]:
    method = getattr(api, method_name, None)
    if not callable(method):
        return []
    try:
        return list(method(parent=parent, page_size=200) or [])
    except TypeError:
        try:
            return list(method(parent=parent) or [])
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unity Gateway SDK %s(%s) failed: %s", method_name, parent, exc)
            return []
    except Exception as exc:  # noqa: BLE001
        logger.debug("Unity Gateway SDK %s(%s) failed: %s", method_name, parent, exc)
        return []


def _list_with_rest(w: Any, path: str, parent: str, key: str) -> list[dict[str, Any]]:
    try:
        resp = w.api_client.do(
            "GET",
            path,
            query={"parent": parent, "page_size": 200, "view": "BASIC"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Unity Gateway REST %s parent=%s failed: %s", path, parent, exc)
        return []
    rows = (resp or {}).get(key) or []
    return rows if isinstance(rows, list) else []


def _parents() -> list[str]:
    parents = ["schemas/system.ai"]
    catalog, schema = get_catalog_schema()
    if catalog and schema:
        parents.append(f"schemas/{catalog}.{schema}")
    # De-dupe, keep order
    seen: set[str] = set()
    out: list[str] = []
    for parent in parents:
        if parent not in seen:
            seen.add(parent)
            out.append(parent)
    return out


def list_unity_gateway_inventory() -> dict[str, Any]:
    """Best-effort model / MCP service inventory for the Unity Gateway tab."""
    try:
        w = get_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "model_services": [], "mcp_services": []}

    api = getattr(w, "ai_gateway", None)
    model_services: list[dict[str, Any]] = []
    mcp_services: list[dict[str, Any]] = []
    errors: list[str] = []

    for parent in _parents():
        models = _list_with_sdk(api, "list_model_services", parent) if api is not None else []
        if not models:
            models = _list_with_rest(w, "/api/2.1/unity-catalog/model-services", parent, "model_services")
        mcps = _list_with_sdk(api, "list_mcp_services", parent) if api is not None else []
        if not mcps:
            mcps = _list_with_rest(w, "/api/2.1/unity-catalog/mcp-services", parent, "mcp_services")
        if not models and not mcps and api is None:
            errors.append(f"{parent}: Unity Gateway SDK is not on this runtime")
        for item in models:
            row = _service_row(item)
            row["parent"] = parent
            if row["name"]:
                model_services.append(row)
        for item in mcps:
            row = _service_row(item)
            row["kind"] = "mcp_service"
            row["parent"] = parent
            if row["name"]:
                mcp_services.append(row)

    return {
        "available": True,
        "sdk": api is not None,
        "model_services": model_services[:200],
        "mcp_services": mcp_services[:200],
        "error": "; ".join(errors) if errors and not model_services and not mcp_services else None,
    }


def list_genie_space_inventory(configured_space_id: str = "") -> dict[str, Any]:
    """Genie spaces visible to the app identity, plus conversation count for ours."""
    try:
        w = get_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "spaces": [], "space_count": 0}

    genie = getattr(w, "genie", None)
    if genie is None:
        return {"available": False, "error": "Genie SDK is not on this runtime", "spaces": [], "space_count": 0}

    spaces: list[dict[str, Any]] = []
    try:
        page = genie.list_spaces(page_size=200)
        raw = getattr(page, "spaces", None)
        if raw is None and isinstance(page, dict):
            raw = page.get("spaces")
        for space in raw or []:
            data = _as_dict(space)
            space_id = str(data.get("space_id") or getattr(space, "space_id", "") or "")
            spaces.append(
                {
                    "space_id": space_id,
                    "title": str(data.get("title") or getattr(space, "title", "") or ""),
                    "description": str(data.get("description") or getattr(space, "description", "") or ""),
                    "warehouse_id": str(data.get("warehouse_id") or getattr(space, "warehouse_id", "") or ""),
                    "configured": bool(configured_space_id and space_id == configured_space_id),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Genie list_spaces failed: %s", exc)
        return {"available": False, "error": str(exc), "spaces": [], "space_count": 0}

    conversation_count = 0
    conversation_count_capped = False
    if configured_space_id:
        try:
            token = None
            for _ in range(10):
                conv = genie.list_conversations(
                    configured_space_id, page_size=100, include_all=True, page_token=token,
                )
                conversation_count += len(list(getattr(conv, "conversations", None) or []))
                token = getattr(conv, "next_page_token", None)
                if not token:
                    break
            else:
                conversation_count_capped = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Genie list_conversations failed: %s", exc)

    return {
        "available": True,
        "spaces": spaces[:200],
        "space_count": len(spaces),
        "configured_space_id": configured_space_id or None,
        "configured_conversation_count": conversation_count,
        "configured_conversation_count_capped": conversation_count_capped,
    }
