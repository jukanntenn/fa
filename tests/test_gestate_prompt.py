from __future__ import annotations

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from fa.gestate import commands as gestate_commands
from fa.task.model import Task
from fa.task.prompt import build_task_prompt, infer_attempt, infer_memory_sequence


def test_claude_prompt_uses_stdin_without_argv_prompt() -> None:
    prompt = "/gestating " + "x" * 10000

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("claude", prompt)

    assert prompt_stdin == prompt
    assert cmd[-1] != "-"
    assert cmd[-1] != ""
    assert not any(prompt in part for part in cmd)


def test_ccr_prompt_uses_stdin_without_argv_prompt() -> None:
    prompt = "/gestating " + "x" * 10000

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("ccr", prompt)

    assert prompt_stdin == prompt
    assert cmd[-1] != "-"
    assert cmd[-1] != ""
    assert not any(prompt in part for part in cmd)


def test_codex_keeps_existing_argv_prompt() -> None:
    prompt = "short prompt"

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

    assert prompt_stdin is None
    assert prompt in cmd


def test_codex_long_prompt_uses_prompt_file_handoff() -> None:
    prompt = "/gestating " + "x" * 8001
    prompt_path = Path("/tmp/prompt.md")

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
        "codex", prompt, prompt_path
    )

    assert prompt_stdin is None
    assert prompt not in cmd
    assert f"Read the full prompt from {prompt_path} and follow it exactly." in cmd


def test_codex_multiline_prompt_uses_prompt_file_handoff() -> None:
    prompt = "line 1\nline 2"
    prompt_path = Path("/tmp/prompt.md")

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
        "codex", prompt, prompt_path
    )

    assert prompt_stdin is None
    assert prompt not in cmd
    assert f"Read the full prompt from {prompt_path} and follow it exactly." in cmd


def test_codex_without_prompt_path_keeps_existing_long_argv_prompt() -> None:
    prompt = "/gestating " + "x" * 8001

    cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

    assert prompt_stdin is None
    assert prompt in cmd


def test_stream_prompt_removes_empty_placeholder_without_dropping_flags() -> None:
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
    class StdinStub(io.StringIO):
        def isatty(self) -> bool:
            return False

    text = "  line1\n" + "x" * 10000 + "\nline3  "
    with patch("fa.gestate.prompting.sys.stdin", StdinStub(text)):
        result = gestate_commands._read_stdin()

    assert result == text.strip()


def test_tty_importerror_fallback_reads_multiline_until_eof() -> None:
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


def test_infer_memory_sequence_counts_existing_memory_files() -> None:
    with TemporaryDirectory() as temp_dir:
        task_path = Path(temp_dir)
        (task_path / "memory-1.md").write_text("one", encoding="utf-8")
        (task_path / "memory-2.md").write_text("two", encoding="utf-8")
        task = Task.new(1, "demo", None, task_path)

        assert infer_memory_sequence(task) == 3


def test_infer_attempt_counts_existing_feedback_files() -> None:
    with TemporaryDirectory() as temp_dir:
        task_path = Path(temp_dir)
        (task_path / "feedback-1.md").write_text("one", encoding="utf-8")
        (task_path / "feedback-2.md").write_text("two", encoding="utf-8")
        task = Task.new(1, "demo", None, task_path)

        assert infer_attempt(task) == 3


def test_build_task_prompt_uses_first_attempt_when_not_attempt_run() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        task_path = root / ".fa" / "tasks" / "1-05-13-demo"
        task_path.mkdir(parents=True)
        (task_path / "feedback-1.md").write_text("feedback", encoding="utf-8")
        task = Task.new(1, "demo", None, task_path)

        with (
            patch("fa.task.prompt.relative_path", side_effect=lambda path: path),
            patch("fa.task.prompt.project_root", return_value=root),
        ):
            prompt = build_task_prompt(task, None, is_attempt_run=False)

    assert "# Task Information" in prompt
    assert "- ID: 1" in prompt
    assert "Memory files" not in prompt


def test_build_task_prompt_includes_parent_context_counts() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        parent_path = root / ".fa" / "tasks" / "1-05-13-parent"
        task_path = parent_path / "2-05-13-child"
        parent_path.mkdir(parents=True)
        task_path.mkdir(parents=True)
        (parent_path / "memory-1.md").write_text("parent memory", encoding="utf-8")
        (parent_path / "feedback-1.md").write_text("parent feedback", encoding="utf-8")
        task = Task.new(2, "child", 1, task_path)
        parent = Task.new(1, "parent", None, parent_path)

        with (
            patch("fa.task.prompt.relative_path", side_effect=lambda path: path),
            patch("fa.task.prompt.project_root", return_value=root),
        ):
            prompt = build_task_prompt(task, parent, is_attempt_run=False)

    assert "Memory files" in prompt
    assert "Feedback files" in prompt


def test_build_task_prompt_raises_when_template_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        task = Task.new(1, "demo", None, Path(temp_dir))

        with (
            patch("fa.task.prompt.relative_path", side_effect=lambda path: path),
            patch(
                "fa.task.prompt.task_template",
                return_value=(
                    type(
                        "Env",
                        (),
                        {
                            "get_template": lambda self, name: (_ for _ in ()).throw(
                                FileNotFoundError()
                            )
                        },
                    )(),
                    "missing",
                ),
            ),
        ):
            with pytest.raises(FileNotFoundError):
                build_task_prompt(task, None, is_attempt_run=False)


def test_claude_accepts_stdin() -> None:
    from fa.gestate.prompting import _tool_accepts_prompt_stdin

    assert _tool_accepts_prompt_stdin("claude")


def test_ccr_accepts_stdin() -> None:
    from fa.gestate.prompting import _tool_accepts_prompt_stdin

    assert _tool_accepts_prompt_stdin("ccr")


def test_codex_rejects_stdin() -> None:
    from fa.gestate.prompting import _tool_accepts_prompt_stdin

    assert not _tool_accepts_prompt_stdin("codex")


def test_build_tool_cmd_raises_valueerror_for_unknown_tool() -> None:
    from fa.core.config import build_tool_cmd

    with pytest.raises(ValueError, match="nonexistent"):
        build_tool_cmd("nonexistent", "hello")


def test_build_tool_cmd_builds_known_tool_command_with_prompt() -> None:
    from fa.core.config import build_tool_cmd

    cmd = build_tool_cmd("codex", "test prompt")
    assert "test prompt" in cmd


def test_is_task_id_returns_false_for_non_integer() -> None:
    from fa.gestate.prompting import _is_task_id

    assert not _is_task_id("abc")
    assert not _is_task_id("")
    assert not _is_task_id("1.5")


def test_is_task_id_returns_false_for_nonexistent_id() -> None:
    from fa.gestate import prompting

    with patch.object(prompting, "find_task", return_value=None):
        assert not prompting._is_task_id("999")


def test_is_task_id_returns_true_for_existing_task() -> None:
    from fa.gestate import prompting
    from fa.task.model import Task

    fake_task = Task.new(42, "exists", None, Path("/tmp/fake"))
    with patch.object(prompting, "find_task", return_value=fake_task):
        assert prompting._is_task_id("42")
