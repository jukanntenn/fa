import logging
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.task import runner, storage


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = 0
        self.release = threading.Event()
        self.wait_started = threading.Event()
        self.finished = threading.Event()

    def wait(self) -> int:
        self.wait_started.set()
        self.release.wait(timeout=1)
        self.finished.set()
        return self.returncode


class TaskRunnerInteractiveViewerTests(unittest.TestCase):
    def _create_approved_task(self, tempdir: str):
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")
            task.transition_to("approved")
            storage.save_task(task)
            return task

    def test_open_viewer_true_opens_controller_without_ctrl_l(self) -> None:
        fake_process = FakeProcess()
        controllers = []

        class FakeController:
            def __init__(self, viewer) -> None:
                self.viewer = viewer
                self.open_count = 0
                self.wait_closed_timeout = None
                controllers.append(self)

            def open(self) -> None:
                self.open_count += 1

            def is_open(self) -> bool:
                return False

            def wait_closed(self, timeout=None) -> None:
                self.wait_closed_timeout = timeout

        def fake_read_key():
            fake_process.release.set()
            return None

        with TemporaryDirectory() as tempdir:
            task = self._create_approved_task(tempdir)
            log_dir = Path(tempdir) / "logs"
            with (
                patch.object(storage, "find_project_root", return_value=Path(tempdir)),
                patch("fa.task.runner.sys.stdin.isatty", return_value=True),
                patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
                patch("fa.task.runner.ViewerController", FakeController),
                patch(
                    "fa.task.runner._read_main_session_key", side_effect=fake_read_key
                ),
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
            ):
                result = runner._run_task_interactive(
                    task=task,
                    parent=None,
                    tool="claude",
                    rounds=1,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                    open_viewer=True,
                )

        self.assertFalse(result)
        self.assertEqual(controllers[0].open_count, 1)
        self.assertIsNone(controllers[0].wait_closed_timeout)

    def test_ctrl_l_opens_viewer_and_main_loop_pauses_while_open(self) -> None:
        fake_process = FakeProcess()
        read_count = 0
        controllers = []

        class FakeController:
            def __init__(self, viewer) -> None:
                self.viewer = viewer
                self.opened = False
                self.open_count = 0
                self.open_seen_count = 0
                controllers.append(self)

            def open(self) -> None:
                self.opened = True
                self.open_count += 1

            def is_open(self) -> bool:
                if not self.opened:
                    return False
                self.open_seen_count += 1
                if self.open_seen_count == 1:
                    fake_process.release.set()
                    return True
                self.opened = False
                return False

            def wait_closed(self, timeout=None) -> None:
                pass

        def fake_read_key():
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                return "\x0c"
            self.fail("read key called while viewer should be open")

        with TemporaryDirectory() as tempdir:
            task = self._create_approved_task(tempdir)
            log_dir = Path(tempdir) / "logs"
            with (
                patch.object(storage, "find_project_root", return_value=Path(tempdir)),
                patch("fa.task.runner.sys.stdin.isatty", return_value=True),
                patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
                patch("fa.task.runner.ViewerController", FakeController),
                patch(
                    "fa.task.runner._read_main_session_key", side_effect=fake_read_key
                ),
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
            ):
                result = runner._run_task_interactive(
                    task=task,
                    parent=None,
                    tool="claude",
                    rounds=1,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                )

        self.assertFalse(result)
        self.assertEqual(read_count, 1)
        self.assertEqual(controllers[0].open_count, 1)

    def test_ctrl_l_reopens_after_viewer_closes(self) -> None:
        fake_process = FakeProcess()
        read_count = 0
        controllers = []

        class FakeController:
            def __init__(self, viewer) -> None:
                self.viewer = viewer
                self.open_count = 0
                self.wait_closed_called = False
                controllers.append(self)

            def open(self) -> None:
                self.open_count += 1

            def is_open(self) -> bool:
                return False

            def wait_closed(self, timeout=None) -> None:
                self.wait_closed_called = True

        def fake_read_key():
            nonlocal read_count
            read_count += 1
            if read_count in {1, 2}:
                return "\x0c"
            if read_count == 3:
                self.assertTrue(fake_process.wait_started.wait(timeout=1))
                fake_process.release.set()
                self.assertTrue(fake_process.finished.wait(timeout=1))
                time.sleep(0.01)
                return None
            return None

        with TemporaryDirectory() as tempdir:
            task = self._create_approved_task(tempdir)
            log_dir = Path(tempdir) / "logs"
            with (
                patch.object(storage, "find_project_root", return_value=Path(tempdir)),
                patch("fa.task.runner.sys.stdin.isatty", return_value=True),
                patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
                patch("fa.task.runner.ViewerController", FakeController),
                patch(
                    "fa.task.runner._read_main_session_key", side_effect=fake_read_key
                ),
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
            ):
                result = runner._run_task_interactive(
                    task=task,
                    parent=None,
                    tool="claude",
                    rounds=1,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                    open_viewer=False,
                )

        self.assertFalse(result)
        self.assertEqual(read_count, 3)
        self.assertEqual(controllers[0].open_count, 2)
        self.assertTrue(controllers[0].wait_closed_called)

    def test_run_task_interactive_passes_codex_tool_to_task_viewer(self) -> None:
        fake_process = FakeProcess()
        fake_process.release.set()
        viewer_tools = []

        class FakeViewer:
            def __init__(
                self, slug: str, total_rounds: int, tool: str = "claude"
            ) -> None:
                viewer_tools.append(tool)

            def start_round(self, round_index: int, log_path: Path) -> None:
                pass

            def end_round(self, duration: float) -> None:
                pass

            def mark_done(self) -> None:
                pass

            def mark_failed(self) -> None:
                pass

            def _drain_current_log(self) -> None:
                pass

        class FakeController:
            def __init__(self, viewer: FakeViewer) -> None:
                self.viewer = viewer

            def open(self) -> None:
                pass

            def is_open(self) -> bool:
                return False

            def wait_closed(self, timeout=None) -> None:
                pass

        with TemporaryDirectory() as tempdir:
            task = self._create_approved_task(tempdir)
            log_dir = Path(tempdir) / "logs"
            with (
                patch.object(storage, "find_project_root", return_value=Path(tempdir)),
                patch("fa.task.runner.sys.stdin.isatty", return_value=False),
                patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
                patch("fa.task.runner.TaskViewer", FakeViewer),
                patch("fa.task.runner.ViewerController", FakeController),
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
            ):
                result = runner._run_task_interactive(
                    task=task,
                    parent=None,
                    tool="codex",
                    rounds=1,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                )

        self.assertFalse(result)
        self.assertEqual(viewer_tools, ["codex"])


