import logging
import threading
import time
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


def _create_approved_task(tempdir: str):
    with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
        task = storage.create_task("single")
        (task.path / "spec.md").write_text("spec", encoding="utf-8")
        (task.path / "plan.md").write_text("plan", encoding="utf-8")
        task.transition_to("approved")
        storage.save_task(task)
        return task


def test_open_viewer_true_opens_controller_without_ctrl_l() -> None:
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
        task = _create_approved_task(tempdir)
        log_dir = Path(tempdir) / "logs"
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.runner.sys.stdin.isatty", return_value=True),
            patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
            patch("fa.task.runner.ViewerController", FakeController),
            patch("fa.task.runner._read_main_session_key", side_effect=fake_read_key),
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

    assert not result
    assert controllers[0].open_count == 1
    assert controllers[0].wait_closed_timeout is None


def test_ctrl_l_opens_viewer_and_main_loop_pauses_while_open() -> None:
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
        raise AssertionError("read key called while viewer should be open")

    with TemporaryDirectory() as tempdir:
        task = _create_approved_task(tempdir)
        log_dir = Path(tempdir) / "logs"
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.runner.sys.stdin.isatty", return_value=True),
            patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
            patch("fa.task.runner.ViewerController", FakeController),
            patch("fa.task.runner._read_main_session_key", side_effect=fake_read_key),
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

    assert not result
    assert read_count == 1
    assert controllers[0].open_count == 1


def test_ctrl_l_reopens_after_viewer_closes() -> None:
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
            assert fake_process.wait_started.wait(timeout=1)
            fake_process.release.set()
            assert fake_process.finished.wait(timeout=1)
            time.sleep(0.01)
            return None
        return None

    with TemporaryDirectory() as tempdir:
        task = _create_approved_task(tempdir)
        log_dir = Path(tempdir) / "logs"
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.task.runner.sys.stdin.isatty", return_value=True),
            patch("fa.task.runner.subprocess.Popen", return_value=fake_process),
            patch("fa.task.runner.ViewerController", FakeController),
            patch("fa.task.runner._read_main_session_key", side_effect=fake_read_key),
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

    assert not result
    assert read_count == 3
    assert controllers[0].open_count == 2
    assert controllers[0].wait_closed_called


def test_run_task_interactive_passes_codex_tool_to_task_viewer() -> None:
    fake_process = FakeProcess()
    fake_process.release.set()
    viewer_tools = []
    viewer_log_paths = []

    class FakeViewer:
        def __init__(self, slug: str, total_rounds: int, tool: str = "claude") -> None:
            viewer_tools.append(tool)

        def start_round(
            self,
            round_index: int,
            log_path: Path,
            viewer_log_path: Path | None = None,
        ) -> None:
            viewer_log_paths.append(viewer_log_path)

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
        task = _create_approved_task(tempdir)
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

    assert not result
    assert viewer_tools == ["codex"]
    assert len(viewer_log_paths) == 1
    assert viewer_log_paths[0] is not None
    assert viewer_log_paths[0].name.endswith("-viewer.log")
