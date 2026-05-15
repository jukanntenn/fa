from __future__ import annotations


# ─── _approve_task_descendants ──────────────────────────────────
def test_approve_descendants_with_no_children(storage_root):
    from fa.gestate.tasks import _approve_task_descendants
    from fa.task.storage import create_task

    task = create_task("leaf")
    count, total, failed = _approve_task_descendants(task)
    assert count == 0
    assert total == 0
    assert failed is False


def test_approve_descendants_approves_draft_children(storage_root):
    from fa.gestate.tasks import _approve_task_descendants, find_task
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
    from fa.gestate.tasks import _approve_task_descendants
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    child.status = "approved"
    save_task(child)
    count, total, failed = _approve_task_descendants(parent)
    assert count == 0
    assert total == 1
    assert failed is False


# ─── _find_new_parent_task ─────────────────────────────────────
def test_find_new_parent_task_returns_none_when_no_new_tasks(storage_root):
    from fa.gestate.tasks import _find_new_parent_task
    from fa.task.storage import create_task, save_task

    task = create_task("test")
    save_task(task)
    preexisting = frozenset({task.id})
    result = _find_new_parent_task(preexisting)
    assert result is None


def test_find_new_parent_task_returns_task_with_no_parent(storage_root):
    from fa.gestate.tasks import _find_new_parent_task
    from fa.task.storage import create_task, save_task

    preexisting = frozenset()
    task = create_task("orphan")
    save_task(task)
    result = _find_new_parent_task(preexisting)
    assert result is not None
    assert result.id == task.id


def test_find_new_parent_task_returns_min_id_when_no_orphans(storage_root):
    from fa.gestate.tasks import _find_new_parent_task
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
    from fa.gestate.tasks import _find_new_parent_task
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


# ─── _resolve_task_descendants (from test_resolve_descendants) ──
def test_resolve_descendants_with_no_children(storage_root):
    from fa.gestate.tasks import _resolve_task_descendants
    from fa.task.storage import create_task

    task = create_task("leaf")
    result = _resolve_task_descendants(task)
    assert result == []


def test_resolve_descendants_with_child(storage_root):
    from fa.gestate.tasks import _resolve_task_descendants
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    save_task(child)
    result = _resolve_task_descendants(parent)
    assert len(result) == 1
    assert result[0].id == child.id


def test_resolve_descendants_with_nested_children(storage_root):
    from fa.gestate.tasks import _resolve_task_descendants
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
