from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core.logview import TaskViewer
from fa.gestate import commands as gestate_commands


class FakeController:
    close_called = False
    wait_closed_called = False

    def __init__(self, viewer: TaskViewer, *, is_open: bool = True) -> None:
        self.viewer = viewer
        self._is_open = is_open

    def is_open(self) -> bool:
        return self._is_open

    def close(self) -> None:
        type(self).close_called = True

    def wait_closed(self, timeout: float | None = None) -> None:
        type(self).wait_closed_called = True


def test_gestate_auto_run_closes_open_viewer_without_runnable_tasks() -> None:
    FakeController.close_called = False
    FakeController.wait_closed_called = False

    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task, save_task

            parent = create_task("parent")
            child = create_task("child", parent_id=parent.id)
            (parent.path / "spec.md").write_text("spec", encoding="utf-8")
            (child.path / "plan.md").write_text("plan", encoding="utf-8")
            child.status = "completed"
            save_task(child)

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
                ),
                patch("fa.gestate.commands.ViewerController", FakeController),
            ):
                gestate_commands.gestate(
                    str(parent.id), tool="claude", max_rounds=1, run=True
                )

    assert FakeController.close_called
    assert FakeController.wait_closed_called


def test_gestate_auto_run_hands_off_open_viewer() -> None:
    FakeController.close_called = False
    FakeController.wait_closed_called = False

    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
                ),
                patch("fa.gestate.commands.ViewerController", FakeController),
                patch(
                    "fa.gestate.commands._run_runnable_task_tree", return_value=0
                ) as run_tree,
            ):
                gestate_commands.gestate(
                    str(task.id),
                    tool="claude",
                    max_rounds=1,
                    run=True,
                    run_tool="claude",
                )

    run_tree.assert_called_once()
    assert run_tree.call_args.kwargs["open_viewer"]
    assert FakeController.close_called
    assert FakeController.wait_closed_called


def test_gestate_auto_run_does_not_handoff_when_viewer_closed() -> None:
    FakeController.close_called = False
    FakeController.wait_closed_called = False

    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
                ),
                patch(
                    "fa.gestate.commands.ViewerController",
                    lambda viewer: FakeController(viewer, is_open=False),
                ),
                patch(
                    "fa.gestate.commands._run_runnable_task_tree", return_value=0
                ) as run_tree,
            ):
                gestate_commands.gestate(
                    str(task.id), tool="claude", max_rounds=1, run=True
                )

    run_tree.assert_called_once()
    assert not run_tree.call_args.kwargs["open_viewer"]
    assert not FakeController.close_called


def test_gestate_auto_run_does_not_handoff_to_non_streaming_run_tool() -> None:
    FakeController.close_called = False
    FakeController.wait_closed_called = False

    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
                ),
                patch("fa.gestate.commands.ViewerController", FakeController),
                patch(
                    "fa.gestate.commands._run_runnable_task_tree", return_value=0
                ) as run_tree,
            ):
                gestate_commands.gestate(
                    str(task.id),
                    tool="claude",
                    max_rounds=1,
                    run=True,
                    run_tool="opencode",
                )

    run_tree.assert_called_once()
    assert not run_tree.call_args.kwargs["open_viewer"]
    assert FakeController.close_called
    assert FakeController.wait_closed_called


def test_gestate_auto_run_hands_off_to_codex_viewer() -> None:
    FakeController.close_called = False
    FakeController.wait_closed_called = False

    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
                ),
                patch("fa.gestate.commands.ViewerController", FakeController),
                patch(
                    "fa.gestate.commands._run_runnable_task_tree", return_value=0
                ) as run_tree,
            ):
                gestate_commands.gestate(
                    str(task.id),
                    tool="claude",
                    max_rounds=1,
                    run=True,
                    run_tool="codex",
                )

    run_tree.assert_called_once()
    assert run_tree.call_args.kwargs["open_viewer"]
    assert FakeController.close_called
    assert FakeController.wait_closed_called
