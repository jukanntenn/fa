from __future__ import annotations

from fa.core.logview_parse import _split_complete_lines


def test_complete_lines_with_trailing_newline() -> None:
    assert _split_complete_lines("hello\nworld\n") == ["hello", "world"]


def test_no_trailing_newline() -> None:
    assert _split_complete_lines("hello\nworld") == ["hello"]


def test_blank_line_dropped() -> None:
    assert _split_complete_lines("hello\n\nworld\n") == ["hello", "world"]


def test_empty_string() -> None:
    assert _split_complete_lines("") == []


def test_only_newlines() -> None:
    assert _split_complete_lines("\n\n\n") == []


def test_trailing_space_preserved() -> None:
    assert _split_complete_lines("line with trailing space \n") == [
        "line with trailing space "
    ]
