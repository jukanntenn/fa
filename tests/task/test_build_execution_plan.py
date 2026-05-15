from __future__ import annotations

from fa.task.runner import build_execution_plan


def test_build_execution_plan_empty():
    result = build_execution_plan({}, [])
    assert result == []


def test_build_execution_plan_simple(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    result = build_execution_plan({parent.id: parent, child.id: child}, [child.id])
    assert child.id in result


def test_build_execution_plan_with_children(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child1 = create_task("child1", parent.id)
    child2 = create_task("child2", parent.id)
    result = build_execution_plan(
        {parent.id: parent, child1.id: child1, child2.id: child2},
        [parent.id, child1.id, child2.id],
    )
    assert child1.id in result
    assert child2.id in result


def test_build_execution_plan_root_task_only(storage_root):
    from fa.task.storage import create_task

    root = create_task("root")
    result = build_execution_plan({root.id: root}, [root.id])
    assert result == [root.id]


def test_build_execution_plan_appends_parent_then_children(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    result = build_execution_plan(
        {parent.id: parent, child.id: child},
        [parent.id, child.id],
    )
    assert result[0] == parent.id
    assert child.id in result


def test_build_execution_plan_deduplicates_already_appended_children(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child1 = create_task("child1", parent.id)
    child2 = create_task("child2", parent.id)
    result = build_execution_plan(
        {parent.id: parent, child1.id: child1, child2.id: child2},
        [parent.id, child1.id, child2.id, child1.id],
    )
    assert child1.id in result
    assert child2.id in result


def test_build_execution_plan_sibling_after_seen_parent(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child1 = create_task("child1", parent.id)
    child2 = create_task("child2", parent.id)
    result = build_execution_plan(
        {parent.id: parent, child1.id: child1, child2.id: child2},
        [child1.id, child2.id],
    )
    assert result.index(child1.id) < result.index(child2.id)
