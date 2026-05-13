import io
import unittest
from pathlib import Path
from unittest.mock import patch

from fa.gestate import commands as gestate_commands


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
            {"claude": ["claude", "-p", "{prompt}", "--verbose"]},
        ):
            cmd, prompt_stdin = gestate_commands._build_tool_cmd_for_prompt(
                "claude", "hello"
            )

        self.assertEqual(prompt_stdin, "hello")
        self.assertEqual(cmd, ["claude", "-p", "--verbose"])

    def test_non_tty_read_stdin_preserves_full_text_except_outer_strip(self) -> None:
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
