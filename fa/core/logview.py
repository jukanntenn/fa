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


_ANSI_CSI_END = frozenset(chr(c) for c in range(0x40, 0x7F))
_SGR_CLOSE_CATEGORIES = {
    "22": {"intensity"},
    "23": {"italic"},
    "24": {"underline"},
    "25": {"blink"},
    "27": {"inverse"},
    "28": {"hidden"},
    "29": {"strike"},
    "39": {"fg"},
    "49": {"bg"},
}


def _update_active_sgr(params: str, active_sgr: set[str]) -> None:
    codes = params.split(";") if params else ["0"]
    i = 0
    while i < len(codes):
        code = codes[i] or "0"
        if code == "0":
            active_sgr.clear()
        elif code in _SGR_CLOSE_CATEGORIES:
            active_sgr.difference_update(_SGR_CLOSE_CATEGORIES[code])
        elif code in {"1", "2"}:
            active_sgr.add("intensity")
        elif code == "3":
            active_sgr.add("italic")
        elif code == "4":
            active_sgr.add("underline")
        elif code == "5":
            active_sgr.add("blink")
        elif code == "7":
            active_sgr.add("inverse")
        elif code == "8":
            active_sgr.add("hidden")
        elif code == "9":
            active_sgr.add("strike")
        elif code in {
            "30",
            "31",
            "32",
            "33",
            "34",
            "35",
            "36",
            "37",
            "90",
            "91",
            "92",
            "93",
            "94",
            "95",
            "96",
            "97",
        }:
            active_sgr.add("fg")
        elif code in {
            "40",
            "41",
            "42",
            "43",
            "44",
            "45",
            "46",
            "47",
            "100",
            "101",
            "102",
            "103",
            "104",
            "105",
            "106",
            "107",
        }:
            active_sgr.add("bg")
        elif code in {"38", "48"}:
            active_sgr.add("fg" if code == "38" else "bg")
            if i + 1 < len(codes) and codes[i + 1] == "5":
                i += 2
            elif i + 1 < len(codes) and codes[i + 1] == "2":
                i += 4
        i += 1


def _truncate_to_visible(line: str, max_cols: int) -> str:
    if max_cols <= 0:
        return ""
    result: list[str] = []
    visible = 0
    i = 0
    active_sgr: set[str] = set()
    while i < len(line):
        if visible >= max_cols:
            break
        ch = line[i]
        if ch == "\x1b" and i + 1 < len(line) and line[i + 1] == "[":
            j = i + 2
            while j < len(line) and line[j] not in _ANSI_CSI_END:
                j += 1
            if j >= len(line):
                break
            seq = line[i : j + 1]
            result.append(seq)
            if seq.endswith("m"):
                _update_active_sgr(seq[2:-1], active_sgr)
            i = j + 1
            continue
        result.append(ch)
        visible += 1
        i += 1
    text = "".join(result)
    if active_sgr:
        text += _RESET
    return text


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
            parts.append(
                f"{_DIM}[tool result]{_RESET}\n{_truncate(str(content), 2000, preserve_newlines=True)}"
            )
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
            parts.append(
                f"{_DIM}[tool result]{_RESET}\n{_truncate(str(content), 2000, preserve_newlines=True)}"
            )
    return "\n".join(parts) if parts else None


