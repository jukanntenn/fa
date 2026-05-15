from pathlib import Path

from fa.task.model import Task
from fa.task.storage import resolve_to_leaves


def _task(task_id: int, parent_id: int | None = None) -> Task:
    return Task(
        id=task_id,
        slug=f"t-{task_id}",
        parent_id=parent_id,
        status="draft",
        depends_on=[],
        related_to=[],
        created_at="2026-01-01T00:00:00",
        completed_at=None,
        path=Path(f"/tmp/tasks/{task_id}"),
    )


def test_single_leaf_returns_itself():
    assert resolve_to_leaves([1], {1: _task(1)}) == [1]


def test_single_root_with_children_returns_leaves():
    tasks = {1: _task(1), 2: _task(2, parent_id=1), 3: _task(3, parent_id=1)}
    assert resolve_to_leaves([1], tasks) == [2, 3]


def test_deeply_nested_tree_returns_deepest_leaves():
    tasks = {
        1: _task(1),
        2: _task(2, 1),
        3: _task(3, 2),
        4: _task(4, 2),
        5: _task(5, 3),
    }
    assert resolve_to_leaves([1], tasks) == [5, 4]


def test_mixed_leaf_and_nonleaf_input():
    tasks = {
        1: _task(1),
        2: _task(2),
        3: _task(3, parent_id=2),
        4: _task(4, parent_id=2),
    }
    assert resolve_to_leaves([1, 2], tasks) == [1, 3, 4]


def test_missing_task_ids_are_silently_skipped():
    assert resolve_to_leaves([1, 99], {1: _task(1)}) == [1]


def test_duplicate_input_ids_deduplicated():
    assert resolve_to_leaves([1, 1, 1], {1: _task(1)}) == [1]


def test_empty_input_returns_empty_list():
    assert resolve_to_leaves([], {}) == []
