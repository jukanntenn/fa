from __future__ import annotations

import sys
from pathlib import Path

import typer

from fa.core.config import TOOL_COMMANDS
from fa.task.storage import find_task


def _is_task_id(value: str) -> bool:
    try:
        task_id = int(value.strip())
    except ValueError:
        return False
    return find_task(task_id) is not None


def _read_stdin() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.key_binding import KeyBindings

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            buf = event.app.current_buffer
            if buf.text.strip() and buf.document.current_line.strip() == "":
                buf.validate_and_handle()
            else:
                buf.newline(copy_margin=False)

        typer.echo("  (Press Enter on blank line to submit)")
        text = pt_prompt(
            "Enter intent brief or task ID:\n> ",
            multiline=True,
            key_bindings=kb,
        )
        return text.strip()
    except ImportError:
        typer.echo(
            "Warning: prompt_toolkit not installed, finish input with Ctrl-D.",
            err=True,
        )
        typer.echo("Enter intent brief or task ID:")
        text = sys.stdin.read()
        return text.strip()
    except EOFError:
        return ""


def _build_tool_cmd(tool: str, prompt: str) -> list[str]:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    template = TOOL_COMMANDS[tool]
    return [part.format(prompt=prompt) for part in template]


def _tool_accepts_prompt_stdin(tool: str) -> bool:
    return tool in {"claude", "ccr"}


def _build_tool_cmd_for_prompt(
    tool: str, prompt: str, prompt_path: Path | None = None
) -> tuple[list[str], str | None]:
    if not _tool_accepts_prompt_stdin(tool):
        if prompt_path is not None and (len(prompt) > 8000 or "\n" in prompt):
            handoff = f"Read the full prompt from {prompt_path} and follow it exactly."
            return _build_tool_cmd(tool, handoff), None
        return _build_tool_cmd(tool, prompt), None
    cmd = _build_tool_cmd(tool, "")
    return [part for part in cmd if part != ""], prompt
