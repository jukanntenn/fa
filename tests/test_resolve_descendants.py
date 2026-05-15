from __future__ import annotations

from fa.gestate.tasks import _resolve_task_descendants


def test_resolve_descendants_with_no_children(storage_root):
    from fa.task.storage import create_task

    task = create_task("leaf")
    result = _resolve_task_descendants(task)
    assert result == []


def test_resolve_descendants_with_child(storage_root):
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    save_task(child)
    result = _resolve_task_descendants(parent)
    assert len(result) == 1
    assert result[0].id == child.id


def test_resolve_descendants_with_nested_children(storage_root):
    from fa.task.storage import create_task, save_task

    grandparent = create_task("grandparent")
    parent = create_task("parent", grandparent.id)
    child = create_task("child", parent.id)
    save_task(parent)
    save_task(child)
    result = _resolve_task_descendants(grandparent)
    assert len(result) == 2
    assert result[0].id == parent.id
    assert result[1].id == child.id
