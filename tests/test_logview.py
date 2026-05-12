import io
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core.logview import (
    _RESET,
    Entry,
    TaskViewer,
    ViewerController,
    _truncate_to_visible,
    parse_codex_line,
    parse_jsonl_line,
)


class TruncateToVisibleTests(unittest.TestCase):
    def test_plain_text_truncation(self) -> None:
        self.assertEqual(_truncate_to_visible("hello world", 5), "hello")

    def test_preserves_complete_ansi_sequence_and_resets_open_style(self) -> None:
        self.assertEqual(
            _truncate_to_visible("\033[31mhello\033[0m", 3),
            "\033[31mhel\033[0m",
        )

    def test_closing_foreground_prevents_extra_reset(self) -> None:
        self.assertEqual(
            _truncate_to_visible("\033[31mred\033[39m plain", 6),
            "\033[31mred\033[39m pl",
        )

    def test_reset_plus_style_counts_as_open_style(self) -> None:
        self.assertEqual(
            _truncate_to_visible("\033[0;31mhello", 3),
            "\033[0;31mhel\033[0m",
        )

    def test_incomplete_ansi_sequence_is_not_emitted(self) -> None:
        self.assertEqual(_truncate_to_visible("abc\033[31", 10), "abc")

    def test_escape_sequence_after_visible_limit_is_not_emitted(self) -> None:
        self.assertEqual(_truncate_to_visible("abc\033[31m", 3), "abc")

    def test_extended_foreground_color_resets_when_truncated(self) -> None:
        self.assertEqual(
            _truncate_to_visible("\033[38;5;196mabcdef", 3),
            f"\033[38;5;196mabc{_RESET}",
        )


class ResultFormattingTests(unittest.TestCase):
    def test_result_message_is_not_truncated(self) -> None:
        long_result = "x" * 5000
        line = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 1000,
                "result": long_result,
            }
        )

        formatted = parse_jsonl_line(line)

        if formatted is None:
            self.fail("Expected result message to be formatted")
        self.assertIn(long_result, formatted)
        self.assertTrue(formatted.endswith(long_result))


