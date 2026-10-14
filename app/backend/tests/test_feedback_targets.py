"""Customer-safe runtime feedback configuration."""

import asyncio
import time
from unittest.mock import patch

from backend import feedback
from backend.routers import user


def test_feedback_targets_default_to_public_issue_tracker(monkeypatch):
    for name in (
        "COST_OBS_FEEDBACK_GITHUB_URL",
        "COST_OBS_FEEDBACK_EMAIL",
        "COST_OBS_FEEDBACK_SLACK_URL",
        "COST_OBS_FEEDBACK_SLACK_TEAM_ID",
        "COST_OBS_FEEDBACK_SLACK_MEMBER_ID",
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    targets = feedback._feedback_targets_from_env()

    assert targets == {
        "github_issue_url": (
            "https://github.com/smathews13/cost-obs-databricks-v2.0/issues/new"
        ),
        "email_href": None,
        "slack": None,
    }


def test_feedback_targets_accept_valid_optional_destinations(monkeypatch):
    team_id = "T" + ("1" * 8)
    member_id = "U" + ("2" * 8)
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_GITHUB_URL",
        "https://github.com/example/project/issues/new",
    )
    monkeypatch.setenv("COST_OBS_FEEDBACK_EMAIL", "feedback@example.com")
    monkeypatch.setenv("COST_OBS_FEEDBACK_SLACK_TEAM_ID", team_id)
    monkeypatch.setenv("COST_OBS_FEEDBACK_SLACK_MEMBER_ID", member_id)
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
        f"https://example.slack.com/team/{member_id}",
    )

    targets = feedback._feedback_targets_from_env()

    assert targets["email_href"] == (
        "mailto:feedback@example.com?subject=cost-obs%20v2.0%20feedback"
    )
    assert targets["slack"] == {
        "url": f"slack://user?team={team_id}&id={member_id}",
        "fallback_url": f"https://example.slack.com/team/{member_id}",
    }


def test_feedback_targets_accept_direct_deep_link_or_https_profile(monkeypatch):
    team_id = "T" + ("5" * 8)
    member_id = "W" + ("6" * 8)
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_URL",
        f"slack://user?id={member_id}&team={team_id}",
    )
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
        f"https://example.slack.com/team/{member_id}",
    )

    assert feedback._feedback_targets_from_env()["slack"] == {
        "url": f"slack://user?team={team_id}&id={member_id}",
        "fallback_url": f"https://example.slack.com/team/{member_id}",
    }

    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_URL",
        f"https://example.slack.com/team/{member_id}",
    )
    assert feedback._feedback_targets_from_env()["slack"] == {
        "url": f"https://example.slack.com/team/{member_id}",
        "fallback_url": None,
    }


def test_feedback_targets_reject_credentials_and_partial_slack(monkeypatch):
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_GITHUB_URL",
        "https://token:secret@github.com/example/project/issues/new",
    )
    monkeypatch.setenv("COST_OBS_FEEDBACK_EMAIL", "not-an-address")
    monkeypatch.setenv("COST_OBS_FEEDBACK_SLACK_TEAM_ID", "T" + ("3" * 8))
    monkeypatch.setenv("COST_OBS_FEEDBACK_SLACK_MEMBER_ID", "U" + ("4" * 8))
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_URL",
        "javascript:alert(1)",
    )
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
        "https://hooks.slack.com/services/do-not-return-this",
    )

    serialized = repr(feedback._feedback_targets_from_env())

    assert "secret" not in serialized
    assert "hooks.slack.com" not in serialized
    assert "not-an-address" not in serialized
    assert serialized.count("github.com/smathews13/cost-obs-databricks-v2.0/issues/new") == 1


def test_feedback_targets_reject_non_allowlisted_hosts(monkeypatch):
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_GITHUB_URL",
        "https://gitlab.com/example/project/issues/new",
    )
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_URL",
        "https://example.slack.com/archives/C0123456789",
    )
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
        "https://example.com/team/U" + ("2" * 8),
    )

    targets = feedback._feedback_targets_from_env()

    assert targets["github_issue_url"] == (
        "https://github.com/smathews13/cost-obs-databricks-v2.0/issues/new"
    )
    assert targets["slack"] is None
    assert "gitlab.com" not in repr(targets)
    assert "example.com/team" not in repr(targets)


