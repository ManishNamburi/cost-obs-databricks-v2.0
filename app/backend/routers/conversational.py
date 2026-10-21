"""
Conversational surface — Genie-backed chat for the whole app.

Thin wrapper over the Databricks Genie SDK (`WorkspaceClient.genie`). Every
user prompt is sent to the configured Genie space (`GENIE_SPACE_ID`). The
response is returned with the generated SQL, the row set, and a short
natural-language summary.

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
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import get_user_workspace_client, lb_get_config

router = APIRouter()
logger = logging.getLogger(__name__)

_WAIT = timedelta(seconds=90)
_TERMINAL_OK = {"COMPLETED", "QUERY_RESULT_EXPIRED"}
_TERMINAL_FAIL = {"FAILED", "CANCELLED"}


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ReplyRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=4000)


def configured_space_id() -> str:
    """Bundle env first; Lakebase next (setup job writes the ID when it creates the space)."""
    sid = (os.environ.get("GENIE_SPACE_ID") or "").strip()
    if sid:
        return sid
    cfg = lb_get_config("genie_space_id")
    if isinstance(cfg, dict):
        return str(cfg.get("space_id") or "").strip()
    if isinstance(cfg, str):
        return cfg.strip()
    return ""


def _space_id() -> str:
    sid = configured_space_id()
    if not sid:
        raise HTTPException(
            status_code=503,
            detail=(
                "Conversational surface is not configured yet. The setup job "
                "creates the Genie space on deploy; wait for that step or set "
                "GENIE_SPACE_ID in the bundle."
            ),
        )
    return sid


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


def _status_value(status: Any) -> str:
    if status is None:
        return ""
    return str(getattr(status, "value", status) or "").upper()


def _raise_if_failed(message: Any) -> None:
    status = _status_value(getattr(message, "status", None) or _as_dict(message).get("status"))
    if status in _TERMINAL_FAIL:
        error = getattr(message, "error", None)
        err_dict = _as_dict(error)
        raise HTTPException(
            status_code=502,
            detail=(err_dict.get("error") or err_dict.get("message") or f"Genie call finished in state {status}"),
        )


def _fetch_query_result(
    w: Any, space_id: str, conv_id: str, msg_id: str, attachment_id: str | None
) -> tuple[list[str], list[list[Any]]]:
    genie = w.genie
    attempts: list[tuple[str, Any]] = []
    if attachment_id:
        attempts.append(
            (
                "attachment",
                lambda: genie.get_message_attachment_query_result(
                    space_id, conv_id, msg_id, attachment_id
                ),
            )
        )
        by_attach = getattr(genie, "get_message_query_result_by_attachment", None)
        if callable(by_attach):
            attempts.append(("by_attachment", lambda: by_attach(space_id, conv_id, msg_id, attachment_id)))
    attempts.append(("message", lambda: genie.get_message_query_result(space_id, conv_id, msg_id)))

    for label, fetch in attempts:
        try:
            resp = fetch()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[conversational] query-result %s failed: %s", label, exc)
            continue
        data = _as_dict(resp)
        stmt = data.get("statement_response") or {}
        if not stmt and getattr(resp, "statement_response", None) is not None:
            stmt = _as_dict(resp.statement_response)
        manifest = stmt.get("manifest") or {}
        schema = manifest.get("schema") or {}
        columns = [str(c.get("name") or "") for c in (schema.get("columns") or [])]
        result = stmt.get("result") or {}
        raw_rows = result.get("data_array")
        rows = raw_rows if isinstance(raw_rows, list) else []
        if columns or rows:
            return columns, rows
    return [], []


def _build_response(w: Any, space_id: str, conv_id: str, msg_id: str, message: Any) -> dict[str, Any]:
    """Assemble {text, sql, columns, rows} from a completed Genie message."""
    text = ""
    sql = ""
    attachment_id: str | None = None
    data = _as_dict(message)
    attachments = getattr(message, "attachments", None) or data.get("attachments") or []

    for attach in attachments:
        attach_data = _as_dict(attach)
        text_block = attach_data.get("text") or _as_dict(getattr(attach, "text", None))
        query_block = attach_data.get("query") or _as_dict(getattr(attach, "query", None))
        if isinstance(text_block, dict) and text_block.get("content"):
            text = (text_block.get("content") or "").strip()
        if isinstance(query_block, dict) and (query_block.get("query") or "").strip():
            sql = (query_block.get("query") or "").strip()
            attachment_id = (
                attach_data.get("attachment_id")
                or getattr(attach, "attachment_id", None)
                or query_block.get("id")
                or attachment_id
            )
            if not text:
                text = (query_block.get("description") or query_block.get("title") or "").strip()

    if not text:
        text = (data.get("content") or getattr(message, "content", None) or "").strip()

    columns: list[str] = []
    rows: list[list[Any]] = []
    status = _status_value(getattr(message, "status", None) or data.get("status"))
    if sql and status != "QUERY_RESULT_EXPIRED":
        columns, rows = _fetch_query_result(w, space_id, conv_id, msg_id, attachment_id)

    return {"text": text, "sql": sql, "columns": columns, "rows": rows}


@router.get("/status")
def get_status() -> dict[str, Any]:
    """Report whether the conversational surface can serve requests."""
    space_id = configured_space_id()
    if not space_id:
        return {
            "configured": False,
            "reason": "Genie space is not set yet. The setup job creates it on deploy.",
        }

    try:
        w = get_user_workspace_client()
        space = w.genie.get_space(space_id)
        title = getattr(space, "title", None) or _as_dict(space).get("title")
        return {"configured": True, "space_id": space_id, "title": title}
    except Exception as exc:  # noqa: BLE001 — surface reason to UI
        logger.warning("[conversational] Genie space probe failed: %s", exc)
        return {"configured": False, "reason": str(exc)}


@router.post("/message")
def start_conversation(req: MessageRequest) -> dict[str, Any]:
    """Open a new Genie conversation with the user's first message."""
    space_id = _space_id()
    w = get_user_workspace_client()
    try:
        msg = w.genie.start_conversation_and_wait(space_id, req.message, timeout=_WAIT)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("[conversational] start_conversation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _raise_if_failed(msg)
    conv_id = str(getattr(msg, "conversation_id", None) or _as_dict(msg).get("conversation_id") or "")
    msg_id = str(getattr(msg, "message_id", None) or getattr(msg, "id", None) or _as_dict(msg).get("message_id") or "")
    if not conv_id or not msg_id:
        raise HTTPException(status_code=502, detail="Genie did not return conversation/message IDs")
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
    try:
        msg = w.genie.create_message_and_wait(
            space_id, req.conversation_id, req.message, timeout=_WAIT
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("[conversational] create_message failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _raise_if_failed(msg)
    msg_id = str(getattr(msg, "message_id", None) or getattr(msg, "id", None) or _as_dict(msg).get("message_id") or "")
    if not msg_id:
        raise HTTPException(status_code=502, detail="Genie did not return a message ID")
    return {
        "conversation_id": req.conversation_id,
        "message_id": msg_id,
        "response": _build_response(w, space_id, req.conversation_id, msg_id, msg),
    }
