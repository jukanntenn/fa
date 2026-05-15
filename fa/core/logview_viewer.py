from __future__ import annotations

import dataclasses
import select
import shutil
import sys
import threading
import time
from pathlib import Path

from fa.core.logview_parse import (
    _BOLD,
    _DIM,
    _GREEN,
    _RED,
    _RESET,
    _YELLOW,
    _strip_ansi,
    _truncate_to_visible,
    parse_codex_line,
    parse_jsonl_line,
)
from fa.core.tty import cbreak_session


@dataclasses.dataclass
class Entry:
    round_index: int
    text: str


class TaskViewer:
    def __init__(self, slug: str, total_rounds: int, tool: str = "claude") -> None:
        self.slug = slug
        self.total_rounds = total_rounds
        self.tool = tool
        self._parser_state: dict[str, str] = {}
        self._entries: list[Entry] = []
        self._scroll_offset = 0
        self._current_round = 0
        self._current_log: Path | None = None
        self._viewer_log_path: Path | None = None
        self._last_log: Path | None = None
        self._log_offset = 0
        self._task_done = threading.Event()
        self._task_failed = threading.Event()
        self._close_requested = threading.Event()
        self._drain_lock = threading.Lock()

    def start_round(
        self,
        round_index: int,
        log_path: Path,
        viewer_log_path: Path | None = None,
    ) -> None:
        with self._drain_lock:
            self._current_round = round_index
            self._current_log = log_path
            self._viewer_log_path = viewer_log_path
            self._last_log = None
            self._log_offset = 0
            self._parser_state = {}
            text = (
                f"{_DIM}--- Round {round_index}/{self.total_rounds} started ---{_RESET}"
            )
            self._append_entry(Entry(round_index=round_index, text=text))

    def end_round(self, duration: float) -> None:
        with self._drain_lock:
            self._drain_current_log_unlocked()
            text = f"{_DIM}--- Round {self._current_round}/{self.total_rounds} completed ({duration:.1f}s) ---{_RESET}"
            self._append_entry(Entry(round_index=self._current_round, text=text))

    def _append_entry(self, entry: Entry) -> None:
        self._entries.append(entry)
        if self._scroll_offset > 0:
            self._scroll_offset += entry.text.count("\n") + 1
        if self._viewer_log_path is None:
            return
        self._viewer_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._viewer_log_path.open("a", encoding="utf-8") as file:
            file.write(_strip_ansi(entry.text).rstrip() + "\n")

    def mark_failed(self) -> None:
        self._task_failed.set()

    def mark_done(self) -> None:
        self._task_done.set()

    def request_close(self) -> None:
        self._close_requested.set()

    def run(self) -> None:
        self._close_requested.clear()
        with cbreak_session():
            try:
                self._run_loop()
            finally:
                sys.stdout.write("\n")
                sys.stdout.flush()

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

    def _parse_log_line(self, raw_line: str) -> str | None:
        if self.tool == "codex":
            return parse_codex_line(raw_line, self._parser_state)
        return parse_jsonl_line(raw_line)

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
            formatted = self._parse_log_line(raw_line)
            if formatted is not None:
                self._append_entry(
                    Entry(round_index=self._current_round, text=formatted)
                )

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
        show_footer = show_header and footer is not None
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
        round_info = (
            f" Round {current_round}/{self.total_rounds}" if current_round > 0 else ""
        )
        return f"{_BOLD}--- Task \"{self.slug}\"{round_info} (press 'q' to return) ---{_RESET}"


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
