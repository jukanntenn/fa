from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from fa.cli import app
from fa.task import storage
from fa.task.commands import _dedupe_archive_roots


def test_child_ids_use_lowest_available_ids_after_parent(storage_root):
    parent = storage.create_task("parent")
    child_one = storage.create_task("child-one", parent.id)
    child_two = storage.create_task("child-two", parent.id)
    child_three = storage.create_task("child-three", parent.id)

    assert parent.id == 1
    assert [child_one.id, child_two.id, child_three.id] == [2, 3, 4]
    assert [child_one.parent_id, child_two.parent_id, child_three.parent_id] == [
        parent.id,
        parent.id,
        parent.id,
    ]
    assert child_one.path.parent == parent.path
    assert child_two.path.parent == parent.path
    assert child_three.path.parent == parent.path


def test_child_id_skips_active_ids_that_are_already_used(storage_root):
    parent = storage.create_task("parent")
    other = storage.create_task("other")
    child = storage.create_task("child", parent.id)

    assert parent.id == 1
    assert other.id == 2
    assert child.id == 3
    assert child.parent_id == parent.id


def test_top_level_ids_remain_monotonic_after_child_allocation(storage_root):
    parent = storage.create_task("parent")
    child = storage.create_task("child", parent.id)
    other = storage.create_task("other")

    assert parent.id == 1
    assert child.id == 2
    assert other.id == 3


def test_missing_parent_still_raises_file_not_found(storage_root):
    with pytest.raises(FileNotFoundError):
        storage.create_task("child", parent_id=999)
    assert storage.all_tasks() == {}


def test_all_tasks_still_excludes_archived_tasks(storage_root):
    task = storage.create_task("archived")
    month_dir = storage.archive_dir() / "2026-05"
    month_dir.mkdir(parents=True)
    task.path.rename(month_dir / task.path.name)

    assert task.id not in storage.all_tasks()
    assert storage.find_task(task.id) is None
    assert task.id in storage.all_task_ids(include_archive=True)


def test_all_tasks_with_include_archive_returns_archived(storage_root):
    task = storage.create_task("to-archive")
    month_dir = storage.archive_dir() / "2026-05"
    month_dir.mkdir(parents=True)
    task.path.rename(month_dir / task.path.name)

    assert task.id not in storage.all_tasks()
    assert task.id in storage.all_tasks(include_archive=True)


def test_top_level_id_skips_archived_ids(storage_root):
    archived = storage.create_task("archived")
    month_dir = storage.archive_dir() / "2026-05"
    month_dir.mkdir(parents=True)
    archived.path.rename(month_dir / archived.path.name)

    active = storage.create_task("active")

    assert archived.id == 1
    assert active.id == 2


def test_child_id_skips_archived_ids(storage_root):
    parent = storage.create_task("parent")
    archived = storage.create_task("archived")
    month_dir = storage.archive_dir() / "2026-05"
    month_dir.mkdir(parents=True)
    archived.path.rename(month_dir / archived.path.name)

    child = storage.create_task("child", parent.id)

    assert parent.id == 1
    assert archived.id == 2
    assert child.id == 3
    assert child.parent_id == parent.id


def test_next_task_id_starts_at_one_with_no_tasks(storage_root):
    assert storage.next_task_id() == 1


def test_create_task_raises_value_error_for_invalid_slug(storage_root):
    with pytest.raises(ValueError):
        storage.create_task("-invalid")
    with pytest.raises(ValueError):
        storage.create_task("has space")
    assert storage.all_tasks() == {}


def test_all_tasks_skips_corrupt_json(storage_root):
    task = storage.create_task("valid")
    corrupt_dir = storage.tasks_dir() / "99-05-13-bad"
    corrupt_dir.mkdir()
    corrupt_dir.joinpath("task.json").write_text("not json", encoding="utf-8")

    result = storage.all_tasks()

    assert task.id in result
    assert 99 not in result


