from __future__ import annotations

from fa.nudge.runner import _find_json_objects


def test_empty_string():
    assert _find_json_objects("") == []


def test_no_braces():
    assert _find_json_objects("hello world") == []


def test_single_object():
    assert _find_json_objects('{"key": "value"}') == ['{"key": "value"}']


def test_multiple_objects():
    result = _find_json_objects('a {"x": 1} b {"y": 2} c')
    assert result == ['{"x": 1}', '{"y": 2}']


def test_nested_braces():
    result = _find_json_objects('{"a": {"b": 2}}')
    assert result == ['{"a": {"b": 2}}']


def test_brace_in_string():
    result = _find_json_objects('{"key": "val{ue"}')
    assert result == ['{"key": "val{ue"}']


def test_escaped_quote_in_string():
    result = _find_json_objects('{"key": "val\\"ue"}')
    assert result == ['{"key": "val\\"ue"}']


def test_incomplete_object():
    assert _find_json_objects('{"key":') == []


def test_adjacent_objects():
    result = _find_json_objects('{"a":1}{"b":2}')
    assert result == ['{"a":1}', '{"b":2}']


def test_brace_in_string_not_counted():
    result = _find_json_objects('{"k": "}{"}')
    assert result == ['{"k": "}{"}']
