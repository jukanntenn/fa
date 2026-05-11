from __future__ import annotations

import json
import logging
import select
import shutil
import sys
import time
from pathlib import Path

logger = logging.getLogger("fa")

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"

_STREAM_JSON_TOOLS = {"claude", "ccr"}


def _truncate(text: str, max_len: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def parse_jsonl_line(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Failed to parse JSONL line: %s", raw[:500])
        return f"{_DIM}[raw] {_truncate(raw)}{_RESET}"
    msg_type = obj.get("type")
    if msg_type == "system":
        return None
    if msg_type == "result":
        return _format_result(obj)
    if msg_type == "assistant":
        return _format_assistant(obj)
    if msg_type == "user":
        return _format_user(obj)
    return f"{_DIM}[unknown: {msg_type}]{_RESET}"


def _format_assistant(obj: dict) -> str | None:
    message = obj.get("message", {})
    contents = message.get("content", [])
    if not contents:
        return None
    parts: list[str] = []
    for item in contents:
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text", "")
            if text.strip():
                parts.append(text.strip())
        elif item_type == "tool_use":
            name = item.get("name", "unknown")
            inp = item.get("input", {})
            summary = _tool_input_summary(name, inp)
            parts.append(f"{_BOLD}{_CYAN}[tool: {name}]{_RESET} {summary}")
        elif item_type == "thinking":
            thinking = item.get("thinking", "")
            if thinking.strip():
                parts.append(f"{_DIM}[thinking...] {_truncate(thinking, 100)}{_RESET}")
        elif item_type == "tool_result":
            content = item.get("content", "")
            if isinstance(content, list):
                texts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                content = " ".join(texts)
            parts.append(f"{_DIM}[tool result] {_truncate(str(content))}{_RESET}")
    return "\n".join(parts) if parts else None


def _format_user(obj: dict) -> str | None:
    message = obj.get("message", {})
    contents = message.get("content", [])
    if not contents:
        return None
    parts: list[str] = []
    for item in contents:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            content = item.get("content", "")
            if isinstance(content, list):
                texts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                content = " ".join(texts)
            parts.append(f"{_DIM}[tool result] {_truncate(str(content))}{_RESET}")
    return "\n".join(parts) if parts else None


def _format_result(obj: dict) -> str:
    subtype = obj.get("subtype", "unknown")
    duration_ms = obj.get("duration_ms")
    result_text = obj.get("result", "")
    duration_str = ""
    if duration_ms is not None:
        duration_str = f" in {duration_ms / 1000:.1f}s"
    if subtype == "success":
        return (
            f"{_BOLD}{_GREEN}[completed{duration_str}]{_RESET} "
            f"{_truncate(result_text, 300)}"
        )
    return f"{_BOLD}{_RED}[failed{duration_str}]{_RESET} {_truncate(result_text, 300)}"


def _tool_input_summary(name: str, inp: dict) -> str:
    if name == "Read" and "file_path" in inp:
        return inp["file_path"]
    if name == "Edit" and "file_path" in inp:
        old = _truncate(inp.get("old_string", ""), 60)
        return f"{inp['file_path']}: {old}"
    if name == "Write" and "file_path" in inp:
        return inp["file_path"]
    if name == "Bash" and "command" in inp:
        return _truncate(inp["command"], 100)
    if name == "Grep" and "pattern" in inp:
        return inp["pattern"]
    if name == "Glob" and "pattern" in inp:
        return inp["pattern"]
    keys = list(inp.keys())[:3]
    return ", ".join(f"{k}=..." for k in keys)


def tail_log(log_path: Path) -> None:
    offset = 0
    if log_path.exists():
        offset = log_path.stat().st_size
    lines_buffer: list[str] = []
    try:
        while True:
            new_data = _read_new_lines(log_path, offset)
            if new_data:
                offset += sum(len(line.encode("utf-8")) + 1 for line in new_data)
                lines_buffer.extend(new_data)
            _render(lines_buffer)
            if _check_quit():
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _read_new_lines(path: Path, offset: int) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            text = f.read()
    except OSError:
        return []
    if not text:
        return []
    lines = text.split("\n")
    if not text.endswith("\n"):
        lines = lines[:-1]
    return [ln for ln in lines if ln.strip()]


def _render(lines: list[str]) -> None:
    cols, rows = shutil.get_terminal_size((80, 24))
    sys.stdout.write("\033[H\033[J")
    header = f"{_BOLD}--- Agent Log Viewer (press 'q' to exit) ---{_RESET}"
    sys.stdout.write(header + "\n")
    display_lines: list[str] = []
    for raw_line in lines:
        formatted = parse_jsonl_line(raw_line)
        if formatted is not None:
            display_lines.append(formatted)
    if not display_lines:
        display_lines = [f"{_YELLOW}Waiting for agent output...{_RESET}"]
    max_content_lines = rows - 3
    visible = display_lines[-max_content_lines:]
    for line in visible:
        for sub_line in line.split("\n"):
            sys.stdout.write(sub_line[:cols] + "\n")
    sys.stdout.flush()


def _check_quit() -> bool:
    if not sys.stdin.isatty():
        return False
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if readable:
        char = sys.stdin.read(1)
        if char == "q":
            return True
    return False
