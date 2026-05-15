from __future__ import annotations

from pathlib import Path

from fa.core.config import _load_dotenv


def test_load_dotenv_returns_empty_for_nonexistent_file():
    result = _load_dotenv(Path("/nonexistent/file"))
    assert result == {}


def test_load_dotenv_parses_simple_key_value(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value")
    result = _load_dotenv(env_file)
    assert result == {"KEY": "value"}


def test_load_dotenv_ignores_comments(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nKEY=value")
    result = _load_dotenv(env_file)
    assert result == {"KEY": "value"}


def test_load_dotenv_ignores_blank_lines(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("\nKEY=value\n")
    result = _load_dotenv(env_file)
    assert result == {"KEY": "value"}


def test_load_dotenv_strips_whitespace(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("  KEY  =  value  ")
    result = _load_dotenv(env_file)
    assert result == {"KEY": "value"}


def test_load_dotenv_ignores_line_without_equals(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\nINVALID_LINE\nOTHER=valid")
    result = _load_dotenv(env_file)
    assert result == {"KEY": "value", "OTHER": "valid"}
    assert "INVALID_LINE" not in result
