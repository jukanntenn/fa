from __future__ import annotations

import dataclasses
import json
import logging
import select
import shutil
import sys
import threading
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


@dataclasses.dataclass
class Entry:
    round_index: int
    text: str


def _truncate(text: str, max_len: int = 200, preserve_newlines: bool = False) -> str:
    if preserve_newlines:
        text = text.strip()
    else:
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
                parts.append(_truncate(text, 4000, preserve_newlines=True))
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
    result = _truncate(str(result_text), 4000, preserve_newlines=True)
    if subtype == "success":
        return f"{_BOLD}{_GREEN}[completed{duration_str}]{_RESET}\n{result}"
    return f"{_BOLD}{_RED}[failed{duration_str}]{_RESET}\n{result}"


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


class TaskViewer:
    def __init__(self, slug: str, total_rounds: int) -> None:
        self.slug = slug
        self.total_rounds = total_rounds
        self._entries: list[Entry] = []
        self._scroll_offset = 0
        self._current_round = 0
        self._current_log: Path | None = None
        self._last_log: Path | None = None
        self._log_offset = 0
        self._original_tty = None
        self._task_done = threading.Event()
        self._task_failed = threading.Event()
        self._exit_requested = threading.Event()

    @property
    def user_exited(self) -> bool:
        return self._exit_requested.is_set()

    def start_round(self, round_index: int, log_path: Path) -> None:
        self._current_round = round_index
        self._current_log = log_path
        self._last_log = None
        self._log_offset = 0
        if round_index > 1:
            self._append_entry(
                f"{_DIM}--- Starting Round {round_index}/{self.total_rounds} ---{_RESET}"
            )

    def end_round(self, duration: float) -> None:
        self._drain_current_log()
        self._append_entry(
            f"{_DIM}--- Round {self._current_round}/{self.total_rounds} completed ({duration:.1f}s) ---{_RESET}"
        )

    def mark_failed(self) -> None:
        self._task_failed.set()

    def mark_done(self) -> None:
        self._task_done.set()

    def run(self) -> None:
        self._enter_cbreak()
        try:
            self._run_loop()
        finally:
            self._leave_cbreak()
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _enter_cbreak(self) -> None:
        if not sys.stdin.isatty():
            return
        import termios as termios_module
        import tty as tty_module

        try:
            self._original_tty = termios_module.tcgetattr(sys.stdin.fileno())
            tty_module.setcbreak(sys.stdin.fileno())
        except Exception:
            self._original_tty = None

    def _leave_cbreak(self) -> None:
        if self._original_tty is None:
            return
        import termios as termios_module

        try:
            termios_module.tcsetattr(
                sys.stdin.fileno(), termios_module.TCSADRAIN, self._original_tty
            )
        except Exception:
            pass
        self._original_tty = None

    def _run_loop(self) -> None:
        while True:
            self._drain_current_log()
            self._handle_input()
            self._render()
            if self._should_exit():
                break
            time.sleep(0.3)

    def _should_exit(self) -> bool:
        if self._exit_requested.is_set():
            return True
        if not sys.stdin.isatty():
            if self._task_done.is_set() or self._task_failed.is_set():
                return True
        return False

    def _drain_current_log(self) -> None:
        if self._current_log is None:
            return
        if self._current_log != self._last_log:
            self._last_log = self._current_log
            self._log_offset = 0
        new_lines = self._read_log_lines(self._current_log, self._log_offset)
        if not new_lines:
            return
        self._log_offset += sum(len(line.encode("utf-8")) + 1 for line in new_lines)
        for raw_line in new_lines:
            formatted = parse_jsonl_line(raw_line)
            if formatted is not None:
                self._append_entry(formatted)

    def _append_entry(self, text: str) -> None:
        self._entries.append(Entry(round_index=self._current_round, text=text))
        if self._scroll_offset > 0:
            self._scroll_offset += text.count("\n") + 1

    def _read_log_lines(self, path: Path, offset: int) -> list[str]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as file:
                file.seek(offset)
                text = file.read()
        except OSError:
            return []
        if not text:
            return []
        lines = text.split("\n")
        if not text.endswith("\n"):
            lines = lines[:-1]
        return [line for line in lines if line.strip()]

    def _handle_input(self) -> None:
        if not sys.stdin.isatty():
            return
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if not readable:
                return
            ch = sys.stdin.read(1)
            if ch == "q":
                self._exit_requested.set()
                return
            if ch == "\x1b":
                self._handle_escape_sequence()

    def _handle_escape_sequence(self) -> None:
        seq = "\x1b"
        try:
            for _ in range(3):
                readable, _, _ = select.select([sys.stdin], [], [], 0.02)
                if not readable:
                    break
                seq += sys.stdin.read(1)
                if seq in {
                    "\x1b[A",
                    "\x1b[B",
                    "\x1b[H",
                    "\x1b[F",
                    "\x1b[5~",
                    "\x1b[6~",
                }:
                    break
        except Exception:
            return
        if seq == "\x1b[A":
            self._scroll_up(1)
        elif seq == "\x1b[B":
            self._scroll_down(1)
        elif seq == "\x1b[5~":
            self._scroll_up(self._page_size())
        elif seq == "\x1b[6~":
            self._scroll_down(self._page_size())
        elif seq == "\x1b[H":
            self._scroll_offset = 10**6
        elif seq == "\x1b[F":
            self._scroll_offset = 0

    def _scroll_up(self, count: int) -> None:
        self._scroll_offset += count

    def _scroll_down(self, count: int) -> None:
        self._scroll_offset = max(0, self._scroll_offset - count)

    def _page_size(self) -> int:
        _, rows = shutil.get_terminal_size((80, 24))
        return max(1, rows - 3)

    def _render(self) -> None:
        cols, rows = shutil.get_terminal_size((80, 24))
        content_height = max(1, rows - 2)
        lines = [self._render_header()]
        body_lines = self._render_body_lines(cols)
        if self._scroll_offset == 0:
            visible = body_lines[-content_height:]
        else:
            scroll = min(self._scroll_offset, max(0, len(body_lines) - content_height))
            end = len(body_lines) - scroll
            start = max(0, end - content_height)
            visible = body_lines[start:end]
            if start > 0:
                visible = [f"{_DIM}[-- more above --]{_RESET}"] + visible[1:]
            if end < len(body_lines):
                visible = visible[:-1] + [f"{_DIM}[-- new output below --]{_RESET}"]
        lines.extend(visible)
        footer = self._render_footer()
        if footer is not None:
            lines.append(footer)
        output = "\033[H\033[J" + "\n".join(lines[:rows])
        sys.stdout.write(output)
        sys.stdout.flush()

    def _render_body_lines(self, cols: int) -> list[str]:
        if not self._entries:
            return [f"{_YELLOW}Waiting for agent output...{_RESET}"]
        lines: list[str] = []
        for entry in self._entries:
            for sub_line in entry.text.split("\n"):
                if not sub_line:
                    lines.append("")
                else:
                    lines.append(sub_line[:cols])
        return lines

    def _render_footer(self) -> str | None:
        if self._task_done.is_set():
            return f"{_GREEN}Task completed. Press 'q' to exit.{_RESET}"
        if self._task_failed.is_set():
            return f"{_RED}Task failed. Press 'q' to exit.{_RESET}"
        return None

    def _render_header(self) -> str:
        if self._current_round > 0:
            return (
                f'{_BOLD}--- Task "{self.slug}" Round '
                f"{self._current_round}/{self.total_rounds} (press 'q' to exit) ---{_RESET}"
            )
        return f"{_BOLD}--- Task \"{self.slug}\" (press 'q' to exit) ---{_RESET}"
