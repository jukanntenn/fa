import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fa.core.logview import TaskViewer, ViewerController
from fa.gestate import commands as gestate_commands


class GestateRunnerTests(unittest.TestCase):
    def test_non_stream_runner_uses_subprocess_run_without_viewer(self) -> None:
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

        self.assertEqual(result, 0)
        self.assertIsNone(run.call_args.kwargs["input"])

    def test_runner_returns_none_when_tool_execution_raises_oserror(self) -> None:
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
            log_path = Path(tempdir) / "round.log"
            with (
                patch("fa.gestate.runner.sys.stdin.isatty", return_value=False),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=fake_process,
                ),
            ):
                result = gestate_commands._run_tool_with_optional_viewer(
                    tool="claude",
                    prompt="hello",
                    log_path=log_path,
                    logger=Mock(),
                    viewer=viewer,
                    round_index=1,
                )
            persisted = log_path.with_name("round-viewer.log").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result, 0)
        self.assertEqual(fake_process.input, "hello")
        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("Round 1/1 started", entries)
        self.assertIn("Round 1/1 completed", entries)
        self.assertIn("Round 1/1 started", persisted)
        self.assertIn("Round 1/1 completed", persisted)

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
            log_path = Path(tempdir) / "round.log"
            with (
                patch("fa.gestate.runner.sys.stdin.isatty", return_value=False),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=fake_process,
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
            persisted = log_path.with_name("round-viewer.log").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result, 0)
        self.assertIsNone(fake_process.input)
        self.assertIn("hello", popen.call_args.args[0])
        self.assertIs(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("Round 1/1 started", entries)
        self.assertIn("Round 1/1 completed", entries)
        self.assertIn("Round 1/1 started", persisted)
        self.assertIn("Round 1/1 completed", persisted)

    def test_stream_runner_records_failed_round_when_popen_raises_oserror(self) -> None:
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
                patch("fa.gestate.runner.sys.stdin.isatty", return_value=True),
                patch(
                    "fa.gestate.commands.subprocess.Popen",
                    return_value=FakeProcess(),
                ),
                patch(
                    "fa.gestate.runner._read_main_session_key",
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
