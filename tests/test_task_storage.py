import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
