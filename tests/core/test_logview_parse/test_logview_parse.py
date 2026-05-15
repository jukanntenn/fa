from __future__ import annotations

from fa.core.logview_parse import (
    _extract_text_content,
    _format_assistant,
    _format_content_item,
    _format_result,
    _format_tool_result,
    _format_user,
    _truncate_to_visible,
    parse_codex_line,
    parse_jsonl_line,
)


def test_extract_text_content_from_list():
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "text", "text": "World"},
    ]
    result = _extract_text_content(content)
    assert result == "Hello World"


def test_extract_text_content_ignores_non_text():
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "image", "text": "World"},
    ]
    result = _extract_text_content(content)
    assert result == "Hello"


def test_extract_text_content_string():
    result = _extract_text_content("Hello World")
    assert result == "Hello World"


def test_truncate_to_visible_returns_empty_for_zero():
    result = _truncate_to_visible("Hello World", 0)
    assert result == ""


def test_truncate_to_visible_returns_empty_for_negative():
    result = _truncate_to_visible("Hello World", -1)
    assert result == ""


def test_truncate_to_visible_truncates():
    result = _truncate_to_visible("Hello World", 5)
    assert result == "Hello"


def test_format_content_item_text_with_content():
    item = {"type": "text", "text": "Hello World"}
    result = _format_content_item(item)
    assert result is not None
    assert "Hello World" in result


def test_format_content_item_text_empty_returns_none():
    item = {"type": "text", "text": "   "}
    result = _format_content_item(item)
    assert result is None


def test_format_content_item_tool_use():
    item = {
        "type": "tool_use",
        "name": "Read",
        "input": {"file_path": "/tmp/test.txt"},
    }
    result = _format_content_item(item)
    assert result is not None
    assert "[tool: Read]" in result
    assert "/tmp/test.txt" in result


def test_format_content_item_thinking():
    item = {"type": "thinking", "thinking": "Let me think about this"}
    result = _format_content_item(item)
    assert result is not None
    assert "[thinking...]" in result


def test_format_content_item_tool_result():
    item = {
        "type": "tool_result",
        "content": [{"type": "text", "text": "result content"}],
    }
    result = _format_content_item(item)
    assert result is not None
    assert "[tool result]" in result


def test_format_assistant_with_text_content():
    obj = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hello"}]},
    }
    result = _format_assistant(obj)
    assert result is not None
    assert "Hello" in result


def test_format_assistant_with_empty_content():
    obj = {"type": "assistant", "message": {"content": []}}
    result = _format_assistant(obj)
    assert result is None


def test_format_user_with_tool_result():
    obj = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": [{"type": "text", "text": "output"}]}
            ]
        },
    }
    result = _format_user(obj)
    assert result is not None
    assert "output" in result


def test_format_result_success():
    obj = {
        "type": "result",
        "subtype": "success",
        "result": "Task completed",
        "duration_ms": 1500,
    }
    result = _format_result(obj)
    assert "completed in 1.5s" in result
    assert "Task completed" in result


def test_format_result_failure():
    obj = {"type": "result", "subtype": "error", "result": "Task failed"}
    result = _format_result(obj)
    assert "[failed]" in result
    assert "Task failed" in result


def test_parse_jsonl_line_parses_assistant_message():
    import json

    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
    )
    result = parse_jsonl_line(line)
    assert result is not None
    assert "hi" in result


def test_parse_jsonl_line_returns_none_for_system():
    import json

    line = json.dumps({"type": "system", "content": "ignored"})
    result = parse_jsonl_line(line)
    assert result is None


def test_parse_jsonl_line_returns_raw_for_invalid_json():
    result = parse_jsonl_line("not valid json {")
    assert result is not None
    assert "[raw]" in result


def test_parse_jsonl_line_empty_returns_none():
    result = parse_jsonl_line("")
    assert result is None


def test_parse_jsonl_line_whitespace_returns_none():
    result = parse_jsonl_line("   \n\t  ")
    assert result is None


def test_parse_jsonl_line_unknown_type():
    import json

    line = json.dumps({"type": "custom_type", "data": "value"})
    result = parse_jsonl_line(line)
    assert result is not None
    assert "unknown" in result


def test_format_result_without_duration():
    obj = {"type": "result", "subtype": "success", "result": "Done"}
    result = _format_result(obj)
    assert "completed" in result
    assert "1.5s" not in result


def test_format_user_empty_content_returns_none():
    obj = {"type": "user", "message": {"content": []}}
    result = _format_user(obj)
    assert result is None


