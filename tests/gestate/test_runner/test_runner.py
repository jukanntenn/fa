import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fa.core.logview import TaskViewer, ViewerController
from fa.gestate import commands as gestate_commands


def test_non_stream_runner_uses_subprocess_run_without_viewer() -> None:
    viewer = TaskViewer("gestate", total_rounds=1, tool="opencode")
    with TemporaryDirectory() as tempdir:
        with patch("fa.gestate.runner.subprocess.run") as run:
            run.return_value.returncode = 0

            result = gestate_commands._run_tool_with_optional_viewer(
                tool="opencode",
                prompt="hello",
                log_path=Path(tempdir) / "run.log",
                logger=Mock(),
                viewer=viewer,
                round_index=1,
            )

    assert result == 0
    assert run.call_args.kwargs["input"] is None


def test_runner_returns_none_when_tool_execution_raises_oserror() -> None:
    with TemporaryDirectory() as tempdir:
        with patch("fa.gestate.runner.subprocess.run", side_effect=OSError):
            result = gestate_commands._run_tool_with_optional_viewer(
                tool="codex",
                prompt="hello",
                log_path=Path(tempdir) / "run.log",
                logger=Mock(),
                viewer=None,
                round_index=1,
            )

    assert result is None


def test_stream_runner_starts_and_ends_viewer_round_when_not_tty() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0
            self.input: str | None = None

        def communicate(self, input: str | None = None) -> None:
            self.input = input

    fake_process = FakeProcess()
    viewer = TaskViewer("gestate", total_rounds=1)
    with TemporaryDirectory() as tempdir:
        log_path = Path(tempdir) / "round.log"
        with (
            patch("fa.gestate.runner.sys.stdin.isatty", return_value=False),
            patch("fa.gestate.runner.subprocess.Popen", return_value=fake_process),
        ):
            result = gestate_commands._run_tool_with_optional_viewer(
                tool="claude",
                prompt="hello",
                log_path=log_path,
                logger=Mock(),
                viewer=viewer,
                round_index=1,
            )
        persisted = log_path.with_name("round-viewer.log").read_text(encoding="utf-8")

    assert result == 0
    assert fake_process.input == "hello"
    entries = "\n".join(entry.text for entry in viewer._entries)
    assert "Round 1/1 started" in entries
    assert "Round 1/1 completed" in entries
    assert "Round 1/1 started" in persisted
    assert "Round 1/1 completed" in persisted


def test_codex_runner_starts_and_ends_viewer_round_when_not_tty() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0
            self.input: str | None = None

        def communicate(self, input: str | None = None) -> None:
            self.input = input

    fake_process = FakeProcess()
    viewer = TaskViewer("gestate", total_rounds=1, tool="codex")
    with TemporaryDirectory() as tempdir:
        log_path = Path(tempdir) / "round.log"
        with (
            patch("fa.gestate.runner.sys.stdin.isatty", return_value=False),
            patch(
                "fa.gestate.runner.subprocess.Popen", return_value=fake_process
            ) as popen,
        ):
            result = gestate_commands._run_tool_with_optional_viewer(
                tool="codex",
                prompt="hello",
                log_path=log_path,
                logger=Mock(),
                viewer=viewer,
                round_index=1,
            )
        persisted = log_path.with_name("round-viewer.log").read_text(encoding="utf-8")

    assert result == 0
    assert fake_process.input is None
    assert "hello" in popen.call_args.args[0]
    assert popen.call_args.kwargs["stdin"] is subprocess.DEVNULL
    entries = "\n".join(entry.text for entry in viewer._entries)
    assert "Round 1/1 started" in entries
    assert "Round 1/1 completed" in entries
    assert "Round 1/1 started" in persisted
    assert "Round 1/1 completed" in persisted


def test_stream_runner_records_failed_round_when_popen_raises_oserror() -> None:
    viewer = TaskViewer("gestate", total_rounds=1)
    with TemporaryDirectory() as tempdir:
        with (
            patch("fa.gestate.runner.sys.stdin.isatty", return_value=False),
            patch("fa.gestate.runner.subprocess.Popen", side_effect=OSError),
        ):
            result = gestate_commands._run_tool_with_optional_viewer(
                tool="claude",
                prompt="hello",
                log_path=Path(tempdir) / "round.log",
                logger=Mock(),
                viewer=viewer,
                round_index=1,
            )

    assert result is None
    entries = "\n".join(entry.text for entry in viewer._entries)
    assert "Round 1/1 started" in entries
    assert "Round 1/1 completed" in entries


def test_viewer_controller_does_not_open_duplicate_thread() -> None:
    import threading

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
            assert viewer_started.wait(timeout=1)
            viewer_controller.open()
            assert run_viewer.call_count == 1
            assert viewer_controller.is_open()
        finally:
            release_viewer.set()
            deadline = time.monotonic() + 1
            while viewer_controller.is_open() and time.monotonic() < deadline:
                time.sleep(0.01)


def test_viewer_controller_reopens_after_viewer_exits() -> None:
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
        assert run_viewer.call_count == 2


def test_stream_runner_does_not_read_keys_while_viewer_is_open() -> None:
    import threading

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
            patch("fa.gestate.runner.sys.stdin.isatty", return_value=True),
            patch("fa.gestate.runner.subprocess.Popen", return_value=FakeProcess()),
            patch("fa.core.tty._read_main_session_key", side_effect=fake_read_key),
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

    assert result == 0
    assert read_count == 1
