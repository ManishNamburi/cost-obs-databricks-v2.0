from unittest.mock import patch

from backend.routers.conversational import configured_space_id


def test_configured_space_id_prefers_env(monkeypatch):
    monkeypatch.setenv("GENIE_SPACE_ID", "env-space")
    with patch("backend.routers.conversational.lb_get_config", return_value={"space_id": "lb-space"}):
        assert configured_space_id() == "env-space"


def test_configured_space_id_falls_back_to_lakebase(monkeypatch):
    monkeypatch.delenv("GENIE_SPACE_ID", raising=False)
    with patch("backend.routers.conversational.lb_get_config", return_value={"space_id": "lb-space"}):
        assert configured_space_id() == "lb-space"


def test_configured_space_id_empty_when_unset(monkeypatch):
    monkeypatch.delenv("GENIE_SPACE_ID", raising=False)
    with patch("backend.routers.conversational.lb_get_config", return_value=None):
        assert configured_space_id() == ""
