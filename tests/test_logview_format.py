from __future__ import annotations

from fa.core.logview_parse import _format_content_item, _format_tool_result


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
