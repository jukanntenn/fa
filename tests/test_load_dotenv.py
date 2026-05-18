from __future__ import annotations

import tempfile
from pathlib import Path

from fa.core.env import load_dotenv, strip_quotes


def test_strip_quotes_double() -> None:
    assert strip_quotes('"hello"') == "hello"


def test_strip_quotes_single() -> None:
    assert strip_quotes("'hello'") == "hello"


def test_strip_quotes_no_quotes() -> None:
    assert strip_quotes("hello") == "hello"


def test_strip_quotes_single_char() -> None:
    assert strip_quotes('"') == '"'


def test_strip_quotes_empty() -> None:
    assert strip_quotes("") == ""


def test_strip_quotes_mismatched() -> None:
    assert strip_quotes("\"hello'") == "\"hello'"


def test_load_dotenv_basic() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("KEY=value\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "value"}


def test_load_dotenv_multiple_lines() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("A=1\nB=2\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"A": "1", "B": "2"}


def test_load_dotenv_quoted_value() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text('KEY="value"\n', encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "value"}


def test_load_dotenv_comment_line() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("# comment\nKEY=val\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "val"}


def test_load_dotenv_blank_line() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("\nKEY=val\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "val"}


def test_load_dotenv_missing_file() -> None:
    result = load_dotenv(Path("/nonexistent/path/.env"))
    assert result == {}


def test_load_dotenv_value_with_equals() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("KEY=val=ue\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "val=ue"}


def test_load_dotenv_key_no_value() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("KEY=\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": ""}


def test_load_dotenv_no_equals() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("NOEQUALS\n", encoding="utf-8")
        assert load_dotenv(env_file) == {}
