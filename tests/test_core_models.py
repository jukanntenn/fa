from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from fa.core.project import ensure_fa_structure, find_project_root
from fa.core.quota import (
    QuotaResult,
    _load_settings,
    check_glm_quota,
    check_glm_quota_and_wait,
)
from fa.task.model import InvalidTransition, Task


def test_find_project_root_prefers_nearest_fa_directory() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        nested = root / "workspace" / "feature"
        (root / ".fa").mkdir()
        nested.mkdir(parents=True)

        assert find_project_root(nested) == root


def test_find_project_root_returns_git_root_when_fa_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        nested = root / "workspace" / "feature"
        (root / ".git").mkdir()
        nested.mkdir(parents=True)

        assert find_project_root(nested) == root


def test_find_project_root_returns_start_when_no_markers_exist() -> None:
    with TemporaryDirectory() as temp_dir:
        start = Path(temp_dir) / "workspace" / "feature"
        start.mkdir(parents=True)

        original_is_dir = Path.is_dir

        def marker_free_is_dir(path: Path) -> bool:
            if path.name in {".fa", ".git"}:
                return False
            return original_is_dir(path)

        with patch.object(Path, "is_dir", marker_free_is_dir):
            assert find_project_root(start) == start.resolve()


def test_ensure_fa_structure_creates_expected_directories() -> None:
    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)

        fa_dir = ensure_fa_structure(project_root)

        assert fa_dir == project_root / ".fa"
        assert (fa_dir / "tasks" / "archive").is_dir()
        assert (fa_dir / "logs" / "agents").is_dir()
        assert (fa_dir / "policies").is_dir()
        assert (fa_dir / "templates").is_dir()


def test_from_dict_normalizes_pending_status_alias() -> None:
    task = Task.from_dict(
        {
            "id": 7,
            "slug": "demo-task",
            "parent_id": 3,
            "status": "pending",
            "depends_on": [1, 2],
            "related_to": [4],
            "created_at": "2026-05-13T12:00:00",
            "completed_at": None,
        },
        Path("/tmp/task"),
    )

    assert task.status == "draft"
    assert task.depends_on == [1, 2]
    assert task.related_to == [4]
    assert task.parent_id == 3
    assert task.path == Path("/tmp/task")


def test_from_dict_defaults_missing_optional_relationship_fields() -> None:
    task = Task.from_dict(
        {
            "id": 11,
            "slug": "defaults",
            "created_at": "2026-05-13T12:00:00",
        },
        Path("/tmp/defaults"),
    )

    assert task.parent_id is None
    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []
    assert task.completed_at is None


def test_to_dict_round_trips_serializable_fields() -> None:
    task = Task(
        id=9,
        slug="round-trip",
        parent_id=None,
        status="running",
        depends_on=[1],
        related_to=[2],
        created_at="2026-05-13T12:00:00",
        completed_at="2026-05-13T13:00:00",
        path=Path("/tmp/task"),
    )

    assert task.to_dict() == {
        "id": 9,
        "slug": "round-trip",
        "parent_id": None,
        "status": "running",
        "depends_on": [1],
        "related_to": [2],
        "created_at": "2026-05-13T12:00:00",
        "completed_at": "2026-05-13T13:00:00",
    }


def test_transition_to_updates_status_for_valid_transition() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    task.transition_to("approved")
    task.transition_to("running")
    task.transition_to("completed")

    assert task.status == "completed"


def test_transition_to_rejects_unknown_status() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    with pytest.raises(ValueError, match="unknown status: unknown"):
        task.transition_to("unknown")


def test_transition_to_rejects_invalid_transition() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    with pytest.raises(InvalidTransition) as exc_info:
        task.transition_to("running")

    assert exc_info.value.current == "draft"
    assert exc_info.value.target == "running"


def test_new_creates_draft_task_with_empty_relationships() -> None:
    task = Task.new(5, "new-task", 2, Path("/tmp/task"))

    assert task.id == 5
    assert task.slug == "new-task"
    assert task.parent_id == 2
    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []
    assert task.completed_at is None
    assert task.path == Path("/tmp/task")


def test_load_settings_returns_none_when_settings_file_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        with patch("fa.core.quota.Path.home", return_value=home):
            assert _load_settings() is None


def test_load_settings_returns_none_when_settings_json_invalid() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        settings_dir = home / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{invalid", encoding="utf-8")

        with patch("fa.core.quota.Path.home", return_value=home):
            assert _load_settings() is None


def test_load_settings_returns_parsed_settings_when_json_valid() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        settings_dir = home / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(
            '{"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}',
            encoding="utf-8",
        )

        with patch("fa.core.quota.Path.home", return_value=home):
            assert _load_settings() == {"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}


def test_check_glm_quota_skips_when_token_missing() -> None:
    logger = logging.getLogger("test")
    with patch("fa.core.quota._load_settings", return_value=None):
        assert check_glm_quota(logger).proceed


def test_check_glm_quota_proceeds_when_quota_check_request_fails() -> None:
    logger = logging.getLogger("test")
    with (
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch("fa.core.quota.urllib.request.urlopen", side_effect=RuntimeError("boom")),
    ):
        assert check_glm_quota(logger).proceed


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
        patch("fa.core.quota.urllib.request.urlopen", mocked_urlopen),
    ):
        assert check_glm_quota(logger).proceed


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
        patch("fa.core.quota.urllib.request.urlopen", mocked_urlopen),
        patch("fa.core.quota.wait_for_quota_reset"),
    ):
        assert check_glm_quota_and_wait(logger)


def test_check_glm_quota_returns_wait_ts_when_threshold_exceeded() -> None:
    logger = logging.getLogger("test")
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
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch("fa.core.quota.urllib.request.urlopen", mocked_urlopen),
    ):
        result = check_glm_quota(logger)

    expected_ts = int(1000 / 1000) + 1800
    assert result == QuotaResult(False, expected_ts)


def test_check_glm_quota_and_wait_waits_and_returns_true() -> None:
    logger = logging.getLogger("test")
    wait_ts = int(1000 / 1000) + 1800

    with (
        patch(
            "fa.core.quota.check_glm_quota", return_value=QuotaResult(False, wait_ts)
        ),
        patch("fa.core.quota.wait_for_quota_reset") as wait_mock,
    ):
        assert check_glm_quota_and_wait(logger) is True
        wait_mock.assert_called_once_with(wait_ts, logger)


def test_check_glm_quota_proceeds_when_no_tokens_limit_entry_exists() -> None:
    logger = logging.getLogger("test")
    payload = {"data": {"limits": [{"type": "REQUESTS_LIMIT", "percentage": 99}]}}
    response = io.StringIO(json.dumps(payload))
    mocked_urlopen = MagicMock()
    mocked_urlopen.return_value.__enter__.return_value = response

    with (
        patch(
            "fa.core.quota._load_settings",
            return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
        ),
        patch("fa.core.quota.urllib.request.urlopen", mocked_urlopen),
    ):
        assert check_glm_quota(logger).proceed
