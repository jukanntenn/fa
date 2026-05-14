from __future__ import annotations

import io
import json
import threading
import time
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


def test_truncate_preserves_newlines_when_requested() -> None:
    assert _truncate("alpha\nbeta", 20, preserve_newlines=True) == "alpha\nbeta"


def test_truncate_replaces_newlines_when_not_preserving() -> None:
    assert _truncate("alpha\nbeta", 20) == "alpha beta"


def test_truncate_short_input_both_modes() -> None:
    assert _truncate("a\nb", 10) == "a b"
    assert _truncate("a\nb", 10, preserve_newlines=True) == "a\nb"


def test_strip_ansi_removes_escape_sequences() -> None:
    assert _strip_ansi("\033[31mred\033[0m text") == "red text"


def test_strip_ansi_removes_sequences_without_surrounding_text() -> None:
    assert _strip_ansi("\x1b[31mred\x1b[0m") == "red"


def test_update_sgr_depth_resets_counter() -> None:
    depth = [0]
    _update_sgr_depth("1;31", depth)
    assert depth[0] == 2
    _update_sgr_depth("0", depth)
    assert depth[0] == 0


def test_update_sgr_depth_increments_and_decrements() -> None:
    depth = [0]
    _update_sgr_depth("1;31", depth)
    assert depth[0] == 2
    _update_sgr_depth("22;39", depth)
    assert depth[0] == 0


def test_parse_jsonl_line_returns_raw_line_for_invalid_json() -> None:
    assert parse_jsonl_line("not json") == "\x1b[2m[raw] not json\x1b[0m"


def test_parse_jsonl_line_returns_unknown_message_for_unknown_type() -> None:
    assert parse_jsonl_line('{"type":"mystery"}') == "\x1b[2m[unknown: mystery]\x1b[0m"


def test_parse_jsonl_line_returns_raw_contains_markers() -> None:
    result = parse_jsonl_line("not json")
    assert result is not None
    assert "[raw]" in result
    assert "not json" in result


def test_parse_jsonl_line_returns_unknown_contains_marker() -> None:
    result = parse_jsonl_line('{"type": "mystery"}')
    assert result is not None
    assert "[unknown: mystery]" in result


def test_tool_input_summary_formats_known_tool_inputs() -> None:
    assert _tool_input_summary("Read", {"file_path": "a.txt"}) == "a.txt"
    assert (
        _tool_input_summary(
            "Edit", {"file_path": "a.txt", "old_string": "x", "new_string": "y"}
        )
        == "a.txt: x"
    )
    assert _tool_input_summary("Write", {"file_path": "a.txt"}) == "a.txt"
    assert _tool_input_summary("Bash", {"command": "pytest -q"}) == "pytest -q"
    assert _tool_input_summary("Grep", {"pattern": "task"}) == "task"
    assert _tool_input_summary("Glob", {"pattern": "tests/*.py"}) == "tests/*.py"


def test_tool_input_summary_formats_common_inputs() -> None:
    assert _tool_input_summary("Read", {"file_path": "/tmp/x"}) == "/tmp/x"
    assert _tool_input_summary("Edit", {"file_path": "/tmp/x"}) == "/tmp/x: "
    assert _tool_input_summary("Write", {"file_path": "/tmp/x"}) == "/tmp/x"
    assert _tool_input_summary("Bash", {"command": "echo hi"}) == "echo hi"
    assert _tool_input_summary("Grep", {"pattern": "foo"}) == "foo"
    assert _tool_input_summary("Glob", {"pattern": "*.py"}) == "*.py"


def test_truncate_to_visible_plain_text_truncation() -> None:
    assert _truncate_to_visible("hello world", 5) == "hello"


def test_truncate_to_visible_preserves_complete_ansi_sequence_and_resets_open_style() -> (
    None
):
    assert _truncate_to_visible("\033[31mhello\033[0m", 3) == "\033[31mhel\033[0m"


def test_truncate_to_visible_closing_foreground_prevents_extra_reset() -> None:
    assert (
        _truncate_to_visible("\033[31mred\033[39m plain", 6) == "\033[31mred\033[39m pl"
    )


def test_truncate_to_visible_reset_plus_style_counts_as_open_style() -> None:
    assert _truncate_to_visible("\033[0;31mhello", 3) == "\033[0;31mhel\033[0m"


def test_truncate_to_visible_incomplete_ansi_sequence_is_not_emitted() -> None:
    assert _truncate_to_visible("abc\033[31", 10) == "abc"


def test_truncate_to_visible_escape_sequence_after_visible_limit_is_not_emitted() -> (
    None
):
    assert _truncate_to_visible("abc\033[31m", 3) == "abc"


def test_truncate_to_visible_extended_foreground_color_resets_when_truncated() -> None:
    assert (
        _truncate_to_visible("\033[38;5;196mabcdef", 3) == f"\033[38;5;196mabc{_RESET}"
    )


