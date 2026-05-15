from __future__ import annotations

from fa.gestate.tasks import _resolve_execution_candidates, _validate_task


def test_resolve_execution_candidates_returns_leaf_approved_tasks(storage_root):
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    child.status = "approved"
    save_task(child)
    result = _resolve_execution_candidates(parent)
    assert child.id in result


def test_resolve_execution_candidates_ignores_non_leaf(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    child.status = "approved"
    result = _resolve_execution_candidates(parent)
    assert parent.id not in result


def test_resolve_execution_candidates_returns_leaf_failed_tasks(storage_root):
    from fa.task.storage import create_task, save_task

    parent = create_task("parent")
    child = create_task("child", parent.id)
    child.status = "failed"
    save_task(child)
    result = _resolve_execution_candidates(parent)
    assert child.id in result


def test_validate_task_returns_issue_for_non_draft_status(storage_root):
    from fa.task.storage import create_task

    task = create_task("test")
    task.status = "approved"
    issues = _validate_task(task)
    assert any("status is 'approved'" in issue for issue in issues)


def test_validate_task_returns_issue_for_missing_spec(storage_root):
    from fa.task.storage import create_task

    task = create_task("test")
    issues = _validate_task(task)
    assert any("missing spec.md" in issue for issue in issues)


def test_validate_task_returns_issue_for_missing_plan(storage_root):
    from fa.task.storage import create_task

    task = create_task("test")
    issues = _validate_task(task)
    assert any("missing plan.md" in issue for issue in issues)


def test_validate_task_returns_empty_for_valid_task(storage_root):
    from fa.task.storage import create_task

    task = create_task("test")
    (task.path / "spec.md").write_text("# spec")
    (task.path / "plan.md").write_text("# plan")
    issues = _validate_task(task)
    assert issues == []


def test_validate_task_returns_issue_for_child_missing_plan(storage_root):
    from fa.task.storage import create_task

    parent = create_task("parent")
    (parent.path / "spec.md").write_text("# spec")
    child = create_task("child", parent.id)
    child.status = "completed"
    issues = _validate_task(parent)
    assert any("subtask" in issue and "missing plan.md" in issue for issue in issues)