def test_feedback_targets_use_persisted_target_when_env_is_absent(monkeypatch):
    for name in (
        "COST_OBS_FEEDBACK_SLACK_URL",
        "COST_OBS_FEEDBACK_SLACK_TEAM_ID",
        "COST_OBS_FEEDBACK_SLACK_MEMBER_ID",
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    team_id = "T" + ("A" * 8)
    member_id = "U" + ("B" * 8)
    persisted = f"slack://user?team={team_id}&id={member_id}"
    feedback.invalidate_feedback_settings_cache()

    with patch.object(
        feedback,
        "_load_persisted_feedback_slack_url",
        return_value=persisted,
    ):
        targets = asyncio.run(user.get_feedback_targets())

    assert targets["slack"] == {"url": persisted, "fallback_url": None}


def test_persisted_feedback_target_uses_single_entry_cache(monkeypatch):
    for name in (
        "COST_OBS_FEEDBACK_SLACK_URL",
        "COST_OBS_FEEDBACK_SLACK_TEAM_ID",
        "COST_OBS_FEEDBACK_SLACK_MEMBER_ID",
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    member_id = "U" + ("P" * 8)
    persisted = f"https://workspace.slack.com/team/{member_id}"
    feedback.invalidate_feedback_settings_cache()

    with patch(
        "backend.db.lb_get_config",
        return_value={"feedback_slack_url": persisted},
    ) as load_settings:
        first = asyncio.run(user.get_feedback_targets())
        second = asyncio.run(user.get_feedback_targets())

    assert first == second
    assert first["slack"] == {"url": persisted, "fallback_url": None}
    assert load_settings.call_count == 1
    assert feedback._feedback_settings_cache.maxsize == 1
    assert feedback._feedback_settings_cache.currsize == 1


def test_feedback_targets_prefer_validated_env_over_persisted(monkeypatch):
    env_member_id = "W" + ("C" * 8)
    persisted_member_id = "U" + ("D" * 8)
    env_url = f"https://workspace.slack.com/team/{env_member_id}"
    persisted_url = f"https://workspace.slack.com/team/{persisted_member_id}"
    monkeypatch.setenv("COST_OBS_FEEDBACK_SLACK_URL", env_url)
    feedback.invalidate_feedback_settings_cache()

    with patch.object(
        feedback,
        "_load_persisted_feedback_slack_url",
        return_value=persisted_url,
    ) as load_persisted:
        targets = asyncio.run(user.get_feedback_targets())

    assert targets["slack"] == {"url": env_url, "fallback_url": None}
    assert persisted_member_id not in repr(targets)
    load_persisted.assert_not_called()


def test_feedback_targets_timeout_keeps_fast_public_targets(monkeypatch):
    for name in (
        "COST_OBS_FEEDBACK_SLACK_URL",
        "COST_OBS_FEEDBACK_SLACK_TEAM_ID",
        "COST_OBS_FEEDBACK_SLACK_MEMBER_ID",
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "COST_OBS_FEEDBACK_GITHUB_URL",
        "https://github.com/example/project/issues/new",
    )
    monkeypatch.setenv("COST_OBS_FEEDBACK_EMAIL", "feedback@example.com")
    monkeypatch.setattr(feedback, "_FEEDBACK_SETTINGS_TIMEOUT_SECONDS", 0.01)
    feedback.invalidate_feedback_settings_cache()

    def slow_load():
        time.sleep(0.08)
        return None

    async def invoke():
        started = time.monotonic()
        targets = await user.get_feedback_targets()
        return targets, time.monotonic() - started

    with patch.object(feedback, "_load_persisted_feedback_slack_url", side_effect=slow_load):
        targets, elapsed = asyncio.run(invoke())

    assert elapsed < 0.06
    assert targets["github_issue_url"] == "https://github.com/example/project/issues/new"
    assert targets["email_href"].startswith("mailto:feedback@example.com")
    assert targets["slack"] is None


def test_feedback_targets_never_expose_persisted_webhook(monkeypatch):
    for name in (
        "COST_OBS_FEEDBACK_SLACK_URL",
        "COST_OBS_FEEDBACK_SLACK_TEAM_ID",
        "COST_OBS_FEEDBACK_SLACK_MEMBER_ID",
        "COST_OBS_FEEDBACK_SLACK_WEB_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    feedback.invalidate_feedback_settings_cache()
    webhook_url = "https://hooks.slack.com/services/" + "synthetic-secret"

    with patch.object(
        feedback,
        "_load_persisted_feedback_slack_url",
        return_value=webhook_url,
    ):
        targets = asyncio.run(user.get_feedback_targets())

    assert targets["slack"] is None
    assert "hooks.slack.com" not in repr(targets)
    assert "synthetic-secret" not in repr(targets)
