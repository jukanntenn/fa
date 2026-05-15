from __future__ import annotations

from fa.core.config import tool_extra_env


def test_tool_extra_env_returns_none_for_non_codex():
    result = tool_extra_env("kilo")
    assert result is None


def test_tool_extra_env_returns_none_for_codex_without_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = tool_extra_env("codex")
    assert result is None


def test_tool_extra_env_returns_key_for_codex_with_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("CODEX_API_KEY=sk-test123\n")
    result = tool_extra_env("codex")
    assert result == {"CODEX_API_KEY": "sk-test123"}
