"""Validation and normalization for customer-safe feedback destinations."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from cachetools import TTLCache

logger = logging.getLogger(__name__)

_SLACK_TEAM_PATTERN = re.compile(r"^T[A-Z0-9]{8,15}$")
_SLACK_MEMBER_PATTERN = re.compile(r"^[UW][A-Z0-9]{8,15}$")
_SLACK_PROFILE_PATH_PATTERN = re.compile(r"^/team/([UW][A-Z0-9]{8,15})/?$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DEFAULT_FEEDBACK_ISSUE_URL = (
    "https://github.com/smathews13/cost-obs-databricks-v2.0/issues/new"
)
# This lookup runs independently of dashboard loading. Allow one Lakebase-backed
# settings read to finish so the first menu open after a deploy does not omit a
# configured Slack destination and then remain stale for the whole browser session.
_FEEDBACK_SETTINGS_TIMEOUT_SECONDS = 15.0
_feedback_settings_cache: TTLCache[str, str | None] = TTLCache(maxsize=1, ttl=30)
_feedback_settings_cache_lock = threading.Lock()
_feedback_settings_load_lock = threading.Lock()
_feedback_settings_generation = 0


def safe_https_url(value: str, *, host: str | None = None) -> str | None:
    """Return a credential-free HTTPS URL without query or fragment data."""
    candidate = value.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return None
    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or port is not None
        or parsed.query
        or parsed.fragment
        or (host and parsed.hostname != host)
    ):
        return None
    return candidate


def safe_slack_profile_url(value: str) -> str | None:
    """Return an HTTPS Slack member profile URL, never a webhook or token URL."""
    candidate = safe_https_url(value)
    if not candidate:
        return None
    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").lower()
    match = _SLACK_PROFILE_PATH_PATTERN.fullmatch(parsed.path)
    if (
        not hostname.endswith(".slack.com")
        or hostname == "hooks.slack.com"
        or match is None
        or not _SLACK_MEMBER_PATTERN.fullmatch(match.group(1))
    ):
        return None
    return candidate.removesuffix("/")


def safe_slack_deep_link(value: str) -> str | None:
    """Return a canonical Slack user deep link with complete, valid IDs."""
    candidate = value.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return None
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "slack"
        or parsed.netloc != "user"
        or parsed.path not in ("", "/")
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return None
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    if set(query) != {"team", "id"}:
        return None
    team_id = query["team"]
    member_id = query["id"]
    if (
        len(team_id) != 1
        or len(member_id) != 1
        or not _SLACK_TEAM_PATTERN.fullmatch(team_id[0])
        or not _SLACK_MEMBER_PATTERN.fullmatch(member_id[0])
    ):
        return None
    return f"slack://user?{urlencode({'team': team_id[0], 'id': member_id[0]})}"


def safe_feedback_slack_url(value: str) -> str | None:
    """Validate either supported Slack feedback target and normalize it."""
    return safe_slack_deep_link(value) or safe_slack_profile_url(value)


def safe_slack_ids_target(team_id: str, member_id: str) -> str | None:
    """Build a deep link only when both legacy split IDs are complete."""
    if (
        not _SLACK_TEAM_PATTERN.fullmatch(team_id)
        or not _SLACK_MEMBER_PATTERN.fullmatch(member_id)
    ):
        return None
    return f"slack://user?{urlencode({'team': team_id, 'id': member_id})}"


def _feedback_targets_from_env(
    persisted_slack_url: str | None = None,
) -> dict[str, Any]:
    """Return safe feedback targets, preferring runtime environment values."""
    configured_issue_url = safe_https_url(
        os.getenv("COST_OBS_FEEDBACK_GITHUB_URL", ""),
        host="github.com",
    )
    email = os.getenv("COST_OBS_FEEDBACK_EMAIL", "").strip()
    email_href = (
        f"mailto:{email}?subject={quote('cost-obs v2.0 feedback')}"
        if _EMAIL_PATTERN.fullmatch(email)
        else None
    )

    team_id = os.getenv("COST_OBS_FEEDBACK_SLACK_TEAM_ID", "").strip()
    member_id = os.getenv("COST_OBS_FEEDBACK_SLACK_MEMBER_ID", "").strip()
    slack_web_url = safe_slack_profile_url(
        os.getenv("COST_OBS_FEEDBACK_SLACK_WEB_URL", "")
    )
    configured_slack_url = os.getenv("COST_OBS_FEEDBACK_SLACK_URL", "")
    slack_deep_link = safe_slack_deep_link(configured_slack_url)
    configured_slack_web_url = safe_slack_profile_url(configured_slack_url)
    legacy_slack_deep_link = safe_slack_ids_target(team_id, member_id)
    slack = None
    if slack_deep_link:
        slack = {
            "url": slack_deep_link,
            "fallback_url": slack_web_url,
        }
    elif configured_slack_web_url:
        slack = {
            "url": configured_slack_web_url,
            "fallback_url": None,
        }
    elif legacy_slack_deep_link:
        slack = {
            "url": legacy_slack_deep_link,
            "fallback_url": slack_web_url,
        }
    elif slack_web_url:
        slack = {
            "url": slack_web_url,
            "fallback_url": None,
        }
    else:
        runtime_slack_url = (
            safe_feedback_slack_url(persisted_slack_url)
            if isinstance(persisted_slack_url, str)
            else None
        )
        if runtime_slack_url:
            slack = {
                "url": runtime_slack_url,
                "fallback_url": None,
            }

    return {
        "github_issue_url": configured_issue_url or _DEFAULT_FEEDBACK_ISSUE_URL,
        "email_href": email_href,
        "slack": slack,
    }


def invalidate_feedback_settings_cache() -> None:
    """Clear the bounded runtime target cache after an admin settings save."""
    global _feedback_settings_generation
    with _feedback_settings_cache_lock:
        _feedback_settings_generation += 1
        _feedback_settings_cache.clear()


def _slack_url_from_settings(settings: object) -> str | None:
    if not isinstance(settings, dict):
        return None
    raw_url = settings.get("feedback_slack_url")
    return safe_feedback_slack_url(raw_url) if isinstance(raw_url, str) else None


def _load_persisted_feedback_slack_url() -> str | None:
    """Read and validate the durable target without allowing duplicate hung loads."""
    with _feedback_settings_cache_lock:
        if "slack_url" in _feedback_settings_cache:
            return _feedback_settings_cache["slack_url"]
        generation = _feedback_settings_generation

    if not _feedback_settings_load_lock.acquire(blocking=False):
        return None
    try:
        slack_url: str | None = None
        loaded = False
        try:
            from backend.db import lb_get_config

            cfg = lb_get_config("app_settings")
            if isinstance(cfg, dict) and cfg:
                slack_url = _slack_url_from_settings(cfg)
                loaded = True
        except Exception:
            logger.warning("Could not load durable feedback target from Lakebase")

        if not loaded:
            try:
                from backend.routers.settings import get_app_settings

                slack_url = _slack_url_from_settings(get_app_settings())
            except Exception:
                logger.warning("Could not load durable feedback target")
                slack_url = None

        with _feedback_settings_cache_lock:
            if generation == _feedback_settings_generation:
                _feedback_settings_cache["slack_url"] = slack_url
        return slack_url
    finally:
        _feedback_settings_load_lock.release()


async def _persisted_feedback_slack_url() -> str | None:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_load_persisted_feedback_slack_url),
            timeout=_FEEDBACK_SETTINGS_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("Durable feedback target lookup timed out")
        return None


async def resolve_feedback_targets() -> dict[str, Any]:
    """Expose customer-safe feedback links configured at app runtime."""
    env_targets = _feedback_targets_from_env()
    if env_targets["slack"]:
        return env_targets
    persisted_slack_url = await _persisted_feedback_slack_url()
    return _feedback_targets_from_env(persisted_slack_url)