def test_truncate_preserves_newlines():
    from fa.core.logview_parse import _truncate

    result = _truncate("line1\nline2\nline3", 20, preserve_newlines=True)
    assert "\n" in result


def test_truncate_short_text():
    from fa.core.logview_parse import _truncate

    result = _truncate("short", 10)
    assert result == "short"


def test_truncate_long_text_truncates():
    from fa.core.logview_parse import _truncate

    result = _truncate("Hello World Example Text", 10)
    assert result == "Hello Worl..."


def test_strip_ansi():
    from fa.core.logview_parse import _strip_ansi

    result = _strip_ansi("\x1b[31mred\x1b[0m")
    assert result == "red"


def test_update_sgr_depth_bold_codes():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("1", 0)
    assert result == 1


def test_update_sgr_depth_38_256_color():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("38;5;196", 0)
    assert result == 1


def test_update_sgr_depth_38_rgb_color():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("38;2;255;0;0", 0)
    assert result == 1


def test_update_sgr_depth_48_color():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("48;5;21", 1)
    assert result == 2


def test_update_sgr_depth_resets_depth():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("0", 5)
    assert result == 0


def test_update_sgr_depth_decrements_for_certain_codes():
    from fa.core.logview_parse import _update_sgr_depth

    result = _update_sgr_depth("22", 3)
    assert result == 2


def test_parse_jsonl_line_user_type():
    import json

    line = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "content": [{"type": "text", "text": "output"}],
                    }
                ]
            },
        }
    )
    result = parse_jsonl_line(line)
    assert result is not None
    assert "output" in result


def test_parse_jsonl_line_result_type():
    import json

    line = json.dumps({"type": "result", "subtype": "success", "result": "Done"})
    result = parse_jsonl_line(line)
    assert result is not None
    assert "completed" in result


def test_truncate_to_visible_with_ansi_escape():
    result = _truncate_to_visible("\x1b[31mHello\x1b[0m World", 8)
    assert result is not None
    assert "Hello" in result


def test_truncate_to_visible_resets_sgr_on_truncation():
    result = _truncate_to_visible("\x1b[1m\x1b[31mHello World", 3)
    assert "\x1b[0m" in result


def test_format_content_item_unknown_type_returns_none():
    item = {"type": "image", "text": "data"}
    result = _format_content_item(item)
    assert result is None


def test_format_assistant_no_formattable_content():
    obj = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "   "}]},
    }
    result = _format_assistant(obj)
    assert result is None


def test_parse_codex_line_user_section_ignores_regular_text():
    state = {"section": "user"}
    result = parse_codex_line("just some user text", state)
    assert result is None


def test_tool_input_summary_edit():
    from fa.core.logview_parse import _tool_input_summary

    result = _tool_input_summary(
        "Edit", {"file_path": "/tmp/a.py", "old_string": "foo"}
    )
    assert "/tmp/a.py" in result
    assert "foo" in result


def test_tool_input_summary_bash():
    from fa.core.logview_parse import _tool_input_summary

    result = _tool_input_summary("Bash", {"command": "ls -la"})
    assert "ls -la" in result


def test_tool_input_summary_grep():
    from fa.core.logview_parse import _tool_input_summary

    result = _tool_input_summary("Grep", {"pattern": "TODO"})
    assert "TODO" in result


def test_tool_input_summary_generic():
    from fa.core.logview_parse import _tool_input_summary

    result = _tool_input_summary("Custom", {"a": 1, "b": 2})
    assert "a=..." in result


def test_format_content_item_thinking_empty():
    item = {"type": "thinking", "thinking": "   "}
    result = _format_content_item(item)
    assert result is None


def test_truncate_to_visible_truncated_ansi_sequence():
    result = _truncate_to_visible("\x1b[31", 5)
    assert result == ""


# ─── _format_tool_result / _format_content_item ────────────────
def test_format_tool_result():
    item = {"content": [{"type": "text", "text": "hello"}]}
    result = _format_tool_result(item)
    assert "[tool result]" in result
    assert "hello" in result


def test_format_tool_result_empty_content():
    item = {"content": []}
    result = _format_tool_result(item)
    assert "[tool result]" in result


def test_format_content_item_text():
    item = {"type": "text", "text": "hello"}
    result = _format_content_item(item)
    assert result is not None
    assert "hello" in result


def test_format_content_item_input():
    item = {"type": "input", "text": "hello"}
    result = _format_content_item(item)
    assert result is None
