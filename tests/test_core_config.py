from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fa.core.config import _load_dotenv, _strip_quotes, build_tool_cmd


class StripQuotesTests(unittest.TestCase):
    def test_strips_double_quotes(self):
        self.assertEqual(_strip_quotes('"hello"'), "hello")

    def test_strips_single_quotes(self):
        self.assertEqual(_strip_quotes("'hello'"), "hello")

    def test_no_quotes_unchanged(self):
        self.assertEqual(_strip_quotes("hello"), "hello")

    def test_mismatched_quotes_unchanged(self):
        self.assertEqual(_strip_quotes("\"hello'"), "\"hello'")

    def test_inner_quotes_preserved(self):
        self.assertEqual(_strip_quotes('"it\'s here"'), "it's here")

    def test_empty_quoted_value(self):
        self.assertEqual(_strip_quotes('""'), "")
        self.assertEqual(_strip_quotes("''"), "")

    def test_single_character_unquoted(self):
        self.assertEqual(_strip_quotes("a"), "a")

    def test_single_quote_char(self):
        self.assertEqual(_strip_quotes('"'), '"')


class LoadDotenvTests(unittest.TestCase):
    def test_strips_double_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text('KEY="value"\n', encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": "value"})

    def test_strips_single_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text("KEY='value'\n", encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": "value"})

    def test_no_quotes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text("KEY=value\n", encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": "value"})

    def test_mismatched_quotes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text("KEY=\"value'\n", encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": "\"value'"})

    def test_inner_quotes_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text('KEY="it\'s here"\n', encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": "it's here"})

    def test_empty_quoted_value(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text('KEY=""\n', encoding="utf-8")
            self.assertEqual(_load_dotenv(env_file), {"KEY": ""})

    def test_nonexistent_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            result = _load_dotenv(Path(d) / "nonexistent.env")
            self.assertEqual(result, {})

    def test_comments_and_blank_lines_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text(
                "# this is a comment\n\n\nKEY=value\n# another comment\nFOO='bar'\n",
                encoding="utf-8",
            )
            self.assertEqual(_load_dotenv(env_file), {"KEY": "value", "FOO": "bar"})


class BuildToolCmdTests(unittest.TestCase):
    def test_claude_without_agent(self):
        self.assertEqual(
            build_tool_cmd("claude", "do stuff"),
            [
                "claude",
                "-p",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
                "--verbose",
                "do stuff",
            ],
        )

    def test_ccr_without_agent(self):
        self.assertEqual(
            build_tool_cmd("ccr", "do stuff"),
            [
                "ccr",
                "code",
                "-p",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
                "--verbose",
                "do stuff",
            ],
        )

    def test_kilo_without_agent(self):
        self.assertEqual(
            build_tool_cmd("kilo", "do stuff"),
            [
                "kilo",
                "run",
                "--auto",
                "do stuff",
                "--print-logs",
                "--log-level",
                "DEBUG",
            ],
        )

    def test_opencode_without_agent(self):
        self.assertEqual(
            build_tool_cmd("opencode", "do stuff"),
            ["opencode", "run", "do stuff", "--print-logs", "--log-level", "DEBUG"],
        )

    def test_codex_without_agent(self):
        self.assertEqual(
            build_tool_cmd("codex", "do stuff"),
            ["codex", "exec", "--full-auto", "do stuff"],
        )

    def test_claude_with_agent(self):
        self.assertEqual(
            build_tool_cmd("claude", "do stuff", agent="reviewer"),
            [
                "claude",
                "-p",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
                "--verbose",
                "--agent",
                "reviewer",
                "do stuff",
            ],
        )

    def test_ccr_with_agent(self):
        self.assertEqual(
            build_tool_cmd("ccr", "do stuff", agent="reviewer"),
            [
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
            ],
        )

    def test_kilo_with_agent(self):
        self.assertEqual(
            build_tool_cmd("kilo", "do stuff", agent="reviewer"),
            [
                "kilo",
                "run",
                "--auto",
                "--agent",
                "reviewer",
                "do stuff",
                "--print-logs",
                "--log-level",
                "DEBUG",
            ],
        )

    def test_opencode_with_agent(self):
        self.assertEqual(
            build_tool_cmd("opencode", "do stuff", agent="reviewer"),
            [
                "opencode",
                "run",
                "--agent",
                "reviewer",
                "do stuff",
                "--print-logs",
                "--log-level",
                "DEBUG",
            ],
        )

    def test_codex_with_agent(self):
        self.assertEqual(
            build_tool_cmd("codex", "do stuff", agent="reviewer"),
            ["codex", "exec", "--full-auto", "$reviewer do stuff"],
        )

    def test_unknown_tool_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            build_tool_cmd("unknown_tool", "do stuff")
        self.assertIn("unknown tool 'unknown_tool'", str(ctx.exception))

    def test_agent_none_same_as_no_agent(self):
        self.assertEqual(
            build_tool_cmd("claude", "do stuff", agent=None),
            build_tool_cmd("claude", "do stuff"),
        )
