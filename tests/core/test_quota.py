from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.core import quota


def test_load_settings_returns_none_when_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        with patch.object(Path, "home", return_value=Path(temp_dir)):
            assert quota._load_settings() is None


def test_load_settings_returns_none_for_invalid_json() -> None:
    with TemporaryDirectory() as temp_dir:
        claude_dir = Path(temp_dir) / ".claude"
        claude_dir.mkdir()
        claude_dir.joinpath("settings.json").write_text("{invalid", encoding="utf-8")
        with patch.object(Path, "home", return_value=Path(temp_dir)):
            assert quota._load_settings() is None


def test_load_settings_returns_json_payload() -> None:
    with TemporaryDirectory() as temp_dir:
        claude_dir = Path(temp_dir) / ".claude"
        claude_dir.mkdir()
        expected = {"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}
        claude_dir.joinpath("settings.json").write_text(
            json.dumps(expected), encoding="utf-8"
        )
        with patch.object(Path, "home", return_value=Path(temp_dir)):
            assert quota._load_settings() == expected


def test_check_glm_quota_skips_without_token() -> None:
    with (
        patch.object(quota, "_load_settings", return_value=None),
        patch.object(quota.urllib.request, "urlopen") as urlopen,
    ):
        result = quota.check_glm_quota(logging.getLogger("test"))
        assert result.proceed is True
        urlopen.assert_not_called()


def test_check_glm_quota_returns_proceed_below_threshold() -> None:
    payload = {"data": {"limits": [{"type": "TOKENS_LIMIT", "percentage": 10}]}}
    response = io.StringIO(json.dumps(payload))
    response.__enter__ = lambda self=response: self
    response.__exit__ = lambda *args: False

    with (
        patch.object(
            quota,
            "_load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", return_value=response),
    ):
        result = quota.check_glm_quota(logging.getLogger("test"))
        assert result.proceed is True
        assert result.wait_until_ts is None


def test_check_glm_quota_returns_no_proceed_without_reset_time() -> None:
    payload = {"data": {"limits": [{"type": "TOKENS_LIMIT", "percentage": 90}]}}
    response = io.StringIO(json.dumps(payload))
    response.__enter__ = lambda self=response: self
    response.__exit__ = lambda *args: False

    with (
        patch.object(
            quota,
            "_load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", return_value=response),
    ):
        result = quota.check_glm_quota(logging.getLogger("test"))
        assert result.proceed is False
        assert result.wait_until_ts is None


def test_check_glm_quota_returns_proceed_when_no_tokens_limit_entry() -> None:
    payload = {"data": {"limits": [{"type": "OTHER", "percentage": 90}]}}
    response = io.StringIO(json.dumps(payload))
    response.__enter__ = lambda self=response: self
    response.__exit__ = lambda *args: False

    with (
        patch.object(
            quota,
            "_load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", return_value=response),
    ):
        result = quota.check_glm_quota(logging.getLogger("test"))
        assert result.proceed is True


def test_check_glm_quota_returns_wait_until_ts_when_threshold_exceeded() -> None:
    payload = {
        "data": {
            "limits": [
                {
                    "type": "TOKENS_LIMIT",
                    "percentage": 90,
                    "nextResetTime": 1000,
                }
            ]
        }
    }
    response = io.StringIO(json.dumps(payload))
    mocked_urlopen = MagicMock()
    mocked_urlopen.return_value.__enter__.return_value = response

    with (
        patch.object(
            quota,
            "_load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", mocked_urlopen),
    ):
        result = quota.check_glm_quota(logging.getLogger("test"))

    assert result.proceed is False
    assert result.wait_until_ts == int(1000 / 1000)


def test_wait_for_quota_reset_sleeps_until_ts_reached() -> None:
    logger = logging.getLogger("test")
    wait_until_ts = 5000

    with (
        patch("fa.core.quota.time.time", side_effect=[0, 3000, 6000]),
        patch("fa.core.quota.time.sleep") as sleep_mock,
    ):
        quota.wait_for_quota_reset(wait_until_ts, logger)

    assert sleep_mock.call_count == 2
    sleep_mock.assert_called_with(10)


def test_wait_for_quota_reset_returns_immediately_when_ts_passed() -> None:
    logger = logging.getLogger("test")

    with (
        patch("fa.core.quota.time.time", return_value=9999),
        patch("fa.core.quota.time.sleep") as sleep_mock,
    ):
        quota.wait_for_quota_reset(5000, logger)

    sleep_mock.assert_not_called()


def test_check_glm_quota_and_wait_waits_and_returns_true() -> None:
    logger = logging.getLogger("test")
    wait_ts = 5000

    with patch(
        "fa.core.quota.check_glm_quota", return_value=quota.QuotaResult(False, wait_ts)
    ):
        with patch("fa.core.quota.wait_for_quota_reset") as wait_mock:
            assert quota.check_glm_quota_and_wait(logger) is True
            wait_mock.assert_called_once_with(wait_ts, logger)


def test_check_glm_quota_and_wait_returns_proceed_when_no_wait() -> None:
    logger = logging.getLogger("test")

    with patch(
        "fa.core.quota.check_glm_quota", return_value=quota.QuotaResult(True, None)
    ):
        assert quota.check_glm_quota_and_wait(logger) is True


def test_check_glm_quota_and_wait_returns_false_when_blocked() -> None:
    logger = logging.getLogger("test")

    with patch(
        "fa.core.quota.check_glm_quota", return_value=quota.QuotaResult(False, None)
    ):
        assert quota.check_glm_quota_and_wait(logger) is False


# ─── quota (extended) ──────────────────────────────────────────
def test_check_glm_quota_proceeds_when_quota_check_request_fails() -> None:
    logger = logging.getLogger("test")
    with (
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch("fa.core.quota.urllib.request.urlopen", side_effect=RuntimeError("boom")),
    ):
        assert quota.check_glm_quota(logger).proceed


def test_check_glm_quota_proceeds_when_tokens_limit_is_below_threshold() -> None:
    logger = logging.getLogger("test")
    payload = {"data": {"limits": [{"type": "TOKENS_LIMIT", "percentage": 42}]}}
    response = io.StringIO(json.dumps(payload))
    mocked_urlopen = MagicMock()
    mocked_urlopen.return_value.__enter__.return_value = response

    with (
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", mocked_urlopen),
    ):
        assert quota.check_glm_quota(logger).proceed


def test_check_glm_quota_and_wait_proceeds_when_reset_time_is_past() -> None:
    logger = logging.getLogger("test")
    payload = {
        "data": {
            "limits": [{"type": "TOKENS_LIMIT", "percentage": 80, "nextResetTime": 0}]
        }
    }
    response = io.StringIO(json.dumps(payload))
    mocked_urlopen = MagicMock()
    mocked_urlopen.return_value.__enter__.return_value = response

    with (
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch.object(quota.urllib.request, "urlopen", mocked_urlopen),
        patch("fa.core.quota.wait_for_quota_reset"),
    ):
        assert quota.check_glm_quota_and_wait(logger)
