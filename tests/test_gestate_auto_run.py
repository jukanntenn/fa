import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from fa.core.logview import TaskViewer
from fa.gestate import commands as gestate_commands


class GestateAutoRunTests(unittest.TestCase):
    def test_resolve_execution_candidates_returns_approved_and_failed_children_only(
        self,
    ) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                parent = create_task("parent")
                approved = create_task("approved", parent_id=parent.id)
                failed = create_task("failed", parent_id=parent.id)
                completed = create_task("completed", parent_id=parent.id)
                (parent.path / "spec.md").write_text("spec", encoding="utf-8")
                for child in (approved, failed, completed):
                    (child.path / "plan.md").write_text("plan", encoding="utf-8")
                approved.transition_to("approved")
                save_task(approved)
                failed.status = "failed"
                save_task(failed)
                completed.status = "completed"
                save_task(completed)

                candidates = gestate_commands._resolve_execution_candidates(parent)

        self.assertEqual(candidates, sorted([approved.id, failed.id]))

    def test_resolve_execution_candidates_returns_leaf_parent_when_no_children(
        self,
    ) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                task.transition_to("approved")
                save_task(task)

                candidates = gestate_commands._resolve_execution_candidates(task)

        self.assertEqual(candidates, [task.id])

    def test_run_runnable_task_tree_calls_run_tasks_with_execution_plan(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                parent = create_task("parent")
                first = create_task("first", parent_id=parent.id)
                second = create_task("second", parent_id=parent.id)
                (parent.path / "spec.md").write_text("spec", encoding="utf-8")
                for child in (first, second):
                    (child.path / "plan.md").write_text("plan", encoding="utf-8")
                    child.transition_to("approved")
                    save_task(child)

                with patch(
                    "fa.gestate.commands.run_tasks", return_value=0
                ) as run_tasks:
                    result = gestate_commands._run_runnable_task_tree(
                        parent, Mock(), "codex", 3, False
                    )

        self.assertEqual(result, 0)
        run_tasks.assert_called_once()
        self.assertEqual(
            run_tasks.call_args.kwargs["ids"], sorted([first.id, second.id])
        )
        self.assertFalse(run_tasks.call_args.kwargs["force"])
        self.assertEqual(run_tasks.call_args.kwargs["tool"], "codex")
        self.assertEqual(run_tasks.call_args.kwargs["rounds"], 3)
        self.assertFalse(run_tasks.call_args.kwargs["glm_plan"])
        self.assertFalse(run_tasks.call_args.kwargs["attempt_mode"])

    def test_run_runnable_task_tree_passes_open_viewer_to_run_tasks(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                task.transition_to("approved")
                save_task(task)

                with patch(
                    "fa.gestate.commands.run_tasks", return_value=0
                ) as run_tasks:
                    result = gestate_commands._run_runnable_task_tree(
                        task, Mock(), "claude", 3, False, open_viewer=True
                    )

        self.assertEqual(result, 0)
        run_tasks.assert_called_once()
        self.assertTrue(run_tasks.call_args.kwargs["open_viewer"])

    def test_run_runnable_task_tree_propagates_failure_code(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                task.transition_to("approved")
                save_task(task)

                with patch("fa.gestate.commands.run_tasks", return_value=1):
                    result = gestate_commands._run_runnable_task_tree(
                        task, Mock(), "codex", 3, False
                    )

        self.assertEqual(result, 1)

    def test_run_runnable_task_tree_returns_zero_when_no_candidates(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                parent = create_task("parent")
                child = create_task("child", parent_id=parent.id)
                (parent.path / "spec.md").write_text("spec", encoding="utf-8")
                (child.path / "plan.md").write_text("plan", encoding="utf-8")
                child.status = "completed"
                save_task(child)

                with patch("fa.gestate.commands.run_tasks") as run_tasks:
                    result = gestate_commands._run_runnable_task_tree(
                        parent, Mock(), "codex", 3, False
                    )

        self.assertEqual(result, 0)
        run_tasks.assert_not_called()

    def test_gestate_exits_when_descendant_approval_fails(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                parent = create_task("parent")
                child = create_task("child", parent_id=parent.id)
                (parent.path / "spec.md").write_text("spec", encoding="utf-8")
                (child.path / "plan.md").write_text("plan", encoding="utf-8")
                child.status = "running"
                save_task(child)

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.run_tasks") as run_tasks,
                    patch("fa.gestate.commands.typer.echo") as echo,
                ):
                    with self.assertRaises(typer.Exit) as raised:
                        gestate_commands.gestate(
                            str(parent.id), tool="codex", max_rounds=1, run=True
                        )

        self.assertEqual(raised.exception.exit_code, 1)
        echo.assert_any_call(
            f"Warning: subtask {child.id} is 'running', skipped approval", err=True
        )
        run_tasks.assert_not_called()

    def test_approve_task_descendants_approves_nested_draft_children(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, find_task

                parent = create_task("parent")
                intermediate = create_task("intermediate", parent_id=parent.id)
                leaf = create_task("leaf", parent_id=intermediate.id)

                result = gestate_commands._approve_task_descendants(parent)

                saved_intermediate = find_task(intermediate.id)
                saved_leaf = find_task(leaf.id)

        self.assertEqual(result, (2, 2, False))
        self.assertIsNotNone(saved_intermediate)
        self.assertIsNotNone(saved_leaf)
        assert saved_intermediate is not None
        assert saved_leaf is not None
        self.assertEqual(saved_intermediate.status, "approved")
        self.assertEqual(saved_leaf.status, "approved")

    def test_approve_task_descendants_reports_non_approvable_nested_child(
        self,
    ) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task, save_task

                parent = create_task("parent")
                intermediate = create_task("intermediate", parent_id=parent.id)
                leaf = create_task("leaf", parent_id=intermediate.id)
                leaf.status = "running"
                save_task(leaf)

                with patch("fa.gestate.commands.typer.echo") as echo:
                    result = gestate_commands._approve_task_descendants(parent)

        self.assertEqual(result, (1, 2, True))
        echo.assert_any_call(
            f"Warning: subtask {leaf.id} is 'running', skipped approval", err=True
        )

    def _invoke_gestate_for_auto_run(self, *args: str) -> tuple[object, object]:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.cli import app, app_state
                from fa.task.storage import create_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch.object(app_state, "logger", Mock()),
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch(
                        "fa.gestate.commands._run_runnable_task_tree",
                        return_value=0,
                    ) as run_tree,
                ):
                    result = CliRunner().invoke(
                        app,
                        ["gestate", str(task.id), "--max-rounds", "1", *args],
                    )
                    return result, run_tree

    def test_gestate_auto_run_defaults_to_claude(self) -> None:
        result, run_tree = self._invoke_gestate_for_auto_run()

        self.assertEqual(result.exit_code, 0, result.output)
        run_tree.assert_called_once()
        self.assertEqual(run_tree.call_args.args[2], "claude")

    def test_gestate_auto_run_respects_run_tool_override(self) -> None:
        result, run_tree = self._invoke_gestate_for_auto_run("--run-tool", "codex")

        self.assertEqual(result.exit_code, 0, result.output)
        run_tree.assert_called_once()
        self.assertEqual(run_tree.call_args.args[2], "codex")

    def test_gestate_auto_run_closes_open_viewer_without_runnable_tasks(self) -> None:
        class FakeController:
            close_called = False
            wait_closed_called = False

            def __init__(self, viewer: TaskViewer) -> None:
                self.viewer = viewer

            def is_open(self) -> bool:
                return True

            def close(self) -> None:
                type(self).close_called = True

            def wait_closed(self, timeout: float | None = None) -> None:
                type(self).wait_closed_called = True

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
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.ViewerController", FakeController),
                ):
                    gestate_commands.gestate(
                        str(parent.id), tool="claude", max_rounds=1, run=True
                    )

        self.assertTrue(FakeController.close_called)
        self.assertTrue(FakeController.wait_closed_called)

    def test_gestate_auto_run_hands_off_open_viewer(self) -> None:
        class FakeController:
            close_called = False
            wait_closed_called = False

            def __init__(self, viewer: TaskViewer) -> None:
                self.viewer = viewer

            def is_open(self) -> bool:
                return True

            def close(self) -> None:
                type(self).close_called = True

            def wait_closed(self, timeout: float | None = None) -> None:
                type(self).wait_closed_called = True

        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.ViewerController", FakeController),
                    patch(
                        "fa.gestate.commands._run_runnable_task_tree",
                        return_value=0,
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
        self.assertTrue(run_tree.call_args.kwargs["open_viewer"])
        self.assertTrue(FakeController.close_called)
        self.assertTrue(FakeController.wait_closed_called)

    def test_gestate_auto_run_does_not_handoff_when_viewer_closed(self) -> None:
        class FakeController:
            close_called = False

            def __init__(self, viewer: TaskViewer) -> None:
                self.viewer = viewer

            def is_open(self) -> bool:
                return False

            def close(self) -> None:
                type(self).close_called = True

            def wait_closed(self, timeout: float | None = None) -> None:
                pass

        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.ViewerController", FakeController),
                    patch(
                        "fa.gestate.commands._run_runnable_task_tree",
                        return_value=0,
                    ) as run_tree,
                ):
                    gestate_commands.gestate(
                        str(task.id), tool="claude", max_rounds=1, run=True
                    )

        run_tree.assert_called_once()
        self.assertFalse(run_tree.call_args.kwargs["open_viewer"])
        self.assertFalse(FakeController.close_called)

    def test_gestate_auto_run_does_not_handoff_to_non_streaming_run_tool(self) -> None:
        class FakeController:
            close_called = False
            wait_closed_called = False

            def __init__(self, viewer: TaskViewer) -> None:
                self.viewer = viewer

            def is_open(self) -> bool:
                return True

            def close(self) -> None:
                type(self).close_called = True

            def wait_closed(self, timeout: float | None = None) -> None:
                type(self).wait_closed_called = True

        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.ViewerController", FakeController),
                    patch(
                        "fa.gestate.commands._run_runnable_task_tree",
                        return_value=0,
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
        self.assertFalse(run_tree.call_args.kwargs["open_viewer"])
        self.assertTrue(FakeController.close_called)
        self.assertTrue(FakeController.wait_closed_called)

    def test_gestate_auto_run_hands_off_to_codex_viewer(self) -> None:
        class FakeController:
            close_called = False
            wait_closed_called = False

            def __init__(self, viewer: TaskViewer) -> None:
                self.viewer = viewer

            def is_open(self) -> bool:
                return True

            def close(self) -> None:
                type(self).close_called = True

            def wait_closed(self, timeout: float | None = None) -> None:
                type(self).wait_closed_called = True

        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=0,
                    ),
                    patch("fa.gestate.commands.ViewerController", FakeController),
                    patch(
                        "fa.gestate.commands._run_runnable_task_tree",
                        return_value=0,
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
        self.assertTrue(run_tree.call_args.kwargs["open_viewer"])
        self.assertTrue(FakeController.close_called)
        self.assertTrue(FakeController.wait_closed_called)

    def test_gestate_no_run_skips_auto_run(self) -> None:
        result, run_tree = self._invoke_gestate_for_auto_run("--no-run")

        self.assertEqual(result.exit_code, 0, result.output)
        run_tree.assert_not_called()