class TaskRunnerRunTasksTests(unittest.TestCase):
    def test_run_tasks_passes_open_viewer_only_to_first_interactive_task(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
                first = storage.create_task("first")
                second = storage.create_task("second")
                for task in (first, second):
                    (task.path / "spec.md").write_text("spec", encoding="utf-8")
                    (task.path / "plan.md").write_text("plan", encoding="utf-8")
                    task.transition_to("approved")
                    storage.save_task(task)

                with (
                    patch("fa.task.runner.build_task_prompt", return_value="prompt"),
                    patch(
                        "fa.task.runner._run_task_interactive", return_value=False
                    ) as run_interactive,
                ):
                    result = runner.run_tasks(
                        logger=logging.getLogger("test"),
                        ids=[first.id, second.id],
                        force=False,
                        tool="claude",
                        rounds=1,
                        glm_plan=False,
                        attempt_mode=False,
                        open_viewer=True,
                    )

        self.assertEqual(result, 0)
        self.assertEqual(run_interactive.call_count, 2)
        self.assertTrue(run_interactive.call_args_list[0].kwargs["open_viewer"])
        self.assertFalse(run_interactive.call_args_list[1].kwargs["open_viewer"])

    def test_run_tasks_uses_interactive_viewer_for_codex(self) -> None:
        with TemporaryDirectory() as tempdir:
            with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
                task = storage.create_task("single")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                task.transition_to("approved")
                storage.save_task(task)

                with (
                    patch("fa.task.runner.build_task_prompt", return_value="prompt"),
                    patch(
                        "fa.task.runner._run_task_interactive",
                        return_value=False,
                    ) as run_interactive,
                ):
                    result = runner.run_tasks(
                        logger=logging.getLogger("test"),
                        ids=[task.id],
                        force=False,
                        tool="codex",
                        rounds=1,
                        glm_plan=False,
                        attempt_mode=False,
                        open_viewer=True,
                    )

        self.assertEqual(result, 0)
        run_interactive.assert_called_once()
        self.assertEqual(run_interactive.call_args.kwargs["tool"], "codex")
        self.assertTrue(run_interactive.call_args.kwargs["open_viewer"])


if __name__ == "__main__":
    unittest.main()
