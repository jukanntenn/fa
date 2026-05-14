from __future__ import annotations

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.gestate import commands as gestate_commands
from fa.task.model import Task
from fa.task.prompt import build_task_prompt, infer_attempt, infer_memory_sequence


class GestatePromptTests(unittest.TestCase):
    def test_claude_prompt_uses_stdin_without_argv_prompt(self) -> None:
        prompt = "/gestating " + "x" * 10000

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
            "claude", prompt
        )

        self.assertEqual(prompt_stdin, prompt)
        self.assertNotEqual(cmd[-1], "-")
        self.assertNotEqual(cmd[-1], "")
        self.assertFalse(any(prompt in part for part in cmd))

    def test_ccr_prompt_uses_stdin_without_argv_prompt(self) -> None:
        prompt = "/gestating " + "x" * 10000

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("ccr", prompt)

        self.assertEqual(prompt_stdin, prompt)
        self.assertNotEqual(cmd[-1], "-")
        self.assertNotEqual(cmd[-1], "")
        self.assertFalse(any(prompt in part for part in cmd))

    def test_codex_keeps_existing_argv_prompt(self) -> None:
        prompt = "short prompt"

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

        self.assertIsNone(prompt_stdin)
        self.assertIn(prompt, cmd)

    def test_codex_long_prompt_uses_prompt_file_handoff(self) -> None:
        prompt = "/gestating " + "x" * 8001
        prompt_path = Path("/tmp/prompt.md")

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
            "codex", prompt, prompt_path
        )

        self.assertIsNone(prompt_stdin)
        self.assertNotIn(prompt, cmd)
        self.assertIn(
            f"Read the full prompt from {prompt_path} and follow it exactly.", cmd
        )

    def test_codex_multiline_prompt_uses_prompt_file_handoff(self) -> None:
        prompt = "line 1\nline 2"
        prompt_path = Path("/tmp/prompt.md")

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
            "codex", prompt, prompt_path
        )

        self.assertIsNone(prompt_stdin)
        self.assertNotIn(prompt, cmd)
        self.assertIn(
            f"Read the full prompt from {prompt_path} and follow it exactly.", cmd
        )

    def test_codex_without_prompt_path_keeps_existing_long_argv_prompt(self) -> None:
        prompt = "/gestating " + "x" * 8001

        cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("codex", prompt)

        self.assertIsNone(prompt_stdin)
        self.assertIn(prompt, cmd)

    def test_stream_prompt_removes_empty_placeholder_without_dropping_flags(
        self,
    ) -> None:
        with patch(
            "fa.gestate.prompting.TOOL_COMMANDS",
            {
                "echo": ["echo", "", "--flag", "{prompt}"],
            },
        ):
            cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
                "echo", "hello"
            )

        self.assertIsNone(prompt_stdin)
        self.assertEqual(cmd, ["echo", "", "--flag", "hello"])

    def test_stream_prompt_keeps_placeholder_when_needed_for_empty_prompt(self) -> None:
        with patch(
            "fa.gestate.prompting.TOOL_COMMANDS",
            {
                "echo": ["echo", "{prompt}"],
            },
        ):
            cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt("echo", "")

        self.assertIsNone(prompt_stdin)
        self.assertEqual(cmd, ["echo", ""])


class ReadStdinTests(unittest.TestCase):
    def test_non_tty_reads_and_strips_stdin(self) -> None:
        class StdinStub(io.StringIO):
            def isatty(self) -> bool:
                return False

        text = "  line1\n" + "x" * 10000 + "\nline3  "
        with patch("fa.gestate.prompting.sys.stdin", StdinStub(text)):
            result = gestate_commands._read_stdin()

        self.assertEqual(result, text.strip())

    def test_tty_importerror_fallback_reads_multiline_until_eof(self) -> None:
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

        self.assertEqual(result, text.strip())


class TaskPromptTests(unittest.TestCase):
    def test_infer_memory_sequence_counts_existing_memory_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir)
            (task_path / "memory-1.md").write_text("one", encoding="utf-8")
            (task_path / "memory-2.md").write_text("two", encoding="utf-8")
            task = Task.new(1, "demo", None, task_path)

            self.assertEqual(infer_memory_sequence(task), 3)

    def test_infer_attempt_counts_existing_feedback_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir)
            (task_path / "feedback-1.md").write_text("one", encoding="utf-8")
            (task_path / "feedback-2.md").write_text("two", encoding="utf-8")
            task = Task.new(1, "demo", None, task_path)

            self.assertEqual(infer_attempt(task), 3)

    def test_build_task_prompt_uses_first_attempt_when_not_attempt_run(self) -> None:
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

        self.assertIn("# Task Information", prompt)
        self.assertIn("- ID: 1", prompt)
        self.assertNotIn("Memory files", prompt)

    def test_build_task_prompt_includes_parent_context_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parent_path = root / ".fa" / "tasks" / "1-05-13-parent"
            task_path = parent_path / "2-05-13-child"
            parent_path.mkdir(parents=True)
            task_path.mkdir(parents=True)
            (parent_path / "memory-1.md").write_text("parent memory", encoding="utf-8")
            (parent_path / "feedback-1.md").write_text(
                "parent feedback", encoding="utf-8"
            )
            task = Task.new(2, "child", 1, task_path)
            parent = Task.new(1, "parent", None, parent_path)

            with (
                patch("fa.task.prompt.relative_path", side_effect=lambda path: path),
                patch("fa.task.prompt.project_root", return_value=root),
            ):
                prompt = build_task_prompt(task, parent, is_attempt_run=False)

        self.assertIn("Memory files", prompt)
        self.assertIn("Feedback files", prompt)

    def test_build_task_prompt_raises_when_template_missing(self) -> None:
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
                                "get_template": lambda self, name: (
                                    _ for _ in ()
                                ).throw(FileNotFoundError())
                            },
                        )(),
                        "missing",
                    ),
                ),
            ):
                with self.assertRaises(FileNotFoundError):
                    build_task_prompt(task, None, is_attempt_run=False)
