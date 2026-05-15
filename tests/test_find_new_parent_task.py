from __future__ import annotations

from fa.gestate.tasks import _find_new_parent_task


def test_find_new_parent_task_returns_none_when_no_new_tasks(storage_root):
    from fa.task.storage import create_task, save_task

    task = create_task("test")
    save_task(task)
    preexisting = frozenset({task.id})
    result = _find_new_parent_task(preexisting)
    assert result is None


def test_find_new_parent_task_returns_task_with_no_parent(storage_root):
    from fa.task.storage import create_task, save_task

    preexisting = frozenset()
    task = create_task("orphan")
    save_task(task)
    result = _find_new_parent_task(preexisting)
    assert result is not None
    assert result.id == task.id


def test_find_new_parent_task_returns_min_id_when_no_orphans(storage_root):
    from fa.task.storage import create_task, save_task

    preexisting = frozenset()
    parent = create_task("parent")
    child = create_task("child", parent.id)
    save_task(parent)
    save_task(child)
    result = _find_new_parent_task(preexisting)
    assert result is not None
    assert result.id == parent.id


def test_find_new_parent_task_returns_min_id_when_all_have_parents(storage_root):
    from fa.task.storage import create_task, save_task

    grandparent = create_task("grandparent")
    parent = create_task("parent", grandparent.id)
    child = create_task("child", parent.id)
    save_task(grandparent)
    save_task(parent)
    save_task(child)
    preexisting = frozenset({grandparent.id})
    result = _find_new_parent_task(preexisting)
    assert result is not None
    assert result.id == parent.id
