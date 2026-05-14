from __future__ import annotations

import io
import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.core.project import ensure_fa_structure, find_project_root
from fa.core.quota import _load_settings, check_glm_quota
from fa.task.model import InvalidTransition, Task


class ProjectHelpersTests(unittest.TestCase):
    def test_find_project_root_prefers_nearest_fa_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "workspace" / "feature"
            (root / ".fa").mkdir()
            nested.mkdir(parents=True)

            self.assertEqual(find_project_root(nested), root)

    def test_find_project_root_returns_git_root_when_fa_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "workspace" / "feature"
            (root / ".git").mkdir()
            nested.mkdir(parents=True)

            self.assertEqual(find_project_root(nested), root)

    def test_find_project_root_returns_start_when_no_markers_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            start = Path(temp_dir) / "workspace" / "feature"
            start.mkdir(parents=True)

            original_is_dir = Path.is_dir

            def marker_free_is_dir(path: Path) -> bool:
                if path.name in {".fa", ".git"}:
                    return False
                return original_is_dir(path)

            with patch.object(Path, "is_dir", marker_free_is_dir):
                self.assertEqual(find_project_root(start), start.resolve())

    def test_ensure_fa_structure_creates_expected_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            fa_dir = ensure_fa_structure(project_root)

            self.assertEqual(fa_dir, project_root / ".fa")
            self.assertTrue((fa_dir / "tasks" / "archive").is_dir())
            self.assertTrue((fa_dir / "logs" / "agents").is_dir())
            self.assertTrue((fa_dir / "policies").is_dir())
            self.assertTrue((fa_dir / "templates").is_dir())


class TaskModelTests(unittest.TestCase):
    def test_from_dict_normalizes_pending_status_alias(self) -> None:
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

        self.assertEqual(task.status, "draft")
        self.assertEqual(task.depends_on, [1, 2])
        self.assertEqual(task.related_to, [4])
        self.assertEqual(task.parent_id, 3)
        self.assertEqual(task.path, Path("/tmp/task"))

    def test_from_dict_defaults_missing_optional_relationship_fields(self) -> None:
        task = Task.from_dict(
            {
                "id": 11,
                "slug": "defaults",
                "created_at": "2026-05-13T12:00:00",
            },
            Path("/tmp/defaults"),
        )

        self.assertIsNone(task.parent_id)
        self.assertEqual(task.status, "draft")
        self.assertEqual(task.depends_on, [])
        self.assertEqual(task.related_to, [])
        self.assertIsNone(task.completed_at)

    def test_to_dict_round_trips_serializable_fields(self) -> None:
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

        self.assertEqual(
            task.to_dict(),
            {
                "id": 9,
                "slug": "round-trip",
                "parent_id": None,
                "status": "running",
                "depends_on": [1],
                "related_to": [2],
                "created_at": "2026-05-13T12:00:00",
                "completed_at": "2026-05-13T13:00:00",
            },
        )

    def test_transition_to_updates_status_for_valid_transition(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        task.transition_to("approved")
        task.transition_to("running")
        task.transition_to("completed")

        self.assertEqual(task.status, "completed")

    def test_transition_to_rejects_unknown_status(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        with self.assertRaisesRegex(ValueError, "unknown status: unknown"):
            task.transition_to("unknown")

    def test_transition_to_rejects_invalid_transition(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        with self.assertRaises(InvalidTransition) as context:
            task.transition_to("running")

        self.assertEqual(context.exception.current, "draft")
        self.assertEqual(context.exception.target, "running")

    def test_new_creates_draft_task_with_empty_relationships(self) -> None:
        task = Task.new(5, "new-task", 2, Path("/tmp/task"))

        self.assertEqual(task.id, 5)
        self.assertEqual(task.slug, "new-task")
        self.assertEqual(task.parent_id, 2)
        self.assertEqual(task.status, "draft")
        self.assertEqual(task.depends_on, [])
        self.assertEqual(task.related_to, [])
        self.assertIsNone(task.completed_at)
        self.assertEqual(task.path, Path("/tmp/task"))


class LoadSettingsTests(unittest.TestCase):
    def test_returns_none_when_settings_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with patch("fa.core.quota.Path.home", return_value=home):
                self.assertIsNone(_load_settings())

    def test_returns_none_when_settings_json_invalid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            settings_dir = home / ".claude"
            settings_dir.mkdir()
            (settings_dir / "settings.json").write_text("{invalid", encoding="utf-8")

            with patch("fa.core.quota.Path.home", return_value=home):
                self.assertIsNone(_load_settings())

    def test_returns_parsed_settings_when_json_valid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            settings_dir = home / ".claude"
            settings_dir.mkdir()
            (settings_dir / "settings.json").write_text(
                '{"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}',
                encoding="utf-8",
            )

            with patch("fa.core.quota.Path.home", return_value=home):
                self.assertEqual(
                    _load_settings(), {"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}
                )


class CheckGlmQuotaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test")

    def test_skips_when_token_missing(self) -> None:
        with patch("fa.core.quota._load_settings", return_value=None):
            self.assertTrue(check_glm_quota(self.logger))

    def test_proceeds_when_quota_check_request_fails(self) -> None:
        with (
            patch(
                "fa.core.quota._load_settings",
                return_value={"env": {"ANTHROPIC_AUTH_TOKEN": "token"}},
            ),
            patch(
                "fa.core.quota.urllib.request.urlopen",
                side_effect=RuntimeError("boom"),
            ),
        ):
            self.assertTrue(check_glm_quota(self.logger))

    def test_proceeds_when_tokens_limit_is_below_threshold(self) -> None:
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
            self.assertTrue(check_glm_quota(self.logger))

    def test_proceeds_when_tokens_limit_has_no_reset_time(self) -> None:
        payload = {
            "data": {
                "limits": [
                    {"type": "TOKENS_LIMIT", "percentage": 80, "nextResetTime": 0}
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
            self.assertTrue(check_glm_quota(self.logger))

    def test_waits_until_reset_with_buffer_when_threshold_exceeded(self) -> None:
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
            patch("fa.core.quota.time.time", side_effect=[0, 5000]),
            patch("fa.core.quota.time.sleep") as sleep_mock,
        ):
            self.assertTrue(check_glm_quota(self.logger))

        sleep_mock.assert_called_once_with(10)

    def test_proceeds_when_no_tokens_limit_entry_exists(self) -> None:
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
            self.assertTrue(check_glm_quota(self.logger))
