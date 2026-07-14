"""
Conversational surface — Genie-backed chat for the whole app.

Thin wrapper over the Databricks Genie REST API. Every user prompt is sent
to the configured Genie space (`GENIE_SPACE_ID`). The response is returned
with the generated SQL, the row set, and a short natural-language summary.
No LLM routing, no narrative synthesis — just the space.

Endpoints:

* ``GET /api/conversational/status`` — configuration probe.
* ``POST /api/conversational/message`` — starts a new conversation.
* ``POST /api/conversational/reply`` — sends a follow-up to an existing
  conversation.

The handlers are declared ``def`` (not ``async def``) on purpose: they make
blocking Databricks SDK calls and poll for up to 90 s. FastAPI runs sync path
operations in a worker thread, so the event loop stays free for other
requests — mirroring the ``run_in_executor`` pattern used by the other
routers.

The router runs Genie calls as the requesting user (via
``get_user_workspace_client``) so answers respect the caller's UC and
Genie-space permissions.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import get_user_workspace_client

router = APIRouter()
logger = logging.getLogger(__name__)


_POLL_INTERVAL_S = 1.0
_MAX_POLL_S = 90.0
# Terminal message states. Genie completes into COMPLETED (or
# QUERY_RESULT_EXPIRED when the answer is ready but the cached result set has
# aged out); FAILED / CANCELLED are hard failures.
_TERMINAL_OK = {"COMPLETED", "QUERY_RESULT_EXPIRED"}
_TERMINAL_FAIL = {"FAILED", "CANCELLED"}


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ReplyRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=4000)


def _space_id() -> str:
    sid = (os.environ.get("GENIE_SPACE_ID") or "").strip()
    if not sid:
        raise HTTPException(
            status_code=503,
            detail=(
                "Conversational surface is not configured. Set GENIE_SPACE_ID "
                "in the app resource bindings (or the databricks.yml bundle "
                "variable) to enable it."
            ),
        )
    return sid


def _poll_until_ready(w: Any, space_id: str, conv_id: str, msg_id: str) -> dict[str, Any]:
    """Block on Genie until the message finishes or we hit the max wait.

    Safe to call from a sync path operation — FastAPI runs it in a worker
    thread, so ``time.sleep`` here does not stall the event loop.
    """
    deadline = time.monotonic() + _MAX_POLL_S
    while True:
        msg = w.api_client.do(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}",
        )
        status = (msg.get("status") or "").upper()
        if status in _TERMINAL_FAIL:
            error = msg.get("error") or {}
            raise HTTPException(
                status_code=502,
                detail=(error.get("error") or f"Genie call finished in state {status}"),
            )
        if status in _TERMINAL_OK:
            return msg
        if time.monotonic() > deadline:
            raise HTTPException(status_code=504, detail="Genie response timed out after 90 s")
        time.sleep(_POLL_INTERVAL_S)


def _fetch_query_result(
    w: Any, space_id: str, conv_id: str, msg_id: str, attachment_id: str | None
) -> tuple[list[str], list[list[Any]]]:
    """Fetch the executed query's rows + column names for a completed message.

    Genie does NOT inline result rows into the message object — they must be
    pulled from a dedicated query-result endpoint that returns a SQL
    ``statement_response``. Prefer the per-attachment endpoint (current API);
    fall back to the message-level endpoint for older workspaces.
    """
    base = f"/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}"
    paths = []
    if attachment_id:
        paths.append(f"{base}/attachments/{attachment_id}/query-result")
    paths.append(f"{base}/query-result")

    for path in paths:
        try:
            resp = w.api_client.do("GET", path)
        except Exception as exc:  # noqa: BLE001 — try the next candidate path
            logger.debug("[conversational] query-result GET %s failed: %s", path, exc)
            continue
        stmt = (resp or {}).get("statement_response") or {}
        manifest = stmt.get("manifest") or {}
        schema = manifest.get("schema") or {}
        columns = [str(c.get("name") or "") for c in (schema.get("columns") or [])]
        result = stmt.get("result") or {}
        raw_rows = result.get("data_array")
        rows = raw_rows if isinstance(raw_rows, list) else []
        if columns or rows:
            return columns, rows
    return [], []


def _build_response(
    w: Any, space_id: str, conv_id: str, msg_id: str, message: dict[str, Any]
) -> dict[str, Any]:
    """Assemble {text, sql, columns, rows} from a completed Genie message."""
    text = ""
    sql = ""
    attachment_id: str | None = None

    for attach in message.get("attachments", []) or []:
        text_block = attach.get("text") or {}
        query_block = attach.get("query") or {}
        if isinstance(text_block, dict) and text_block.get("content"):
            text = (text_block.get("content") or "").strip()
        if isinstance(query_block, dict) and (query_block.get("query") or "").strip():
            sql = (query_block.get("query") or "").strip()
            attachment_id = attach.get("attachment_id") or attachment_id
            if not text:
                text = (query_block.get("description") or "").strip()

    if not text:
        text = (message.get("content") or "").strip()

    columns: list[str] = []
    rows: list[list[Any]] = []
    # Only a query attachment produces a result set. A message that terminated
    # with an expired result set keeps its text/SQL but has no rows to fetch.
    if sql and (message.get("status") or "").upper() != "QUERY_RESULT_EXPIRED":
        columns, rows = _fetch_query_result(w, space_id, conv_id, msg_id, attachment_id)

    return {"text": text, "sql": sql, "columns": columns, "rows": rows}


@router.get("/status")
def get_status() -> dict[str, Any]:
    """Report whether the conversational surface can serve requests."""
    space_id = (os.environ.get("GENIE_SPACE_ID") or "").strip()
    if not space_id:
        return {"configured": False, "reason": "GENIE_SPACE_ID env var is empty"}

    try:
        w = get_user_workspace_client()
        w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}")
        return {"configured": True, "space_id": space_id}
    except Exception as exc:  # noqa: BLE001 — surface reason to UI
        logger.warning("[conversational] Genie space probe failed: %s", exc)
        return {"configured": False, "reason": str(exc)}


@router.post("/message")
def start_conversation(req: MessageRequest) -> dict[str, Any]:
    """Open a new Genie conversation with the user's first message."""
    space_id = _space_id()
    w = get_user_workspace_client()
    started = w.api_client.do(
        "POST",
        f"/api/2.0/genie/spaces/{space_id}/start-conversation",
        body={"content": req.message},
    )
    conv_id = (started.get("conversation") or {}).get("id") or started.get("conversation_id")
    msg_id = (started.get("message") or {}).get("id") or started.get("message_id")
    if not conv_id or not msg_id:
        raise HTTPException(status_code=502, detail="Genie did not return conversation/message IDs")

    msg = _poll_until_ready(w, space_id, conv_id, msg_id)
    return {
        "conversation_id": conv_id,
        "message_id": msg_id,
        "response": _build_response(w, space_id, conv_id, msg_id, msg),
    }


@router.post("/reply")
def reply_to_conversation(req: ReplyRequest) -> dict[str, Any]:
    """Send a follow-up message to an existing Genie conversation."""
    space_id = _space_id()
    w = get_user_workspace_client()
    started = w.api_client.do(
        "POST",
        f"/api/2.0/genie/spaces/{space_id}/conversations/{req.conversation_id}/messages",
        body={"content": req.message},
    )
    msg_id = (started.get("message") or {}).get("id") or started.get("id")
    if not msg_id:
        raise HTTPException(status_code=502, detail="Genie did not return a message ID")

    msg = _poll_until_ready(w, space_id, req.conversation_id, msg_id)
    return {
        "conversation_id": req.conversation_id,
        "message_id": msg_id,
        "response": _build_response(w, space_id, req.conversation_id, msg_id, msg),
    }
