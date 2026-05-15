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


# ─── prompting (extended) ──────────────────────────────────────
def test_claude_prompt_uses_stdin_without_argv_prompt() -> None:
    from fa.gestate import commands as gestate_commands

    prompt = "/gestating " + "x" * 10000

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("claude", prompt)

    assert prompt_stdin == prompt
    assert cmd[-1] != "-"
    assert cmd[-1] != ""
    assert not any(prompt in part for part in cmd)


def test_ccr_prompt_uses_stdin_without_argv_prompt() -> None:
    from fa.gestate import commands as gestate_commands

    prompt = "/gestating " + "x" * 10000

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("ccr", prompt)

    assert prompt_stdin == prompt
    assert cmd[-1] != "-"
    assert cmd[-1] != ""
    assert not any(prompt in part for part in cmd)


def test_codex_long_prompt_uses_prompt_file_handoff() -> None:
    from pathlib import Path

    from fa.gestate import commands as gestate_commands

    prompt = "/gestating " + "x" * 8001
    prompt_path = Path("/tmp/prompt.md")

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
        "codex", prompt, prompt_path
    )

    assert prompt_stdin is None
    assert prompt not in cmd
    assert f"Read the full prompt from {prompt_path} and follow it exactly." in cmd


def test_codex_multiline_prompt_uses_prompt_file_handoff() -> None:
    from pathlib import Path

    from fa.gestate import commands as gestate_commands

    prompt = "line 1\nline 2"
    prompt_path = Path("/tmp/prompt.md")

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
        "codex", prompt, prompt_path
    )

    assert prompt_stdin is None
    assert prompt not in cmd
    assert f"Read the full prompt from {prompt_path} and follow it exactly." in cmd


def test_codex_without_prompt_path_keeps_existing_long_argv_prompt() -> None:
    from fa.gestate import commands as gestate_commands

    prompt = "/gestating " + "x" * 8001

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

    assert prompt_stdin is None
    assert prompt in cmd


def test_stream_prompt_removes_empty_placeholder_without_dropping_flags() -> None:
    from unittest.mock import patch

    from fa.gestate import commands as gestate_commands

    with patch(
        "fa.core.config.TOOL_COMMANDS",
        {
            "echo": ["echo", "", "--flag", "{prompt}"],
        },
    ):
        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("echo", "hello")

    assert prompt_stdin is None
    assert cmd == ["echo", "", "--flag", "hello"]


def test_stream_prompt_keeps_placeholder_when_needed_for_empty_prompt() -> None:
    from unittest.mock import patch

    from fa.gestate import commands as gestate_commands

    with patch(
        "fa.core.config.TOOL_COMMANDS",
        {
            "echo": ["echo", "{prompt}"],
        },
    ):
        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("echo", "")

    assert prompt_stdin is None
    assert cmd == ["echo", ""]


def test_non_tty_reads_and_strips_stdin() -> None:
    import io
    from unittest.mock import patch

    from fa.gestate import commands as gestate_commands

    class StdinStub(io.StringIO):
        def isatty(self) -> bool:
            return False

    text = "  line1\n" + "x" * 10000 + "\nline3  "
    with patch("fa.gestate.prompting.sys.stdin", StdinStub(text)):
        result = gestate_commands._read_stdin()

    assert result == text.strip()


def test_tty_importerror_fallback_reads_multiline_until_eof() -> None:
    import io
    from unittest.mock import patch

    from fa.gestate import commands as gestate_commands

    class StdinStub(io.StringIO):
        def isatty(self) -> bool:
            return True

    text = "  line1\n" + "x" * 10000 + "\nline3  "

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("prompt_toolkit"):
            raise ImportError
        return original_import(name, *args, **kwargs)

    original_import = __import__
    with (
        patch("fa.gestate.prompting.sys.stdin", StdinStub(text)),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        result = gestate_commands._read_stdin()

    assert result == text.strip()


def test_tty_eoferror_returns_empty() -> None:
    import io
    from unittest.mock import patch

    from fa.gestate import prompting

    class StdinStub(io.StringIO):
        def isatty(self) -> bool:
            return True

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("prompt_toolkit"):
            raise EOFError
        return original_import(name, *args, **kwargs)

    original_import = __import__
    with (
        patch("fa.gestate.prompting.sys.stdin", StdinStub("")),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        result = prompting._read_stdin()

    assert result == ""
