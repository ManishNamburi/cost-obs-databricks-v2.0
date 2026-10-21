from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.routers import conversational


def test_start_conversation_uses_genie_sdk(monkeypatch):
    monkeypatch.setenv("GENIE_SPACE_ID", "space-1")
    msg = SimpleNamespace(
        conversation_id="c1",
        message_id="m1",
        id="m1",
        content="hello",
        status="COMPLETED",
        attachments=[],
        error=None,
    )
    w = MagicMock()
    w.genie.start_conversation_and_wait.return_value = msg
    w.genie.get_message_query_result.side_effect = Exception("no rows")
    with patch("backend.routers.conversational.get_user_workspace_client", return_value=w):
        result = conversational.start_conversation(conversational.MessageRequest(message="what is spend"))
    w.genie.start_conversation_and_wait.assert_called_once()
    assert result["conversation_id"] == "c1"
    assert result["response"]["text"] == "hello"


def test_status_uses_get_space(monkeypatch):
    monkeypatch.setenv("GENIE_SPACE_ID", "space-1")
    space = SimpleNamespace(title="Cost Obs")
    w = MagicMock()
    w.genie.get_space.return_value = space
    with patch("backend.routers.conversational.get_user_workspace_client", return_value=w):
        result = conversational.get_status()
    w.genie.get_space.assert_called_once_with("space-1")
    assert result == {"configured": True, "space_id": "space-1", "title": "Cost Obs"}
