import io
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from fa.core.logview import TaskViewer, ViewerController
from fa.gestate import commands as gestate_commands


class GestatePromptTests(unittest.TestCase):
    def test_claude_prompt_uses_stdin_without_argv_prompt(self) -> None:
        prompt = "/gestating " + "x" * 10000

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
            "claude", prompt
        )

        self.assertEqual(prompt_stdin, prompt)
        self.assertNotEqual(cmd[-1], "-")
        self.assertNotEqual(cmd[-1], "")
        self.assertFalse(any(prompt in part for part in cmd))

    def test_ccr_prompt_uses_stdin_without_argv_prompt(self) -> None:
        prompt = "/gestating " + "x" * 10000

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("ccr", prompt)

        self.assertEqual(prompt_stdin, prompt)
        self.assertNotEqual(cmd[-1], "-")
        self.assertNotEqual(cmd[-1], "")
        self.assertFalse(any(prompt in part for part in cmd))

    def test_codex_keeps_existing_argv_prompt(self) -> None:
        prompt = "short prompt"

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

        self.assertIsNone(prompt_stdin)
        self.assertIn(prompt, cmd)

    def test_stream_prompt_removes_empty_placeholder_without_dropping_flags(
        self,
    ) -> None:
        with patch.object(
            gestate_commands,
            "TOOL_COMMANDS",
            {"claude": ["claude", "-p", "{prompt}", "--verbose"]},
        ):
            cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
                "claude", "hello"
            )

        self.assertEqual(prompt_stdin, "hello")
        self.assertEqual(cmd, ["claude", "-p", "--verbose"])

    def test_non_tty_read_stdin_preserves_full_text_except_outer_strip(self) -> None:
        class StdinStub(io.StringIO):
            def isatty(self) -> bool:
                return False

        text = "  line1\n" + "x" * 10000 + "\nline3  "
        with patch("fa.gestate.commands.sys.stdin", StdinStub(text)):
            result = gestate_commands._read_stdin()

        self.assertEqual(result, text.strip())


class GestateArtifactDiffTests(unittest.TestCase):
    def test_format_artifact_diff_reports_modified_created_and_deleted_files(
        self,
    ) -> None:
        before = {"spec.md": "old\n", "child/plan.md": "remove\n"}
        after = {"spec.md": "new\n", "child/new/plan.md": "add\n"}

        diff = gestate_commands._format_artifact_diff(before, after)

        self.assertIn("--- before/spec.md", diff)
        self.assertIn("+++ after/spec.md", diff)
        self.assertIn("-old", diff)
        self.assertIn("+new", diff)
        self.assertIn("--- before/child/plan.md", diff)
        self.assertIn("+++ after/child/plan.md", diff)
        self.assertIn("--- before/child/new/plan.md", diff)
        self.assertIn("+++ after/child/new/plan.md", diff)

    def test_capture_artifact_snapshot_only_reads_specs_and_plans(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "spec.md").write_text("spec", encoding="utf-8")
            (root / "plan.md").write_text("plan", encoding="utf-8")
            (root / "notes.txt").write_text("notes", encoding="utf-8")
            child = root / "child"
            child.mkdir()
            (child / "plan.md").write_text("child plan", encoding="utf-8")

            snapshot = gestate_commands._capture_artifact_snapshot(root)

        self.assertEqual(set(snapshot), {"spec.md", "plan.md", "child/plan.md"})

    def test_print_round_artifact_diff_reports_no_changes(self) -> None:
        with patch("fa.gestate.commands.typer.echo") as echo:
            gestate_commands._print_round_artifact_diff(
                2, {"spec.md": "same"}, {"spec.md": "same"}
            )

        echo.assert_called_with("Round 2: no artifact changes")

    def test_gestate_failed_tool_run_with_no_changes_prints_no_change_and_converges(
        self,
    ) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("demo")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=None,
                    ),
                    patch("fa.gestate.commands.typer.echo") as echo,
                ):
                    gestate_commands.gestate(
                        str(task.id), tool="codex", max_rounds=1, run=False
                    )

        echo.assert_any_call("Round 1: no artifact changes")
        echo.assert_any_call("Converged after 1 round(s)")

    def test_gestate_nonzero_tool_run_with_no_changes_prints_no_change_and_converges(
        self,
    ) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
                from fa.task.storage import create_task

                task = create_task("demo")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")

                with (
                    patch(
                        "fa.gestate.commands._run_tool_with_optional_viewer",
                        return_value=1,
                    ),
                    patch("fa.gestate.commands.typer.echo") as echo,
                ):
                    gestate_commands.gestate(
                        str(task.id), tool="codex", max_rounds=1, run=False
                    )

        echo.assert_any_call("Round 1: no artifact changes")
        echo.assert_any_call("Converged after 1 round(s)")


