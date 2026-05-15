from __future__ import annotations

import json

from fa.core.logview import parse_codex_line, parse_jsonl_line
from fa.core.logview_parse import (
    _RESET,
    _strip_ansi,
    _tool_input_summary,
    _truncate,
    _truncate_to_visible,
    _update_sgr_depth,
)


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
    depth = 0
    depth = _update_sgr_depth("1;31", depth)
    assert depth == 2
    depth = _update_sgr_depth("0", depth)
    assert depth == 0


def test_update_sgr_depth_increments_and_decrements() -> None:
    depth = 0
    depth = _update_sgr_depth("1;31", depth)
    assert depth == 2
    depth = _update_sgr_depth("22;39", depth)
    assert depth == 0


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


def test_tool_input_summary_fallback_for_unknown_tool() -> None:
    result = _tool_input_summary("UnknownTool", {"foo": "bar", "baz": "qux"})
    assert result == "foo=..., baz=..."


def test_tool_input_summary_fallback_for_missing_keys() -> None:
    result = _tool_input_summary("Read", {"other_key": "value"})
    assert result == "other_key=..."


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
