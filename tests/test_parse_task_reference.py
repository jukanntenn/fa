from __future__ import annotations

from pathlib import Path

from fa.gestate.tasks import _parse_task_reference


def test_parse_task_reference_with_malformed_json():
    text = "```json\n{invalid json}\n```"
    result = _parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_non_integer_task_id():
    text = '{"task_id": "not-an-int"}'
    result = _parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_missing_task_id():
    text = '{"some_field": "value"}'
    result = _parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_task_path():
    text = '{"task_id": 123, "task_path": "/some/path"}'
    result = _parse_task_reference(text)
    assert result == (123, Path("/some/path"))
