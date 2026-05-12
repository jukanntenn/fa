import unittest
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


class TaskArchiveCommandTests(unittest.TestCase):
    def test_archive_without_range_moves_all_completed_tasks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(storage, "find_project_root", return_value=root):
                completed = storage.create_task("completed")
                draft = storage.create_task("draft")
                completed.status = "completed"
                storage.save_task(completed)

                result = CliRunner().invoke(app, ["task", "archive"])

                month_dir = storage.archive_dir() / completed.created_at[:7]
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertFalse(completed.path.exists())
                self.assertTrue((month_dir / completed.path.name).is_dir())
                self.assertTrue(draft.path.is_dir())

    def test_archive_without_range_reports_no_completed_tasks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(storage, "find_project_root", return_value=root):
                storage.create_task("draft")

                result = CliRunner().invoke(app, ["task", "archive"])

                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("No completed tasks to archive", result.output)

    def test_archive_explicit_range_preserves_non_completed_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(storage, "find_project_root", return_value=root):
                draft = storage.create_task("draft")

                result = CliRunner().invoke(app, ["task", "archive", str(draft.id)])

                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("is not completed", result.output)

    def test_archive_completed_parent_and_child_moves_parent_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(storage, "find_project_root", return_value=root):
                parent = storage.create_task("parent")
                child = storage.create_task("child", parent.id)
                parent.status = "completed"
                child.status = "completed"
                storage.save_task(parent)
                storage.save_task(child)

                result = CliRunner().invoke(app, ["task", "archive"])

                month_dir = storage.archive_dir() / parent.created_at[:7]
                archived_parent = month_dir / parent.path.name
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertTrue(archived_parent.is_dir())
                self.assertTrue((archived_parent / child.path.name).is_dir())
                self.assertFalse(parent.path.exists())

    def test_archive_explicit_parent_and_child_moves_parent_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(storage, "find_project_root", return_value=root):
                parent = storage.create_task("parent")
                child = storage.create_task("child", parent.id)
                parent.status = "completed"
                child.status = "completed"
                storage.save_task(parent)
                storage.save_task(child)

                result = CliRunner().invoke(
                    app, ["task", "archive", f"{parent.id},{child.id}"]
                )

                month_dir = storage.archive_dir() / parent.created_at[:7]
                archived_parent = month_dir / parent.path.name
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertTrue(archived_parent.is_dir())
                self.assertTrue((archived_parent / child.path.name).is_dir())
                self.assertFalse(parent.path.exists())


if __name__ == "__main__":
    unittest.main()
