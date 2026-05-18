from __future__ import annotations

from fa.core.logview_parse import _extract_text_content


def test_string_passthrough() -> None:
    assert _extract_text_content("hello world") == "hello world"


def test_empty_string() -> None:
    assert _extract_text_content("") == ""


def test_empty_list() -> None:
    assert _extract_text_content([]) == ""


def test_single_text_item() -> None:
    assert _extract_text_content([{"type": "text", "text": "hello"}]) == "hello"


def test_multiple_text_items() -> None:
    assert (
        _extract_text_content(
            [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        )
        == "a b"
    )


def test_mixed_types() -> None:
    assert (
        _extract_text_content(
            [{"type": "image", "text": "x"}, {"type": "text", "text": "y"}]
        )
        == "y"
    )


def test_item_missing_text_key() -> None:
    assert _extract_text_content([{"type": "text"}]) == ""


def test_non_dict_item() -> None:
    assert _extract_text_content([42, {"type": "text", "text": "ok"}]) == "ok"
