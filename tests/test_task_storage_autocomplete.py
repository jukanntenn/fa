from __future__ import annotations

from fa.task.storage import (
    auto_complete_all_eligible_parents,
    auto_complete_parent_of,
)


def test_auto_complete_parent_of_returns_early_when_no_parent_id(storage_root):
    from unittest.mock import MagicMock

    from fa.task.model import Task

    task = Task.new(1, "test", None, storage_root / "t1")
    auto_complete_parent_of({}, task, logger=MagicMock())


def test_auto_complete_parent_of_returns_early_when_parent_completed(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    parent.status = "completed"
    task = create_task("child", parent.id)
    auto_complete_parent_of({parent.id: parent, task.id: task}, task)
    assert parent.status == "completed"


def test_auto_complete_parent_of_returns_early_when_parent_draft(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    task = create_task("child", parent.id)
    auto_complete_parent_of({parent.id: parent, task.id: task}, task)
    assert parent.status == "draft"


def test_auto_complete_parent_of_auto_completes_parent(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    parent.status = "approved"
    child = create_task("child", parent.id)
    child.status = "completed"
    auto_complete_parent_of({parent.id: parent, child.id: child}, child)
    assert parent.status == "completed"


def test_auto_complete_parent_of_does_not_complete_parent_with_incomplete_children(
    storage_root,
):
    from fa.task.storage import create_task

    parent = create_task("parent")
    parent.status = "approved"
    child1 = create_task("child1", parent.id)
    child1.status = "completed"
    child2 = create_task("child2", parent.id)
    child2.status = "approved"
    auto_complete_parent_of(
        {parent.id: parent, child1.id: child1, child2.id: child2}, child1
    )
    assert parent.status == "approved"


def test_auto_complete_all_eligible_parents(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    parent.status = "approved"
    child = create_task("child", parent.id)
    child.status = "completed"
    tasks = {parent.id: parent, child.id: child}
    auto_complete_all_eligible_parents(tasks)
    assert parent.status == "completed"


def test_auto_complete_parent_of_logs_when_logger_provided(storage_root):
    from unittest.mock import MagicMock

    from fa.task.storage import create_task

    parent = create_task("parent")
    parent.status = "approved"
    child = create_task("child", parent.id)
    child.status = "completed"
    logger = MagicMock()
    auto_complete_parent_of({parent.id: parent, child.id: child}, child, logger=logger)
    assert parent.status == "completed"
    logger.info.assert_called_once()
    assert "auto-completed" in logger.info.call_args[0][0]
