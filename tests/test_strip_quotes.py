from __future__ import annotations

from fa.core.config import _strip_quotes


def test_strip_quotes_single():
    assert _strip_quotes("'hello'") == "hello"


def test_strip_quotes_double():
    assert _strip_quotes('"hello"') == "hello"


def test_strip_quotes_no_change():
    assert _strip_quotes("hello") == "hello"


def test_strip_quotes_empty():
    assert _strip_quotes("") == ""


def test_strip_quotes_single_char():
    assert _strip_quotes("a") == "a"
