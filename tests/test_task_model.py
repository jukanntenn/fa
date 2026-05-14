import unittest
from datetime import datetime
from pathlib import Path

from fa.task.model import InvalidTransition, Task


class TaskModelSerializationTests(unittest.TestCase):
    def test_from_dict_normalizes_status_alias(self) -> None:
        task = Task.from_dict(
            {
                "id": 1,
                "slug": "demo",
                "status": "pending",
                "created_at": "2026-05-13T00:00:00",
            },
            Path("/tmp/task"),
        )

        self.assertEqual(task.status, "draft")
        self.assertEqual(task.depends_on, [])
        self.assertEqual(task.related_to, [])

    def test_to_dict_excludes_path(self) -> None:
        task = Task(
            id=1,
            slug="demo",
            parent_id=None,
            status="draft",
            depends_on=[2],
            related_to=[3],
            created_at="2026-05-13T00:00:00",
            completed_at=None,
            path=Path("/tmp/task"),
        )

        self.assertEqual(
            task.to_dict(),
            {
                "id": 1,
                "slug": "demo",
                "parent_id": None,
                "status": "draft",
                "depends_on": [2],
                "related_to": [3],
                "created_at": "2026-05-13T00:00:00",
                "completed_at": None,
            },
        )
        self.assertNotIn("path", task.to_dict())

    def test_new_uses_draft_defaults_and_timestamp_format(self) -> None:
        task = Task.new(7, "demo", None, Path("/tmp/task"))

        self.assertEqual(task.status, "draft")
        self.assertEqual(task.depends_on, [])
        self.assertEqual(task.related_to, [])
        datetime.strptime(task.created_at, "%Y-%m-%dT%H:%M:%S")


class TaskModelTransitionTests(unittest.TestCase):
    def test_transition_to_accepts_valid_transition(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        task.transition_to("approved")

        self.assertEqual(task.status, "approved")

    def test_transition_to_rejects_invalid_transition(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        with self.assertRaises(InvalidTransition):
            task.transition_to("completed")

    def test_transition_to_rejects_unknown_status(self) -> None:
        task = Task.new(1, "demo", None, Path("/tmp/task"))

        with self.assertRaises(ValueError):
            task.transition_to("unknown")


if __name__ == "__main__":
    unittest.main()
