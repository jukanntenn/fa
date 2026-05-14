from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from typer.testing import CliRunner

from fa.cli import app
from fa.task import storage


class TaskStorageIdAllocationTests(unittest.TestCase):
    def test_child_ids_use_lowest_available_ids_after_parent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                parent = storage.create_task("parent")
                child_one = storage.create_task("child-one", parent.id)
                child_two = storage.create_task("child-two", parent.id)
                child_three = storage.create_task("child-three", parent.id)

        self.assertEqual(parent.id, 1)
        self.assertEqual([child_one.id, child_two.id, child_three.id], [2, 3, 4])
        self.assertEqual(
            [child_one.parent_id, child_two.parent_id, child_three.parent_id],
            [parent.id, parent.id, parent.id],
        )
        self.assertEqual(child_one.path.parent, parent.path)
        self.assertEqual(child_two.path.parent, parent.path)
        self.assertEqual(child_three.path.parent, parent.path)

    def test_child_id_skips_active_ids_that_are_already_used(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                parent = storage.create_task("parent")
                other = storage.create_task("other")
                child = storage.create_task("child", parent.id)

        self.assertEqual(parent.id, 1)
        self.assertEqual(other.id, 2)
        self.assertEqual(child.id, 3)
        self.assertEqual(child.parent_id, parent.id)

    def test_top_level_ids_remain_monotonic_after_child_allocation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                parent = storage.create_task("parent")
                child = storage.create_task("child", parent.id)
                other = storage.create_task("other")

        self.assertEqual(parent.id, 1)
        self.assertEqual(child.id, 2)
        self.assertEqual(other.id, 3)

    def test_missing_parent_still_raises_file_not_found(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                with self.assertRaises(FileNotFoundError):
                    storage.create_task("child", parent_id=999)
                self.assertEqual(storage.all_tasks(), {})

    def test_all_tasks_still_excludes_archived_tasks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                task = storage.create_task("archived")
                month_dir = storage.archive_dir() / "2026-05"
                month_dir.mkdir(parents=True)
                task.path.rename(month_dir / task.path.name)

                self.assertNotIn(task.id, storage.all_tasks())
                self.assertIsNone(storage.find_task(task.id))
                self.assertIn(task.id, storage.all_task_ids(include_archive=True))

    def test_top_level_id_skips_archived_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                archived = storage.create_task("archived")
                month_dir = storage.archive_dir() / "2026-05"
                month_dir.mkdir(parents=True)
                archived.path.rename(month_dir / archived.path.name)

                active = storage.create_task("active")

        self.assertEqual(archived.id, 1)
        self.assertEqual(active.id, 2)

    def test_child_id_skips_archived_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                parent = storage.create_task("parent")
                archived = storage.create_task("archived")
                month_dir = storage.archive_dir() / "2026-05"
                month_dir.mkdir(parents=True)
                archived.path.rename(month_dir / archived.path.name)

                child = storage.create_task("child", parent.id)

        self.assertEqual(parent.id, 1)
        self.assertEqual(archived.id, 2)
        self.assertEqual(child.id, 3)
        self.assertEqual(child.parent_id, parent.id)

    def test_next_task_id_starts_at_one_with_no_tasks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                self.assertEqual(storage.next_task_id(), 1)


class TaskStorageHelperTests(unittest.TestCase):
    def test_task_name_uses_supplied_datetime(self) -> None:
        self.assertEqual(
            storage._task_name(5, "demo", datetime(2026, 5, 13, 8, 9, 10)),
            "5-05-13-demo",
        )

    def test_parse_id_range_handles_mixed_input(self) -> None:
        self.assertEqual(storage.parse_id_range("1, 3-5, 4, 2"), [1, 2, 3, 4, 5])

    def test_read_json_returns_none_for_missing_and_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            invalid = Path(temp_dir) / "invalid.json"
            invalid.write_text("{not json}", encoding="utf-8")

            self.assertIsNone(storage._read_json(missing))
            self.assertIsNone(storage._read_json(invalid))

    def test_write_json_round_trips_utf8(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.json"
            data = {"message": "café"}

            storage._write_json(path, data)

            self.assertEqual(storage._read_json(path), data)
            self.assertIn("café", path.read_text(encoding="utf-8"))

    def test_relative_path_uses_project_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / ".fa" / "tasks" / "demo" / "task.json"
            with patch.object(storage, "find_project_root", return_value=root):
                self.assertEqual(
                    storage.relative_path(target), ".fa/tasks/demo/task.json"
                )


class TaskArchiveCommandTests(unittest.TestCase):
    def test_archive_command_moves_task_and_updates_status(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir:
            with patch.object(
                storage, "find_project_root", return_value=Path(temp_dir)
            ):
                result = runner.invoke(app, ["task", "create", "demo"])
                self.assertEqual(result.exit_code, 0, result.output)
                task_id = next(iter(storage.all_task_ids()))
                task = storage.find_task(task_id)
                assert task is not None
                task.transition_to("approved")
                task.transition_to("running")
                task.transition_to("completed")
                storage.save_task(task)
                result = runner.invoke(app, ["task", "archive", str(task_id)])
                self.assertEqual(result.exit_code, 0, result.output)


if __name__ == "__main__":
    unittest.main()