class GestateRunnerTests(unittest.TestCase):
    def test_non_stream_runner_uses_subprocess_run_without_viewer(self) -> None:
        viewer = TaskViewer("gestate", total_rounds=1, tool="opencode")
        with TemporaryDirectory() as tempdir:
            with patch("fa.gestate.commands.subprocess.run") as run:
                run.return_value.returncode = 0

                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="opencode",
                    prompt="hello",
                    log_path=Path(tempdir) / "run.log",
                    logger=Mock(),
                    viewer=viewer,
                    round_index=1,
                )

        self.assertEqual(result, 0)
        self.assertIsNone(run.call_args.kwargs["input"])

    def test_runner_returns_none_when_tool_execution_raises_oserror(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch("fa.gestate.commands.subprocess.run", side_effect=OSError):
                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="codex",
                    prompt="hello",
                    log_path=Path(tempdir) / "run.log",
                    logger=Mock(),
                    viewer=None,
                    round_index=1,
                )

        self.assertIsNone(result)

    def test_stream_runner_starts_and_ends_viewer_round_when_not_tty(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.returncode = 0
                self.input: str | None = None

            def communicate(self, input: str | None = None) -> None:
                self.input = input

        fake_process = FakeProcess()
        viewer = TaskViewer("gestate", total_rounds=1)
        with TemporaryDirectory() as tempdir:
            with (
                patch("fa.gestate.commands.sys.stdin.isatty", return_value=False),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=fake_process,
                ),
            ):
                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="claude",
                    prompt="hello",
                    log_path=Path(tempdir) / "round.log",
                    logger=Mock(),
                    viewer=viewer,
                    round_index=1,
                )

        self.assertEqual(result, 0)
        self.assertEqual(fake_process.input, "hello")
        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("Round 1/1 started", entries)
        self.assertIn("Round 1/1 completed", entries)

    def test_codex_runner_starts_and_ends_viewer_round_when_not_tty(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.returncode = 0
                self.input: str | None = None

            def communicate(self, input: str | None = None) -> None:
                self.input = input

        fake_process = FakeProcess()
        viewer = TaskViewer("gestate", total_rounds=1, tool="codex")
        with TemporaryDirectory() as tempdir:
            with (
                patch("fa.gestate.commands.sys.stdin.isatty", return_value=False),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=fake_process,
                ) as popen,
            ):
                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="codex",
                    prompt="hello",
                    log_path=Path(tempdir) / "round.log",
                    logger=Mock(),
                    viewer=viewer,
                    round_index=1,
                )

        self.assertEqual(result, 0)
        self.assertIsNone(fake_process.input)
        self.assertIn("hello", popen.call_args.args[0])
        self.assertIs(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("Round 1/1 started", entries)
        self.assertIn("Round 1/1 completed", entries)

    def test_stream_runner_records_failed_round_when_popen_raises_oserror(self) -> None:
        viewer = TaskViewer("gestate", total_rounds=1)
        with TemporaryDirectory() as tempdir:
            with (
                patch("fa.gestate.commands.sys.stdin.isatty", return_value=False),
                patch("fa.gestate.commands.subprocess.Popen", side_effect=OSError),
            ):
                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="claude",
                    prompt="hello",
                    log_path=Path(tempdir) / "round.log",
                    logger=Mock(),
                    viewer=viewer,
                    round_index=1,
                )

        self.assertIsNone(result)
        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("Round 1/1 started", entries)
        self.assertIn("Round 1/1 completed", entries)

    def test_viewer_controller_does_not_open_duplicate_thread(self) -> None:
        import threading
        from unittest.mock import patch

        viewer_started = threading.Event()
        release_viewer = threading.Event()

        viewer = TaskViewer("gestate", total_rounds=1)
        viewer_controller = ViewerController(viewer)

        def fake_viewer_run():
            viewer_started.set()
            release_viewer.wait(timeout=1)

        with patch.object(viewer, "run", side_effect=fake_viewer_run) as run_viewer:
            try:
                viewer_controller.open()
                self.assertTrue(viewer_started.wait(timeout=1))
                viewer_controller.open()
                self.assertEqual(run_viewer.call_count, 1)
                self.assertTrue(viewer_controller.is_open())
            finally:
                release_viewer.set()
                deadline = time.monotonic() + 1
                while viewer_controller.is_open() and time.monotonic() < deadline:
                    time.sleep(0.01)

    def test_viewer_controller_reopens_after_viewer_exits(self) -> None:
        from unittest.mock import patch

        viewer = TaskViewer("gestate", total_rounds=1)
        viewer_controller = ViewerController(viewer)

        with patch.object(viewer, "run") as run_viewer:
            viewer_controller.open()
            deadline = time.monotonic() + 1
            while viewer_controller.is_open() and time.monotonic() < deadline:
                time.sleep(0.01)
            viewer_controller.open()
            deadline = time.monotonic() + 1
            while viewer_controller.is_open() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(run_viewer.call_count, 2)

    def test_stream_runner_does_not_read_keys_while_viewer_is_open(self) -> None:
        import threading
        from unittest.mock import patch

        allow_process_exit = threading.Event()

        class FakeProcess:
            def __init__(self) -> None:
                self.returncode = 0

            def communicate(self, input=None):
                allow_process_exit.wait(timeout=0.5)

        viewer_started = threading.Event()
        release_viewer = threading.Event()

        viewer = TaskViewer("gestate", total_rounds=1)
        viewer_controller = ViewerController(viewer)

        read_count = 0

        def fake_viewer_run():
            viewer_started.set()
            release_viewer.wait(timeout=1)

        def fake_read_key():
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                return "\x0c"
            allow_process_exit.set()
            return "\x0c"

        with TemporaryDirectory() as tempdir:
            with (
                patch("fa.gestate.commands.sys.stdin.isatty", return_value=True),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=FakeProcess(),
                ),
                patch(
                    "fa.gestate.commands._read_main_session_key",
                    side_effect=fake_read_key,
                ),
                patch.object(viewer, "run", side_effect=fake_viewer_run),
            ):
                try:
                    result = gestate_commands._run_tool_with_optional_viewer(
                        tool="claude",
                        prompt="hello",
                        log_path=Path(tempdir) / "round.log",
                        logger=Mock(),
                        viewer=viewer,
                        round_index=1,
                        viewer_controller=viewer_controller,
                    )
                finally:
                    allow_process_exit.set()
                    release_viewer.set()
                    deadline = time.monotonic() + 1
                    while viewer_controller.is_open() and time.monotonic() < deadline:
                        time.sleep(0.01)

        self.assertEqual(result, 0)
        self.assertEqual(read_count, 1)


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