def test_all_task_ids_skips_non_int_and_corrupt_ids(storage_root):
    storage.create_task("first")
    non_int_dir = storage.tasks_dir() / "99-05-13-nonint"
    non_int_dir.mkdir()
    non_int_dir.joinpath("task.json").write_text(
        '{"id": "not-a-number", "slug": "x", "created_at": "2026-01-01T00:00:00"}',
        encoding="utf-8",
    )
    corrupt_dir = storage.tasks_dir() / "98-05-13-bad"
    corrupt_dir.mkdir()
    corrupt_dir.joinpath("task.json").write_text("broken", encoding="utf-8")

    result = storage.all_task_ids()

    assert result == {1}


def test_find_children_returns_matching_tasks(storage_root):
    parent = storage.create_task("parent")
    child = storage.create_task("child", parent.id)
    storage.create_task("unrelated")

    children = storage.find_children(parent.id)

    assert len(children) == 1
    assert children[0].id == child.id
    assert children[0].parent_id == parent.id


def test_task_name_uses_supplied_datetime() -> None:
    assert (
        storage._task_name(5, "demo", datetime(2026, 5, 13, 8, 9, 10)) == "5-05-13-demo"
    )


def test_task_name_with_default_none_date_uses_current_datetime() -> None:
    name = storage._task_name(10, "my-task")
    assert name.startswith("10-")
    assert name.endswith("-my-task")


def test_parse_id_range_handles_mixed_input() -> None:
    assert storage.parse_id_range("1, 3-5, 4, 2") == [1, 2, 3, 4, 5]


def test_parse_id_range_with_single_id() -> None:
    assert storage.parse_id_range("42") == [42]


def test_parse_id_range_with_whitespace_only_input() -> None:
    assert storage.parse_id_range("  ,  ,  ") == []


def test_parse_id_range_with_overlapping_ranges() -> None:
    assert storage.parse_id_range("1-3, 2-4") == [1, 2, 3, 4]


def test_parse_id_range_with_single_element_range() -> None:
    assert storage.parse_id_range("5-5") == [5]


def test_parse_id_range_with_adjacent_ranges() -> None:
    assert storage.parse_id_range("1-2, 3-4, 5-6") == [1, 2, 3, 4, 5, 6]


def test_read_json_returns_none_for_missing_and_invalid_json() -> None:
    with TemporaryDirectory() as temp_dir:
        missing = Path(temp_dir) / "missing.json"
        invalid = Path(temp_dir) / "invalid.json"
        invalid.write_text("{not json}", encoding="utf-8")

        assert storage._read_json(missing) is None
        assert storage._read_json(invalid) is None


def test_write_json_round_trips_utf8() -> None:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "sample.json"
        data = {"message": "café"}

        storage._write_json(path, data)

        assert storage._read_json(path) == data
        assert "café" in path.read_text(encoding="utf-8")


def test_relative_path_uses_project_root() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        target = root / ".fa" / "tasks" / "demo" / "task.json"
        with patch.object(storage, "find_project_root", return_value=root):
            assert storage.relative_path(target) == ".fa/tasks/demo/task.json"


def test_archive_command_moves_task_and_updates_status() -> None:
    runner = CliRunner()
    with TemporaryDirectory() as temp_dir:
        with patch.object(storage, "find_project_root", return_value=Path(temp_dir)):
            result = runner.invoke(app, ["task", "create", "demo"])
            assert result.exit_code == 0, result.output
            task_id = next(iter(storage.all_task_ids()))
            task = storage.find_task(task_id)
            assert task is not None
            task.transition_to("approved")
            task.transition_to("running")
            task.transition_to("completed")
            storage.save_task(task)
            result = runner.invoke(app, ["task", "archive", str(task_id)])
            assert result.exit_code == 0, result.output


def test_dedupe_archive_roots_returns_all_when_no_overlap(storage_root):
    from fa.task.model import Task

    t1 = Task.new(1, "t1", None, storage_root / "t1")
    t2 = Task.new(2, "t2", None, storage_root / "t2")
    result = _dedupe_archive_roots([t1, t2])
    assert result == [t1, t2]


def test_dedupe_archive_roots_filters_child_when_parent_selected(storage_root):
    from fa.task.model import Task

    parent = Task.new(1, "parent", None, storage_root / "parent")
    child = Task.new(2, "child", parent.id, storage_root / "parent" / "child")
    result = _dedupe_archive_roots([parent, child])
    assert result == [parent]
    assert child not in result


