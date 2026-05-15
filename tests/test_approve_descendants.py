from __future__ import annotations

from fa.gestate.tasks import _approve_task_descendants


def test_approve_descendants_with_no_children(storage_root):
    from fa.task.storage import create_task

    task = create_task("leaf")
    count, total, failed = _approve_task_descendants(task)
    assert count == 0
    assert total == 0
    assert failed is False


def test_approve_descendants_approves_draft_children(storage_root):
    from fa.gestate.tasks import find_task
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    save_task(child)
    count, total, failed = _approve_task_descendants(parent)
    assert count == 1
    assert total == 1
    assert failed is False
    updated_child = find_task(child.id)
    assert updated_child is not None
    assert updated_child.status == "approved"


def test_approve_descendants_skips_already_approved(storage_root):
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    child.status = "approved"
    save_task(child)
    count, total, failed = _approve_task_descendants(parent)
    assert count == 0
    assert total == 1
    assert failed is False