class CodexFormattingTests(unittest.TestCase):
    def test_codex_metadata_renders_compact_header(self) -> None:
        result = parse_codex_line("OpenAI Codex v0.125.0 (research preview)", {})

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("[codex]", result)
        self.assertIn("OpenAI Codex v0.125.0", result)

    def test_codex_suppresses_user_prompt_body(self) -> None:
        state: dict[str, str] = {}

        self.assertIsNone(parse_codex_line("user", state))
        self.assertIsNone(parse_codex_line("# Task Information", state))

    def test_codex_formats_assistant_text(self) -> None:
        state: dict[str, str] = {}

        parse_codex_line("codex", state)
        result = parse_codex_line("I’ll inspect the code now.", state)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("[codex]", result)
        self.assertIn("inspect the code", result)

    def test_codex_formats_exec_command_and_success(self) -> None:
        state: dict[str, str] = {}

        parse_codex_line("exec", state)
        command = parse_codex_line(
            '/usr/bin/zsh -lc "pytest" in /home/alice/Workspace/fa', state
        )
        success = parse_codex_line(" succeeded in 0ms:", state)

        self.assertIsNotNone(command)
        self.assertIsNotNone(success)
        assert command is not None
        assert success is not None
        self.assertIn("[tool: exec]", command)
        self.assertIn("pytest", command)
        self.assertIn("[exec succeeded]", success)

    def test_codex_formats_exec_success_after_codex_marker(self) -> None:
        state: dict[str, str] = {}

        parse_codex_line("exec", state)
        parse_codex_line('/usr/bin/zsh -lc "pytest" in /home/alice/Workspace/fa', state)
        parse_codex_line("codex", state)
        success = parse_codex_line(" succeeded in 0ms:", state)

        self.assertIsNotNone(success)
        assert success is not None
        self.assertIn("[exec succeeded]", success)
        self.assertNotIn("[codex]", success)

    def test_codex_preserves_exec_output_until_next_role_marker(self) -> None:
        state: dict[str, str] = {}

        parse_codex_line("exec", state)
        parse_codex_line('/usr/bin/zsh -lc "pytest" in /home/alice/Workspace/fa', state)
        parse_codex_line(" succeeded in 0ms:", state)
        output = parse_codex_line("all passed", state)
        parse_codex_line("codex", state)
        done = parse_codex_line("Done.", state)

        self.assertIsNotNone(output)
        self.assertIsNotNone(done)
        assert output is not None
        assert done is not None
        self.assertIn("all passed", output)
        self.assertNotIn("[codex]", output)
        self.assertIn("[codex]", done)
        self.assertIn("Done.", done)

    def test_task_viewer_drains_codex_log_with_codex_parser(self) -> None:
        with TemporaryDirectory() as tempdir:
            log_path = Path(tempdir) / "round.log"
            log_path.write_text(
                "\n".join(
                    [
                        "OpenAI Codex v0.125.0 (research preview)",
                        "user",
                        "hidden prompt",
                        "codex",
                        "I’ll inspect the code now.",
                        "exec",
                        '/usr/bin/zsh -lc "pytest" in /home/alice/Workspace/fa',
                        "codex",
                        " succeeded in 0ms:",
                        "all passed",
                        "codex",
                        "Done.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            viewer = TaskViewer("task", total_rounds=1, tool="codex")
            viewer.start_round(1, log_path)
            viewer._drain_current_log()

        entries = "\n".join(entry.text for entry in viewer._entries)
        self.assertIn("[codex]", entries)
        self.assertIn("inspect the code", entries)
        self.assertIn("[tool: exec]", entries)
        self.assertIn("[exec succeeded]", entries)
        self.assertIn("all passed", entries)
        self.assertIn("Done.", entries)
        self.assertNotIn("hidden prompt", entries)


class TaskViewerStateTests(unittest.TestCase):
    def test_request_close_sets_close_requested(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)

        viewer.request_close()

        self.assertTrue(viewer._close_requested.is_set())

    def test_start_round_preserves_previous_round_entries_and_scroll(self) -> None:
        viewer = TaskViewer("task", total_rounds=2)
        viewer.start_round(1, Path("round-1.log"))
        viewer._entries.append(Entry(round_index=1, text="old output"))
        viewer._scroll_offset = 5

        viewer.start_round(2, Path("round-2.log"))

        self.assertEqual(viewer._current_round, 2)
        self.assertEqual(viewer._current_log, Path("round-2.log"))
        self.assertEqual(viewer._scroll_offset, 6)
        self.assertEqual(len(viewer._entries), 3)
        self.assertIn("Round 1/2 started", viewer._entries[0].text)
        self.assertEqual(viewer._entries[1].text, "old output")
        self.assertIn("Round 2/2 started", viewer._entries[2].text)

    def test_start_round_preserves_scroll_when_new_log_file_has_no_output_yet(
        self,
    ) -> None:
        viewer = TaskViewer("task", total_rounds=2)
        viewer.start_round(1, Path("round-1.log"))
        viewer._entries.append(Entry(round_index=1, text="old output"))
        viewer._scroll_offset = 2

        viewer.start_round(2, Path("missing-round-2.log"))

        self.assertEqual(viewer._scroll_offset, 3)
        self.assertIn("Round 1/2 started", viewer._entries[0].text)
        self.assertEqual(viewer._entries[1].text, "old output")
        self.assertIn("Round 2/2 started", viewer._entries[2].text)
        lines = viewer._render_body_lines_from(viewer._entries, 80, is_waiting=True)
        joined = "\n".join(lines)
        self.assertIn("old output", joined)
        self.assertIn("Round 2/2 started", joined)
        self.assertIn("Waiting for agent output", joined)

    def test_body_lines_include_entries_from_all_rounds(self) -> None:
        viewer = TaskViewer("task", total_rounds=2)
        viewer.start_round(1, Path("round-1.log"))
        viewer._entries.append(Entry(round_index=1, text="round one output"))
        viewer.end_round(1.0)
        viewer.start_round(2, Path("round-2.log"))
        viewer._entries.append(Entry(round_index=2, text="round two output"))

        lines = viewer._render_body_lines_from(viewer._entries, 80, is_waiting=False)

        joined = "\n".join(lines)
        self.assertIn("Round 1/2 started", joined)
        self.assertIn("round one output", joined)
        self.assertIn("Round 1/2 completed", joined)
        self.assertIn("Round 2/2 started", joined)
        self.assertIn("round two output", joined)
        self.assertEqual(viewer._current_round, 2)
        self.assertEqual(viewer._current_log, Path("round-2.log"))

    def test_viewer_persists_round_markers_and_parsed_entries(self) -> None:
        with TemporaryDirectory() as tempdir:
            raw_log = Path(tempdir) / "round-1-claude.log"
            viewer_log = Path(tempdir) / "round-1-claude-viewer.log"
            raw_log.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "text", "text": "hello from agent"}
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            viewer = TaskViewer("task", total_rounds=1, tool="claude")
            viewer.start_round(1, raw_log, viewer_log)
            viewer._drain_current_log()
            viewer.end_round(0.1)

            persisted = viewer_log.read_text(encoding="utf-8")

        self.assertIn("Round 1/1 started", persisted)
        self.assertIn("hello from agent", persisted)
        self.assertIn("Round 1/1 completed", persisted)
        self.assertNotIn("\x1b[", persisted)

    def test_body_lines_truncate_by_visible_width(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)
        entries = [Entry(round_index=1, text="\033[31mabcdef")]

        self.assertEqual(
            viewer._render_body_lines_from(entries, 3, is_waiting=False),
            [f"\033[31mabc{_RESET}"],
        )

    def test_body_lines_include_ansi_safe_waiting_line(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)

        lines = viewer._render_body_lines_from([], 10, is_waiting=True)

        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("\033[33mWaiting f"))
        self.assertTrue(lines[0].endswith(_RESET))

    def test_render_suppresses_chrome_on_tiny_terminal(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)
        viewer.start_round(1, Path("round-1.log"))
        viewer._entries = [Entry(round_index=1, text="body line")]
        viewer.mark_done()

        stdout = io.StringIO()
        with (
            patch("fa.core.logview.shutil.get_terminal_size", return_value=(80, 2)),
            patch("fa.core.logview.sys.stdout", stdout),
        ):
            viewer._render()

        output = stdout.getvalue()
        self.assertEqual(output, "\033[H\033[Jbody line")


class ViewerControllerTests(unittest.TestCase):
    def test_open_does_not_start_duplicate_thread(self) -> None:
        viewer_started = threading.Event()
        release_viewer = threading.Event()
        viewer = TaskViewer("task", total_rounds=1)
        controller = ViewerController(viewer)

        def fake_run() -> None:
            viewer_started.set()
            release_viewer.wait(timeout=1)

        with patch.object(viewer, "run", side_effect=fake_run) as run_viewer:
            try:
                controller.open()
                self.assertTrue(viewer_started.wait(timeout=1))
                controller.open()

                self.assertEqual(run_viewer.call_count, 1)
                self.assertTrue(controller.is_open())
            finally:
                release_viewer.set()
                controller.wait_closed(timeout=1)

        self.assertFalse(controller.is_open())

    def test_close_requests_viewer_close(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)
        controller = ViewerController(viewer)

        controller.close()

        self.assertTrue(viewer._close_requested.is_set())

    def test_open_reopens_after_viewer_exits(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)
        controller = ViewerController(viewer)

        with patch.object(viewer, "run") as run_viewer:
            controller.open()
            deadline = time.monotonic() + 1
            while controller.is_open() and time.monotonic() < deadline:
                time.sleep(0.01)
            controller.open()
            controller.wait_closed(timeout=1)

        self.assertEqual(run_viewer.call_count, 2)


if __name__ == "__main__":
    unittest.main()
