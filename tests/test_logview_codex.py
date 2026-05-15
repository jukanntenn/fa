from __future__ import annotations

from fa.core.logview_parse import _reset_exec_state, parse_codex_line


def test_parse_codex_line_empty_returns_none():
    result = parse_codex_line("")
    assert result is None


def test_parse_codex_line_whitespace_returns_none():
    result = parse_codex_line("   \n")
    assert result is None


def test_parse_codex_line_section_user_sets_state():
    state = {}
    result = parse_codex_line("user", state)
    assert result is None
    assert state["section"] == "user"


def test_parse_codex_line_with_no_state_argument():
    result = parse_codex_line("user")
    assert result is None


def test_parse_codex_line_codex_section_sets_state():
    state = {}
    result = parse_codex_line("codex", state)
    assert result is None
    assert state["section"] == "codex"


def test_parse_codex_line_section_exec_sets_state():
    state = {}
    result = parse_codex_line("exec", state)
    assert result is None
    assert state["section"] == "exec"


def test_parse_codex_line_metadata_workdir_returns_none():
    state = {"section": "metadata"}
    result = parse_codex_line("workdir: /some/path", state)
    assert result is None


def test_parse_codex_line_openai_codex_header_sets_state_and_returns_formatted():
    state = {}
    result = parse_codex_line("OpenAI Codex v0.125.0 (research preview)", state)
    assert result is not None
    assert "[codex]" in result
    assert "OpenAI Codex v0.125.0" in result
    assert state["codex_header_seen"] == "1"


def test_parse_codex_line_exec_command_returns_truncated():
    state = {"section": "exec", "exec_command_seen": "0"}
    result = parse_codex_line("some command", state)
    assert result is not None
    assert "[tool: exec]" in result
    assert "some command" in result


def test_parse_codex_line_codex_section_returns_formatted():
    state = {"section": "codex"}
    result = parse_codex_line("some codex output", state)
    assert result is not None
    assert "[codex]" in result


def test_parse_codex_line_separator_returns_none():
    result = parse_codex_line("--------", {})
    assert result is None


def test_parse_codex_line_exec_output_success():
    state = {"section": "exec", "exec_command_seen": "1"}
    result = parse_codex_line(" succeeded in 0ms:", state)
    assert result is not None
    assert "[exec succeeded]" in result


def test_parse_codex_line_exec_output_failure():
    state = {"section": "exec", "exec_command_seen": "1"}
    result = parse_codex_line(" Failed: command returned error", state)
    assert result is not None
    assert "[exec failed]" in result


def test_parse_codex_line_exec_output_timed_out():
    state = {"section": "exec", "exec_command_seen": "1"}
    result = parse_codex_line(" operation timed out", state)
    assert result is not None
    assert "[exec failed]" in result


def test_parse_codex_line_exec_output_continuation():
    state = {"section": "exec", "exec_output_seen": "1"}
    result = parse_codex_line(" some output line", state)
    assert result is not None
    assert "some output line" in result


def test_parse_codex_line_user_section_suppresses_error():
    state = {"section": "user"}
    result = parse_codex_line("Error: something went wrong", state)
    assert result is not None
    assert "[codex error]" in result


def test_parse_codex_line_codex_section_formatted():
    state = {"section": "codex"}
    result = parse_codex_line("some output here", state)
    assert result is not None
    assert "[codex]" in result


def test_reset_exec_state_clears_exec_keys():
    state = {
        "section": "exec",
        "exec_command_seen": "1",
        "exec_output_seen": "1",
        "other": "value",
    }
    _reset_exec_state(state)
    assert "exec_command_seen" not in state
    assert "exec_output_seen" not in state
    assert state["other"] == "value"


def test_reset_exec_state_handles_missing_keys():
    state = {"section": "exec", "other": "value"}
    _reset_exec_state(state)
    assert state["other"] == "value"


def test_parse_codex_line_codex_section_resets_exec_output_state():
    state = {"exec_output_seen": "1"}
    result = parse_codex_line("codex", state)
    assert result is None
    assert "exec_output_seen" not in state


def test_parse_codex_line_duplicate_codex_header_returns_none():
    state = {"codex_header_seen": "1"}
    result = parse_codex_line("OpenAI Codex v0.125.0 (research preview)", state)
    assert result is None


def test_parse_codex_line_exec_output_neutral_continuation():
    state = {"section": "exec", "exec_command_seen": "1"}
    result = parse_codex_line(" regular output line", state)
    assert result is not None
    assert "regular output line" in result


def test_parse_codex_line_exec_second_command():
    state = {"section": "exec", "exec_command_seen": "1"}
    result = parse_codex_line("second command", state)
    assert result is not None


def test_parse_codex_line_default_metadata_non_matching_returns_none():
    state = {"section": "metadata"}
    result = parse_codex_line("some random text without colon", state)
    assert result is None


def test_parse_codex_line_user_section_ignores_regular_text():
    state = {"section": "user"}
    result = parse_codex_line("just some user text", state)
    assert result is None