def test_dedupe_archive_roots_returns_sorted_by_id(storage_root):
    from fa.task.model import Task

    t3 = Task.new(3, "t3", None, storage_root / "t3")
    t1 = Task.new(1, "t1", None, storage_root / "t1")
    t2 = Task.new(2, "t2", None, storage_root / "t2")
    result = _dedupe_archive_roots([t3, t1, t2])
    assert [t.id for t in result] == [1, 2, 3]


def test_save_task_persists_and_find_task_retrieves_it(storage_root):
    task = storage.create_task("test-task")
    task.status = "approved"
    task.depends_on = [2, 3]
    task.related_to = [4]
    storage.save_task(task)

    retrieved = storage.find_task(task.id)
    assert retrieved is not None
    assert retrieved.slug == "test-task"
    assert retrieved.status == "approved"
    assert retrieved.depends_on == [2, 3]
    assert retrieved.related_to == [4]


def test_save_task_overwrites_existing_task(storage_root):
    task = storage.create_task("original-task")
    storage.save_task(task)

    task.status = "approved"
    storage.save_task(task)

    retrieved = storage.find_task(task.id)
    assert retrieved is not None
    assert retrieved.status == "approved"


def test_create_task_returns_task_with_correct_properties(storage_root):
    task = storage.create_task("my-task")
    assert task.slug == "my-task"
    assert task.status == "draft"
    assert task.parent_id is None
    assert task.depends_on == []
    assert task.related_to == []
    assert task.path.exists()


# ─── auto_complete_parent_of / auto_complete_all_eligible_parents ──
def test_auto_complete_parent_of_returns_early_when_no_parent_id(storage_root):
    from unittest.mock import MagicMock

    from fa.task.model import Task

    task = Task.new(1, "test", None, storage_root / "t1")
    storage.auto_complete_parent_of({}, task, logger=MagicMock())


def test_auto_complete_parent_of_returns_early_when_parent_completed(storage_root):
    parent = storage.create_task("parent")
    parent.status = "completed"
    task = storage.create_task("child", parent.id)
    storage.auto_complete_parent_of({parent.id: parent, task.id: task}, task)
    assert parent.status == "completed"


def test_auto_complete_parent_of_returns_early_when_parent_draft(storage_root):
    parent = storage.create_task("parent")
    task = storage.create_task("child", parent.id)
    storage.auto_complete_parent_of({parent.id: parent, task.id: task}, task)
    assert parent.status == "draft"


def test_auto_complete_parent_of_auto_completes_parent(storage_root):
    parent = storage.create_task("parent")
    parent.status = "approved"
    child = storage.create_task("child", parent.id)
    child.status = "completed"
    storage.auto_complete_parent_of({parent.id: parent, child.id: child}, child)
    assert parent.status == "completed"


def test_auto_complete_parent_of_does_not_complete_parent_with_incomplete_children(
    storage_root,
):
    parent = storage.create_task("parent")
    parent.status = "approved"
    child1 = storage.create_task("child1", parent.id)
    child1.status = "completed"
    child2 = storage.create_task("child2", parent.id)
    child2.status = "approved"
    storage.auto_complete_parent_of(
        {parent.id: parent, child1.id: child1, child2.id: child2}, child1
    )
    assert parent.status == "approved"


def test_auto_complete_all_eligible_parents(storage_root):
    parent = storage.create_task("parent")
    parent.status = "approved"
    child = storage.create_task("child", parent.id)
    child.status = "completed"
    tasks = {parent.id: parent, child.id: child}
    storage.auto_complete_all_eligible_parents(tasks)
    assert parent.status == "completed"


def test_auto_complete_parent_of_logs_when_logger_provided(storage_root):
    from unittest.mock import MagicMock

    parent = storage.create_task("parent")
    parent.status = "approved"
    child = storage.create_task("child", parent.id)
    child.status = "completed"
    logger = MagicMock()
    storage.auto_complete_parent_of(
        {parent.id: parent, child.id: child}, child, logger=logger
    )
    assert parent.status == "completed"
    logger.info.assert_called_once()
    assert "auto-completed" in logger.info.call_args[0][0]
