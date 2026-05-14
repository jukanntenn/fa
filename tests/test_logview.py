from __future__ import annotations

import io
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core.logview import parse_codex_line, parse_jsonl_line
from fa.core.logview_parse import (
    _RESET,
    _strip_ansi,
    _tool_input_summary,
    _truncate,
    _truncate_to_visible,
    _update_sgr_depth,
)
from fa.core.logview_viewer import Entry, TaskViewer, ViewerController


class LogviewParseHelperTests(unittest.TestCase):
    def test_truncate_preserves_newlines_when_requested(self) -> None:
        self.assertEqual(
            _truncate("alpha\nbeta", 20, preserve_newlines=True), "alpha\nbeta"
        )

    def test_truncate_replaces_newlines_when_not_preserving(self) -> None:
        self.assertEqual(_truncate("alpha\nbeta", 20), "alpha beta")

    def test_truncate_short_input_both_modes(self) -> None:
        self.assertEqual(_truncate("a\nb", 10), "a b")
        self.assertEqual(_truncate("a\nb", 10, preserve_newlines=True), "a\nb")

    def test_strip_ansi_removes_escape_sequences(self) -> None:
        self.assertEqual(_strip_ansi("\033[31mred\033[0m text"), "red text")

    def test_strip_ansi_removes_sequences_without_surrounding_text(self) -> None:
        self.assertEqual(_strip_ansi("\x1b[31mred\x1b[0m"), "red")

    def test_update_sgr_depth_resets_counter(self) -> None:
        depth = [0]
        _update_sgr_depth("1;31", depth)
        self.assertEqual(depth[0], 2)
        _update_sgr_depth("0", depth)
        self.assertEqual(depth[0], 0)

    def test_update_sgr_depth_increments_and_decrements(self) -> None:
        depth = [0]
        _update_sgr_depth("1;31", depth)
        self.assertEqual(depth[0], 2)
        _update_sgr_depth("22;39", depth)
        self.assertEqual(depth[0], 0)

    def test_parse_jsonl_line_returns_raw_line_for_invalid_json(self) -> None:
        self.assertEqual(parse_jsonl_line("not json"), "\x1b[2m[raw] not json\x1b[0m")

    def test_parse_jsonl_line_returns_unknown_message_for_unknown_type(self) -> None:
        self.assertEqual(
            parse_jsonl_line('{"type":"mystery"}'), "\x1b[2m[unknown: mystery]\x1b[0m"
        )

    def test_parse_jsonl_line_returns_raw_contains_markers(self) -> None:
        result = parse_jsonl_line("not json")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("[raw]", result)
        self.assertIn("not json", result)

    def test_parse_jsonl_line_returns_unknown_contains_marker(self) -> None:
        result = parse_jsonl_line('{"type": "mystery"}')
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("[unknown: mystery]", result)

    def test_tool_input_summary_formats_known_tool_inputs(self) -> None:
        self.assertEqual(_tool_input_summary("Read", {"file_path": "a.txt"}), "a.txt")
        self.assertEqual(
            _tool_input_summary(
                "Edit", {"file_path": "a.txt", "old_string": "x", "new_string": "y"}
            ),
            "a.txt: x",
        )
        self.assertEqual(_tool_input_summary("Write", {"file_path": "a.txt"}), "a.txt")
        self.assertEqual(
            _tool_input_summary("Bash", {"command": "pytest -q"}), "pytest -q"
        )
        self.assertEqual(_tool_input_summary("Grep", {"pattern": "task"}), "task")
        self.assertEqual(
            _tool_input_summary("Glob", {"pattern": "tests/*.py"}), "tests/*.py"
        )

    def test_tool_input_summary_formats_common_inputs(self) -> None:
        self.assertEqual(_tool_input_summary("Read", {"file_path": "/tmp/x"}), "/tmp/x")
        self.assertEqual(
            _tool_input_summary("Edit", {"file_path": "/tmp/x"}), "/tmp/x: "
        )
        self.assertEqual(
            _tool_input_summary("Write", {"file_path": "/tmp/x"}), "/tmp/x"
        )
        self.assertEqual(_tool_input_summary("Bash", {"command": "echo hi"}), "echo hi")
        self.assertEqual(_tool_input_summary("Grep", {"pattern": "foo"}), "foo")
        self.assertEqual(_tool_input_summary("Glob", {"pattern": "*.py"}), "*.py")


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
        parse_codex_line('python -c "print(1)"', state)
        result = parse_codex_line(" succeeded in 1ms:", state)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("[exec succeeded]", result)


class TaskViewerStateTests(unittest.TestCase):
    def test_viewer_reports_open_and_close_state(self) -> None:
        viewer = TaskViewer("task", total_rounds=1)

        self.assertFalse(viewer._close_requested.is_set())
        self.assertFalse(viewer._task_done.is_set())
        viewer.mark_done()
        self.assertTrue(viewer._task_done.is_set())
        viewer.request_close()
        self.assertTrue(viewer._close_requested.is_set())

    def test_viewer_adds_round_markers_and_body_entries(self) -> None:
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
                            "content": [{"type": "text", "text": "hello from agent"}]
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
            patch(
                "fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 2)
            ),
            patch("fa.core.logview_viewer.sys.stdout", stdout),
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