def test_result_message_is_not_truncated() -> None:
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

    assert formatted is not None
    assert long_result in formatted
    assert formatted.endswith(long_result)


def test_codex_metadata_renders_compact_header() -> None:
    result = parse_codex_line("OpenAI Codex v0.125.0 (research preview)", {})

    assert result is not None
    assert "[codex]" in result
    assert "OpenAI Codex v0.125.0" in result


def test_codex_suppresses_user_prompt_body() -> None:
    state: dict[str, str] = {}

    assert parse_codex_line("user", state) is None
    assert parse_codex_line("# Task Information", state) is None


def test_codex_formats_assistant_text() -> None:
    state: dict[str, str] = {}

    parse_codex_line("codex", state)
    result = parse_codex_line("I'll inspect the code now.", state)

    assert result is not None
    assert "[codex]" in result
    assert "inspect the code" in result


def test_codex_formats_exec_command_and_success() -> None:
    state: dict[str, str] = {}

    parse_codex_line("exec", state)
    command = parse_codex_line(
        '/usr/bin/zsh -lc "pytest" in /home/alice/Workspace/fa', state
    )
    success = parse_codex_line(" succeeded in 0ms:", state)

    assert command is not None
    assert success is not None
    assert "[tool: exec]" in command
    assert "pytest" in command
    assert "[exec succeeded]" in success


def test_codex_formats_exec_success_after_codex_marker() -> None:
    state: dict[str, str] = {}

    parse_codex_line("exec", state)
    parse_codex_line('python -c "print(1)"', state)
    result = parse_codex_line(" succeeded in 1ms:", state)

    assert result is not None
    assert "[exec succeeded]" in result


def test_viewer_reports_open_and_close_state() -> None:
    viewer = TaskViewer("task", total_rounds=1)

    assert not viewer._close_requested.is_set()
    assert not viewer._task_done.is_set()
    viewer.mark_done()
    assert viewer._task_done.is_set()
    viewer.request_close()
    assert viewer._close_requested.is_set()


def test_viewer_adds_round_markers_and_body_entries() -> None:
    viewer = TaskViewer("task", total_rounds=2)
    viewer.start_round(1, Path("round-1.log"))
    viewer._entries.append(Entry(round_index=1, text="round one output"))
    viewer.end_round(1.0)
    viewer.start_round(2, Path("round-2.log"))
    viewer._entries.append(Entry(round_index=2, text="round two output"))

    lines = viewer._render_body_lines_from(viewer._entries, 80, is_waiting=False)

    joined = "\n".join(lines)
    assert "Round 1/2 started" in joined
    assert "round one output" in joined
    assert "Round 1/2 completed" in joined
    assert "Round 2/2 started" in joined
    assert "round two output" in joined
    assert viewer._current_round == 2
    assert viewer._current_log == Path("round-2.log")


def test_viewer_persists_round_markers_and_parsed_entries() -> None:
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

    assert "Round 1/1 started" in persisted
    assert "hello from agent" in persisted
    assert "Round 1/1 completed" in persisted
    assert "\x1b[" not in persisted


def test_body_lines_truncate_by_visible_width() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    entries = [Entry(round_index=1, text="\033[31mabcdef")]

    assert viewer._render_body_lines_from(entries, 3, is_waiting=False) == [
        f"\033[31mabc{_RESET}"
    ]


def test_body_lines_include_ansi_safe_waiting_line() -> None:
    viewer = TaskViewer("task", total_rounds=1)

    lines = viewer._render_body_lines_from([], 10, is_waiting=True)

    assert len(lines) == 1
    assert lines[0].startswith("\033[33mWaiting f")
    assert lines[0].endswith(_RESET)


def test_render_suppresses_chrome_on_tiny_terminal() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, Path("round-1.log"))
    viewer._entries = [Entry(round_index=1, text="body line")]
    viewer.mark_done()

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 2)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert output == "\033[H\033[Jbody line"


def test_viewer_controller_open_does_not_start_duplicate_thread() -> None:
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
            assert viewer_started.wait(timeout=1)
            controller.open()

            assert run_viewer.call_count == 1
            assert controller.is_open()
        finally:
            release_viewer.set()
            controller.wait_closed(timeout=1)

    assert not controller.is_open()


def test_viewer_controller_close_requests_viewer_close() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)

    controller.close()

    assert viewer._close_requested.is_set()


def test_viewer_controller_open_reopens_after_viewer_exits() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)

    with patch.object(viewer, "run") as run_viewer:
        controller.open()
        deadline = time.monotonic() + 1
        while controller.is_open() and time.monotonic() < deadline:
            time.sleep(0.01)
        controller.open()
        controller.wait_closed(timeout=1)

    assert run_viewer.call_count == 2
