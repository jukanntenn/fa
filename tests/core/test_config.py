from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fa.core.config import _build_agent_cmd, build_tool_cmd
from fa.core.env import load_dotenv, strip_quotes


def test_strips_double_quotes():
    assert strip_quotes('"hello"') == "hello"


def test_strips_single_quotes():
    assert strip_quotes("'hello'") == "hello"


def test_no_quotes_unchanged():
    assert strip_quotes("hello") == "hello"


def test_mismatched_quotes_unchanged():
    assert strip_quotes("\"hello'") == "\"hello'"


def test_inner_quotes_preserved():
    assert strip_quotes('"it\'s here"') == "it's here"


def test_empty_quoted_value():
    assert strip_quotes('""') == ""
    assert strip_quotes("''") == ""


def test_single_character_unquoted():
    assert strip_quotes("a") == "a"


def test_single_quote_char():
    assert strip_quotes('"') == '"'


def test_dotenv_strips_double_quotes():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text('KEY="value"\n', encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "value"}


def test_dotenv_strips_single_quotes():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text("KEY='value'\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "value"}


def test_dotenv_no_quotes_unchanged():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text("KEY=value\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "value"}


def test_dotenv_mismatched_quotes_unchanged():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text("KEY=\"value'\n", encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "\"value'"}


def test_dotenv_inner_quotes_preserved():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text('KEY="it\'s here"\n', encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": "it's here"}


def test_dotenv_empty_quoted_value():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text('KEY=""\n', encoding="utf-8")
        assert load_dotenv(env_file) == {"KEY": ""}


def test_dotenv_nonexistent_file_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        result = load_dotenv(Path(d) / "nonexistent.env")
        assert result == {}


def test_dotenv_comments_and_blank_lines_skipped():
    with tempfile.TemporaryDirectory() as d:
        env_file = Path(d) / ".env"
        env_file.write_text(
            "# this is a comment\n\n\nKEY=value\n# another comment\nFOO='bar'\n",
            encoding="utf-8",
        )
        assert load_dotenv(env_file) == {"KEY": "value", "FOO": "bar"}


def test_claude_without_agent():
    assert build_tool_cmd("claude", "do stuff") == [
        "claude",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "do stuff",
    ]


def test_ccr_without_agent():
    assert build_tool_cmd("ccr", "do stuff") == [
        "ccr",
        "code",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "do stuff",
    ]


def test_kilo_without_agent():
    assert build_tool_cmd("kilo", "do stuff") == [
        "kilo",
        "run",
        "--auto",
        "do stuff",
        "--print-logs",
        "--log-level",
        "DEBUG",
    ]


def test_opencode_without_agent():
    assert build_tool_cmd("opencode", "do stuff") == [
        "opencode",
        "run",
        "do stuff",
        "--print-logs",
        "--log-level",
        "DEBUG",
    ]


def test_codex_without_agent():
    assert build_tool_cmd("codex", "do stuff") == [
        "codex",
        "exec",
        "-s",
        "danger-full-access",
        "do stuff",
    ]


def test_claude_with_agent():
    assert build_tool_cmd("claude", "do stuff", agent="reviewer") == [
        "claude",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--agent",
        "reviewer",
        "do stuff",
    ]


def test_ccr_with_agent():
    assert build_tool_cmd("ccr", "do stuff", agent="reviewer") == [
        "ccr",
        "code",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--agent",
        "reviewer",
        "do stuff",
    ]


def test_kilo_with_agent():
    assert build_tool_cmd("kilo", "do stuff", agent="reviewer") == [
        "kilo",
        "run",
        "--auto",
        "--agent",
        "reviewer",
        "do stuff",
        "--print-logs",
        "--log-level",
        "DEBUG",
    ]


def test_opencode_with_agent():
    assert build_tool_cmd("opencode", "do stuff", agent="reviewer") == [
        "opencode",
        "run",
        "--agent",
        "reviewer",
        "do stuff",
        "--print-logs",
        "--log-level",
        "DEBUG",
    ]


def test_codex_with_agent():
    assert build_tool_cmd("codex", "do stuff", agent="reviewer") == [
        "codex",
        "exec",
        "-s",
        "danger-full-access",
        "$reviewer do stuff",
    ]


def test_unknown_tool_raises_value_error():
    with pytest.raises(ValueError, match="unknown tool 'unknown_tool'"):
        build_tool_cmd("unknown_tool", "do stuff")


def test_agent_none_same_as_no_agent():
    assert build_tool_cmd("claude", "do stuff", agent=None) == build_tool_cmd(
        "claude", "do stuff"
    )


# ─── tool_extra_env ────────────────────────────────────────────
def test_tool_extra_env_returns_none_for_non_codex():
    from fa.core.config import tool_extra_env

    result = tool_extra_env("kilo")
    assert result is None


def test_tool_extra_env_returns_none_for_codex_without_env(tmp_path, monkeypatch):
    from fa.core.config import tool_extra_env

    monkeypatch.chdir(tmp_path)
    result = tool_extra_env("codex")
    assert result is None


def test_tool_extra_env_returns_key_for_codex_with_env(tmp_path, monkeypatch):
    from fa.core.config import tool_extra_env

    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("CODEX_API_KEY=sk-test123\n")
    result = tool_extra_env("codex")
    assert result == {"CODEX_API_KEY": "sk-test123"}


# ─── _build_agent_cmd ──────────────────────────────────────────
def test_build_agent_cmd_dollar_style():
    codex_template = ["codex", "exec", "-s", "danger-full-access", "{prompt}"]
    cmd, _ = _build_agent_cmd(codex_template, "hello world", "coder", "$")
    assert cmd == ["codex", "exec", "-s", "danger-full-access", "$coder hello world"]


def test_build_agent_cmd_flag_style():
    claude_template = [
        "claude",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "{prompt}",
    ]
    cmd, _ = _build_agent_cmd(claude_template, "hello", "reviewer", "--agent")
    assert cmd[6:8] == ["--agent", "reviewer"]
    assert cmd[8] == "hello"


def test_build_tool_cmd_without_agent():
    result = build_tool_cmd("claude", "hello")
    assert "--agent" not in result
    assert result[-1] == "hello"


def test_build_tool_cmd_with_agent():
    result = build_tool_cmd("claude", "hello", agent="coder")
    assert "--agent" in result
    assert "coder" in result
