from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.gestate.commands import gestate
from fa.task import storage


def test_gestate_empty_input_exits() -> None:
    import typer

    with (
        patch("fa.cli.app_state"),
        patch("fa.gestate.commands._read_stdin", return_value=""),
    ):
        try:
            gestate(arg=None)
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_gestate_task_id_not_found() -> None:
    import typer

    with (
        patch("fa.cli.app_state"),
        patch("fa.gestate.commands._is_task_id", return_value=True),
    ):
        try:
            gestate(arg="99999")
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_gestate_task_id_found_but_invalid() -> None:
    import typer

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state") as mock_state,
            patch("fa.gestate.commands._is_task_id", return_value=True),
            patch("fa.gestate.commands.find_task") as mock_find,
        ):
            mock_state.logger = MagicMock()
            task = storage.create_task("bad-task")
            mock_find.return_value = task
            try:
                gestate(arg=str(task.id))
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")
