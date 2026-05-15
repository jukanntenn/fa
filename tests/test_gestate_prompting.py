from __future__ import annotations

from fa.gestate.prompting import (
    _build_tool_cmd_for_prompt,
    _is_task_id,
    _tool_accepts_prompt_stdin,
)


def test_is_task_id_returns_true_for_existing_task(storage_root):
    from fa.task.storage import create_task

    task = create_task("test-task")
    assert _is_task_id(str(task.id))


def test_is_task_id_returns_false_for_nonexistent_task(storage_root):
    assert not _is_task_id("99999")


def test_is_task_id_returns_false_for_non_numeric():
    assert not _is_task_id("not-a-number")


def test_is_task_id_strips_whitespace(storage_root):
    from fa.task.storage import create_task

    task = create_task("whitespace-test")
    assert _is_task_id(f"  {task.id}  ")


def test_tool_accepts_prompt_stdin():
    assert _tool_accepts_prompt_stdin("claude")
    assert _tool_accepts_prompt_stdin("ccr")
    assert not _tool_accepts_prompt_stdin("codex")
    assert not _tool_accepts_prompt_stdin("other")


def test_build_tool_cmd_for_prompt_non_claude_short_prompt():
    cmd, stdin = _build_tool_cmd_for_prompt("codex", "short prompt")
    assert stdin is None
    assert "short prompt" in cmd


def test_build_tool_cmd_for_prompt_claude_returns_stdin():
    cmd, stdin = _build_tool_cmd_for_prompt("claude", "test prompt")
    assert stdin == "test prompt"


def test_build_tool_cmd_for_prompt_ccr_returns_stdin():
    cmd, stdin = _build_tool_cmd_for_prompt("ccr", "test prompt")
    assert stdin == "test prompt"


def test_build_tool_cmd_for_prompt_long_prompt_uses_prompt_path(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    long_prompt = "x" * 9000
    cmd, stdin = _build_tool_cmd_for_prompt("codex", long_prompt, prompt_path)
    assert "Read the full prompt from" in " ".join(cmd)


def test_build_tool_cmd_for_prompt_multiline_uses_prompt_path(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    multiline_prompt = "line1\nline2"
    cmd, stdin = _build_tool_cmd_for_prompt("codex", multiline_prompt, prompt_path)
    assert "Read the full prompt from" in " ".join(cmd)
