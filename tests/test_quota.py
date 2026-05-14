from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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
        assert quota.check_glm_quota(logging.getLogger("test"))
        urlopen.assert_not_called()


def test_check_glm_quota_returns_true_below_threshold() -> None:
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
        assert quota.check_glm_quota(logging.getLogger("test"))


def test_check_glm_quota_returns_false_without_reset_time() -> None:
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
        assert not quota.check_glm_quota(logging.getLogger("test"))


def test_check_glm_quota_returns_true_when_no_tokens_limit_entry() -> None:
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
        assert quota.check_glm_quota(logging.getLogger("test"))
