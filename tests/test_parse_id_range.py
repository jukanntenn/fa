from __future__ import annotations

from fa.task.storage import parse_id_range


def test_single_id() -> None:
    assert parse_id_range("5") == [5]


def test_comma_separated() -> None:
    assert parse_id_range("1,3,7") == [1, 3, 7]


def test_range() -> None:
    assert parse_id_range("2-5") == [2, 3, 4, 5]


def test_mixed() -> None:
    assert parse_id_range("1,3-5,8") == [1, 3, 4, 5, 8]


def test_empty_pieces() -> None:
    assert parse_id_range("1,,3") == [1, 3]


def test_trailing_comma() -> None:
    assert parse_id_range("1,2,") == [1, 2]


def test_single_element_range() -> None:
    assert parse_id_range("3-3") == [3]


def test_reversed_range() -> None:
    assert parse_id_range("5-3") == []
