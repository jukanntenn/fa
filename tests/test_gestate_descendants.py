from __future__ import annotations

from fa.gestate.tasks import _resolve_task_descendants


def test_resolve_task_descendants_returns_empty_for_leaf_task(storage_root):
    from fa.task.storage import create_task

    task = create_task("leaf-task")
    result = _resolve_task_descendants(task)
    assert result == []


def test_resolve_task_descendants_returns_children_sorted(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child1 = create_task("child1", parent.id)
    child2 = create_task("child2", parent.id)
    result = _resolve_task_descendants(parent)
    assert result == [child1, child2]


def test_resolve_task_descendants_returns_nested_descendants(storage_root):
    from fa.task.storage import create_task

    grandparent = create_task("grandparent")
    parent = create_task("parent", grandparent.id)
    child = create_task("child", parent.id)
    result = _resolve_task_descendants(grandparent)
    assert result == [parent, child]