def _format_result(obj: dict) -> str:
    subtype = obj.get("subtype", "unknown")
    duration_ms = obj.get("duration_ms")
    result_text = obj.get("result", "")
    duration_str = ""
    if duration_ms is not None:
        duration_str = f" in {duration_ms / 1000:.1f}s"
    result = str(result_text).strip()
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
        self._close_requested = threading.Event()
        self._drain_lock = threading.Lock()

    def start_round(self, round_index: int, log_path: Path) -> None:
        with self._drain_lock:
            self._current_round = round_index
            self._current_log = log_path
            self._last_log = None
            self._log_offset = 0
            text = (
                f"{_DIM}--- Round {round_index}/{self.total_rounds} started ---{_RESET}"
            )
            self._entries.append(Entry(round_index=round_index, text=text))
            if self._scroll_offset > 0:
                self._scroll_offset += text.count("\n") + 1

    def end_round(self, duration: float) -> None:
        with self._drain_lock:
            self._drain_current_log_unlocked()
            text = f"{_DIM}--- Round {self._current_round}/{self.total_rounds} completed ({duration:.1f}s) ---{_RESET}"
            self._entries.append(Entry(round_index=self._current_round, text=text))
            if self._scroll_offset > 0:
                self._scroll_offset += text.count("\n") + 1

    def mark_failed(self) -> None:
        self._task_failed.set()

    def mark_done(self) -> None:
        self._task_done.set()

    def request_close(self) -> None:
        self._close_requested.set()

    def run(self) -> None:
        self._close_requested.clear()
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
        if self._close_requested.is_set():
            return True
        if not sys.stdin.isatty():
            if self._task_done.is_set() or self._task_failed.is_set():
                return True
        return False

    def _drain_current_log(self) -> None:
        with self._drain_lock:
            self._drain_current_log_unlocked()

    def _drain_current_log_unlocked(self) -> None:
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
                self._entries.append(
                    Entry(round_index=self._current_round, text=formatted)
                )
                if self._scroll_offset > 0:
                    self._scroll_offset += formatted.count("\n") + 1

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
                self._close_requested.set()
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
            with self._drain_lock:
                self._scroll_offset = 10**6
        elif seq == "\x1b[F":
            with self._drain_lock:
                self._scroll_offset = 0

    def _scroll_up(self, count: int) -> None:
        with self._drain_lock:
            self._scroll_offset += count

    def _scroll_down(self, count: int) -> None:
        with self._drain_lock:
            self._scroll_offset = max(0, self._scroll_offset - count)

    def _page_size(self) -> int:
        _, rows = shutil.get_terminal_size((80, 24))
        return max(1, rows - 3)

    def _render(self) -> None:
        cols, rows = shutil.get_terminal_size((80, 24))
        if cols < 20:
            cols = 80
        rows = max(1, rows)

        with self._drain_lock:
            entries_snapshot = list(self._entries)
            scroll_offset = self._scroll_offset
            current_round = self._current_round
            is_waiting = (
                self._current_log is not None
                and not self._current_log.exists()
                and not self._task_done.is_set()
                and not self._task_failed.is_set()
            )

        header = _truncate_to_visible(self._render_header_with(current_round), cols)
        footer_text = self._render_footer()
        footer = (
            _truncate_to_visible(footer_text, cols) if footer_text is not None else None
        )
        show_header = rows >= 3
        show_footer = rows >= 3 and footer is not None
        reserved = (1 if show_header else 0) + (1 if show_footer else 0)
        content_height = max(1, rows - reserved)

        body_lines = self._render_body_lines_from(entries_snapshot, cols, is_waiting)
        if scroll_offset == 0:
            visible = body_lines[-content_height:]
        else:
            scroll = min(scroll_offset, max(0, len(body_lines) - content_height))
            end = len(body_lines) - scroll
            start = max(0, end - content_height)
            visible = body_lines[start:end]
            if start > 0:
                visible = [
                    _truncate_to_visible(f"{_DIM}[-- more above --]{_RESET}", cols)
                ] + visible[1:]
            if end < len(body_lines):
                visible = visible[:-1] + [
                    _truncate_to_visible(
                        f"{_DIM}[-- new output below --]{_RESET}", cols
                    )
                ]

        output_parts: list[str] = []
        if show_header:
            output_parts.append(header)
        output_parts.extend(visible)
        if show_footer:
            output_parts.append(footer)

        output = "\033[H\033[J" + "\n".join(output_parts[:rows])
        sys.stdout.write(output)
        sys.stdout.flush()

    def _render_body_lines_from(
        self, entries: list[Entry], cols: int, is_waiting: bool
    ) -> list[str]:
        waiting = _truncate_to_visible(
            f"{_YELLOW}Waiting for agent output...{_RESET}", cols
        )
        if not entries:
            return [waiting]
        lines: list[str] = []
        for entry in entries:
            for sub_line in entry.text.split("\n"):
                if not sub_line:
                    lines.append("")
                else:
                    lines.append(_truncate_to_visible(sub_line, cols))
        if is_waiting:
            lines.append(waiting)
        return lines

    def _render_footer(self) -> str | None:
        if self._task_done.is_set():
            return f"{_GREEN}Task completed. Press 'q' to return.{_RESET}"
        if self._task_failed.is_set():
            return f"{_RED}Task failed. Press 'q' to return.{_RESET}"
        return None

    def _render_header_with(self, current_round: int) -> str:
        if current_round > 0:
            return (
                f'{_BOLD}--- Task "{self.slug}" Round '
                f"{current_round}/{self.total_rounds} (press 'q' to return) ---{_RESET}"
            )
        return f"{_BOLD}--- Task \"{self.slug}\" (press 'q' to return) ---{_RESET}"


class ViewerController:
    def __init__(self, viewer: TaskViewer) -> None:
        self.viewer = viewer
        self._thread: threading.Thread | None = None

    def is_open(self) -> bool:
        if self._thread is None:
            return False
        if self._thread.is_alive():
            return True
        self._thread.join(timeout=0)
        self._thread = None
        return False

    def open(self) -> None:
        if self.is_open():
            return
        self._thread = threading.Thread(target=self.viewer.run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.viewer.request_close()

    def wait_closed(self, timeout: float | None = None) -> None:
        if self._thread is None:
            return
        self._thread.join(timeout=timeout)
        if not self._thread.is_alive():
            self._thread = None
