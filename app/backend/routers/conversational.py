"""
Conversational surface — Genie-backed chat for the whole app.

Thin wrapper over the Databricks Genie REST API. Every user prompt is sent
to the configured Genie space (`GENIE_SPACE_ID`). The response is returned
verbatim with the generated SQL, the row set, and a short natural-language
summary. No LLM routing, no narrative synthesis — just the space.

Endpoints:

* ``GET /api/conversational/status`` — configuration probe.
* ``POST /api/conversational/message`` — starts a new conversation.
* ``POST /api/conversational/reply`` — sends a follow-up to an existing
  conversation.

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


def _extract_response(message: dict[str, Any]) -> dict[str, Any]:
    """Pull the assistant text, generated SQL, and result rows from a Genie message."""
    text = ""
    sql = ""
    rows: list[list[Any]] = []
    columns: list[str] = []

    for attach in message.get("attachments", []) or []:
        text_block = attach.get("text") or {}
        query_block = attach.get("query") or {}
        if isinstance(text_block, dict) and text_block.get("content"):
            text = (text_block.get("content") or "").strip()
        if isinstance(query_block, dict):
            sql = (query_block.get("query") or "").strip() or sql
            desc = query_block.get("description") or ""
            if desc and not text:
                text = desc

    if not text:
        text = (message.get("content") or "").strip()

    result = message.get("query_result") or {}
    if isinstance(result, dict):
        schema = result.get("schema") or {}
        cols = schema.get("columns") or []
        columns = [str(c.get("name") or "") for c in cols]
        raw_rows = result.get("data_array") or result.get("data") or []
        if isinstance(raw_rows, list):
            rows = raw_rows

    return {
        "text": text,
        "sql": sql,
        "columns": columns,
        "rows": rows,
    }


def _poll_until_ready(w: Any, space_id: str, conv_id: str, msg_id: str) -> dict[str, Any]:
    """Block on Genie until the message finishes or we hit the max wait."""
    deadline = time.monotonic() + _MAX_POLL_S
    while True:
        msg = w.api_client.do(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}",
        )
        status = (msg.get("status") or "").upper()
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            if status != "COMPLETED":
                error = msg.get("error") or {}
                raise HTTPException(
                    status_code=502,
                    detail=(error.get("error") or f"Genie call finished in state {status}"),
                )
            return msg
        if time.monotonic() > deadline:
            raise HTTPException(
                status_code=504,
                detail="Genie response timed out after 90 s",
            )
        time.sleep(_POLL_INTERVAL_S)


@router.get("/status")
async def get_status() -> dict[str, Any]:
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
async def start_conversation(req: MessageRequest) -> dict[str, Any]:
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
        "response": _extract_response(msg),
    }


@router.post("/reply")
async def reply_to_conversation(req: ReplyRequest) -> dict[str, Any]:
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
        "response": _extract_response(msg),
    }
