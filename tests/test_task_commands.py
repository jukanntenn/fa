from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.task import storage
from fa.task.commands import (
    _dedupe_archive_roots,
    _select_runnable_candidates,
    create,
    done,
    info,
    list_tasks,
    rm,
)


def _make_task(
    tempdir: str, slug: str, status: str = "completed", parent_id: int | None = None
):
    with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
        task = storage.create_task(slug, parent_id)
        if status == "draft":
            pass
        elif status == "approved":
            task.transition_to("approved")
        elif status == "running":
            task.transition_to("approved")
            task.transition_to("running")
        elif status == "failed":
            task.transition_to("approved")
            task.transition_to("running")
            task.transition_to("failed")
        elif status == "completed":
            task.transition_to("approved")
            task.transition_to("completed")
        storage.save_task(task)
    return task


def test_dedupe_archive_roots_removes_child_when_parent_selected(
    tmp_path: Path,
) -> None:
    with TemporaryDirectory() as tempdir:
        parent = _make_task(tempdir, "parent")
        child = _make_task(tempdir, "child", parent_id=parent.id)
        result = _dedupe_archive_roots([parent, child])
        assert len(result) == 1
        assert result[0].id == parent.id


def test_dedupe_archive_roots_keeps_unrelated_tasks(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        t1 = _make_task(tempdir, "task-a")
        t2 = _make_task(tempdir, "task-b")
        result = _dedupe_archive_roots([t1, t2])
        assert len(result) == 2


def test_dedupe_archive_roots_sorted_by_id(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        t1 = _make_task(tempdir, "task-a")
        t2 = _make_task(tempdir, "task-b")
        result = _dedupe_archive_roots([t2, t1])
        assert result[0].id < result[1].id


def test_dedupe_archive_roots_empty():
    result = _dedupe_archive_roots([])
    assert result == []


def test_select_runnable_candidates_force_excludes_completed(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        approved = _make_task(tempdir, "approved", status="approved")
        completed = _make_task(tempdir, "completed", status="completed")
        tasks = {approved.id: approved, completed.id: completed}
        result = _select_runnable_candidates(
            tasks, [approved.id, completed.id], force=True, attempt=False
        )
        assert result == [approved.id]


def test_select_runnable_candidates_default_returns_approved_failed(
    tmp_path: Path,
) -> None:
    with TemporaryDirectory() as tempdir:
        approved = _make_task(tempdir, "approved", status="approved")
        failed = _make_task(tempdir, "failed", status="failed")
        pending = _make_task(tempdir, "pending", status="pending")
        tasks = {approved.id: approved, failed.id: failed, pending.id: pending}
        result = _select_runnable_candidates(
            tasks, [approved.id, failed.id, pending.id], force=False, attempt=False
        )
        assert set(result) == {approved.id, failed.id}


def test_select_runnable_candidates_attempt_requires_feedback(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("with-feedback")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            task.transition_to("approved")
            (task.path / "feedback-1.md").write_text("fb", encoding="utf-8")
            storage.save_task(task)
            no_fb = storage.create_task("no-feedback")
            (no_fb.path / "spec.md").write_text("spec", encoding="utf-8")
            no_fb.transition_to("approved")
            storage.save_task(no_fb)
        tasks = {task.id: task, no_fb.id: no_fb}
        result = _select_runnable_candidates(
            tasks, [task.id, no_fb.id], force=False, attempt=True
        )
        assert result == [task.id]


def test_select_runnable_candidates_strict_raises_on_non_approved(
    tmp_path: Path,
) -> None:
    from fa.task.commands import CandidateValidationError

    with TemporaryDirectory() as tempdir:
        pending = _make_task(tempdir, "pending", status="pending")
        approved = _make_task(tempdir, "approved", status="approved")
        tasks = {pending.id: pending, approved.id: approved}
        try:
            _select_runnable_candidates(
                tasks,
                [pending.id, approved.id],
                force=False,
                attempt=False,
                strict=True,
            )
            assert False, "Should have raised"
        except CandidateValidationError:
            pass


def test_select_runnable_candidates_strict_approves_valid(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        approved = _make_task(tempdir, "approved", status="approved")
        tasks = {approved.id: approved}
        result = _select_runnable_candidates(
            tasks, [approved.id], force=False, attempt=False, strict=True
        )
        assert result == [approved.id]


def test_create_command_success(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            create("my-task", parent=None)
        output = capsys.readouterr().out
        assert "Created task" in output
        assert "my-task" in output


def test_create_command_with_parent(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            parent = storage.create_task("parent")
            create("child", parent=parent.id)
        output = capsys.readouterr().out
        assert "Created task" in output


def test_list_tasks_command(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            storage.create_task("alpha")
            storage.create_task("beta")
            list_tasks(status=None)
        output = capsys.readouterr().out
        assert "alpha" in output
        assert "beta" in output


def test_list_tasks_filters_by_status(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            storage.create_task("only-draft")
            list_tasks(status="draft")
        output = capsys.readouterr().out
        assert "only-draft" in output


def test_info_command(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("info-task")
            info(task.id)
        output = capsys.readouterr().out
        assert "info-task" in output
        assert "Slug: info-task" in output


def test_info_command_not_found() -> None:
    import typer

    try:
        info(99999)
    except typer.Exit as exc:
        assert exc.exit_code == 1
    else:
        raise AssertionError("Expected typer.Exit")


def test_done_command(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("done-task")
            task.transition_to("approved")
            storage.save_task(task)
            done(str(task.id))
            updated = storage.find_task(task.id)
            assert updated is not None
            assert updated.status == "completed"


def test_done_command_not_found() -> None:
    import typer

    try:
        done("99999")
    except typer.Exit as exc:
        assert exc.exit_code == 1
    else:
        raise AssertionError("Expected typer.Exit")


def test_rm_command_forced(capsys) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("rm-task")
            task_path = task.path
            assert task_path.exists()
            rm(str(task.id), force=True)
            assert not task_path.exists()


def test_rm_command_not_found() -> None:
    import typer

    try:
        rm("99999", force=True)
    except typer.Exit as exc:
        assert exc.exit_code == 1
    else:
        raise AssertionError("Expected typer.Exit")


def test_done_command_invalid_transition() -> None:
    import typer

    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("already-done")
            task.transition_to("approved")
            task.complete()
            storage.save_task(task)
            try:
                done(str(task.id))
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


def test_rm_command_confirm_declined() -> None:
    import typer

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.commands.typer.confirm", return_value=False),
        ):
            task = storage.create_task("declined-rm")
            try:
                rm(str(task.id), force=False)
            except typer.Exit as exc:
                assert exc.exit_code == 0
            else:
                raise AssertionError("Expected typer.Exit")
            assert task.path.exists()


def test_create_command_invalid_parent() -> None:
    import typer

    try:
        create("orphan", parent=99999)
    except typer.Exit as exc:
        assert exc.exit_code == 1
    else:
        raise AssertionError("Expected typer.Exit")
