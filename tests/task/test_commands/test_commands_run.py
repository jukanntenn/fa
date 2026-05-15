from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.task import storage


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


# ─── run command ───────────────────────────────────────────────
def test_run_command_force_without_ids() -> None:
    import typer

    from fa.task.commands import run

    with patch("fa.cli.app_state"):
        try:
            run(
                ids=None,
                force=True,
                tool="codex",
                rounds=3,
                policies=None,
                glm_plan=False,
                attempt=False,
                yes=False,
            )
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_run_command_no_candidates() -> None:
    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
        ):
            run(
                ids=None,
                force=False,
                tool="codex",
                rounds=3,
                policies=None,
                glm_plan=False,
                attempt=False,
                yes=True,
            )


def test_run_command_with_ids() -> None:
    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.run_tasks", return_value=0),
        ):
            task = storage.create_task("run-me")
            task.transition_to("approved")
            storage.save_task(task)
            run(
                ids=str(task.id),
                force=False,
                tool="codex",
                rounds=3,
                policies=None,
                glm_plan=False,
                attempt=False,
                yes=True,
            )


def test_run_command_with_missing_ids() -> None:
    import typer

    from fa.task.commands import run

    with (
        patch.object(storage, "find_project_root", return_value=Path("/tmp")),
        patch("fa.cli.app_state"),
    ):
        try:
            run(
                ids="99999",
                force=False,
                tool="codex",
                rounds=3,
                policies=None,
                glm_plan=False,
                attempt=False,
                yes=True,
            )
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_run_command_nonzero_exit() -> None:
    import typer

    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.run_tasks", return_value=1),
        ):
            task = storage.create_task("fail-run")
            task.transition_to("approved")
            storage.save_task(task)
            try:
                run(
                    ids=str(task.id),
                    force=False,
                    tool="codex",
                    rounds=3,
                    policies=None,
                    glm_plan=False,
                    attempt=False,
                    yes=True,
                )
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


def test_run_command_with_policies() -> None:
    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.run_tasks", return_value=0),
            patch("fa.policy.runner.run_policies_by_ids", return_value=0),
        ):
            task = storage.create_task("policy-run")
            task.transition_to("approved")
            storage.save_task(task)
            run(
                ids=str(task.id),
                force=False,
                tool="codex",
                rounds=3,
                policies="lint,typecheck",
                glm_plan=False,
                attempt=False,
                yes=True,
            )


def test_run_command_candidate_validation_error() -> None:
    import typer

    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
        ):
            task = storage.create_task("draft-task")
            storage.save_task(task)
            try:
                run(
                    ids=str(task.id),
                    force=False,
                    tool="codex",
                    rounds=3,
                    policies=None,
                    glm_plan=False,
                    attempt=False,
                    yes=True,
                )
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


def test_run_command_shows_confirm_and_parent_info(capsys) -> None:
    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.run_tasks", return_value=0),
            patch("fa.task.commands.typer.confirm", return_value=True),
        ):
            parent = storage.create_task("parent")
            parent.transition_to("approved")
            storage.save_task(parent)
            child = storage.create_task("child", parent_id=parent.id)
            child.transition_to("approved")
            storage.save_task(child)
            run(
                ids=str(child.id),
                force=False,
                tool="codex",
                rounds=3,
                policies=None,
                glm_plan=False,
                attempt=False,
                yes=False,
            )
        output = capsys.readouterr().out
        assert "Tasks to execute" in output
        assert "parent" in output


def test_run_command_confirm_declined() -> None:
    import typer

    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.typer.confirm", return_value=False),
        ):
            task = storage.create_task("declined")
            task.transition_to("approved")
            storage.save_task(task)
            try:
                run(
                    ids=str(task.id),
                    force=False,
                    tool="codex",
                    rounds=3,
                    policies=None,
                    glm_plan=False,
                    attempt=False,
                    yes=False,
                )
            except typer.Exit as exc:
                assert exc.exit_code == 0
            else:
                raise AssertionError("Expected typer.Exit")


def test_run_command_policies_nonzero_exit() -> None:
    import typer

    from fa.task.commands import run

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state"),
            patch("fa.task.commands.run_tasks", return_value=0),
            patch("fa.policy.runner.run_policies_by_ids", return_value=1),
        ):
            task = storage.create_task("policy-fail")
            task.transition_to("approved")
            storage.save_task(task)
            try:
                run(
                    ids=str(task.id),
                    force=False,
                    tool="codex",
                    rounds=3,
                    policies="check",
                    glm_plan=False,
                    attempt=False,
                    yes=True,
                )
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


# ─── archive command ───────────────────────────────────────────
def test_archive_no_completed_tasks(capsys) -> None:
    from fa.task.commands import archive

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch(
                "fa.task.commands.archive_dir", return_value=Path(tempdir) / "archive"
            ),
        ):
            archive(id_range=None)
        output = capsys.readouterr().out
        assert "No completed tasks" in output


def test_archive_all_completed() -> None:
    from fa.task.commands import archive

    with TemporaryDirectory() as tempdir:
        archive_dest = Path(tempdir) / "archive"
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.commands.archive_dir", return_value=archive_dest),
        ):
            task = storage.create_task("archive-me")
            task.transition_to("approved")
            task.complete()
            storage.save_task(task)
            archive(id_range=None)


def test_archive_specific_ids(capsys) -> None:
    from fa.task.commands import archive

    with TemporaryDirectory() as tempdir:
        archive_dest = Path(tempdir) / "archive"
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.commands.archive_dir", return_value=archive_dest),
        ):
            task = storage.create_task("archive-me")
            task.transition_to("approved")
            task.complete()
            storage.save_task(task)
            archive(id_range=str(task.id))
        assert not task.path.exists()


def test_archive_not_completed() -> None:
    import typer

    from fa.task.commands import archive

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch(
                "fa.task.commands.archive_dir", return_value=Path(tempdir) / "archive"
            ),
        ):
            task = storage.create_task("not-done")
            try:
                archive(id_range=str(task.id))
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


def test_archive_missing_task() -> None:
    import typer

    from fa.task.commands import archive

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch(
                "fa.task.commands.archive_dir", return_value=Path(tempdir) / "archive"
            ),
        ):
            try:
                archive(id_range="99999")
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")
