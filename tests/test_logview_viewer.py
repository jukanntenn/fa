from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core.logview_parse import _RESET
from fa.core.logview_viewer import Entry, TaskViewer, ViewerController


def test_viewer_reports_open_and_close_state() -> None:
    viewer = TaskViewer("task", total_rounds=1)

    assert not viewer._close_requested.is_set()
    assert not viewer._task_done.is_set()
    viewer.mark_done()
    assert viewer._task_done.is_set()
    viewer.request_close()
    assert viewer._close_requested.is_set()


def test_viewer_adds_round_markers_and_body_entries() -> None:
    viewer = TaskViewer("task", total_rounds=2)
    viewer.start_round(1, Path("round-1.log"))
    viewer._entries.append(Entry(round_index=1, text="round one output"))
    viewer.end_round(1.0)
    viewer.start_round(2, Path("round-2.log"))
    viewer._entries.append(Entry(round_index=2, text="round two output"))

    lines = viewer._render_body_lines_from(viewer._entries, 80, is_waiting=False)

    joined = "\n".join(lines)
    assert "Round 1/2 started" in joined
    assert "round one output" in joined
    assert "Round 1/2 completed" in joined
    assert "Round 2/2 started" in joined
    assert "round two output" in joined
    assert viewer._current_round == 2
    assert viewer._current_log == Path("round-2.log")


def test_viewer_persists_round_markers_and_parsed_entries() -> None:
    with TemporaryDirectory() as tempdir:
        raw_log = Path(tempdir) / "round-1-claude.log"
        viewer_log = Path(tempdir) / "round-1-claude-viewer.log"
        raw_log.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "hello from agent"}]
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        viewer = TaskViewer("task", total_rounds=1, tool="claude")
        viewer.start_round(1, raw_log, viewer_log)
        viewer._drain_current_log()
        viewer.end_round(0.1)

        persisted = viewer_log.read_text(encoding="utf-8")

    assert "Round 1/1 started" in persisted
    assert "hello from agent" in persisted
    assert "Round 1/1 completed" in persisted
    assert "\x1b[" not in persisted


def test_body_lines_truncate_by_visible_width() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    entries = [Entry(round_index=1, text="\033[31mabcdef")]

    assert viewer._render_body_lines_from(entries, 3, is_waiting=False) == [
        f"\033[31mabc{_RESET}"
    ]


def test_body_lines_include_ansi_safe_waiting_line() -> None:
    viewer = TaskViewer("task", total_rounds=1)

    lines = viewer._render_body_lines_from([], 10, is_waiting=True)

    assert len(lines) == 1
    assert lines[0].startswith("\033[33mWaiting f")
    assert lines[0].endswith(_RESET)


def test_render_suppresses_chrome_on_tiny_terminal() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, Path("round-1.log"))
    viewer._entries = [Entry(round_index=1, text="body line")]
    viewer.mark_done()

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 2)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert output == "\033[H\033[Jbody line"


def test_viewer_controller_open_does_not_start_duplicate_thread() -> None:
    viewer_started = threading.Event()
    release_viewer = threading.Event()
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)

    def fake_run() -> None:
        viewer_started.set()
        release_viewer.wait(timeout=1)

    with patch.object(viewer, "run", side_effect=fake_run) as run_viewer:
        try:
            controller.open()
            assert viewer_started.wait(timeout=1)
            controller.open()

            assert run_viewer.call_count == 1
            assert controller.is_open()
        finally:
            release_viewer.set()
            controller.wait_closed(timeout=1)

    assert not controller.is_open()


def test_viewer_controller_close_requests_viewer_close() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)

    controller.close()

    assert viewer._close_requested.is_set()


def test_viewer_controller_open_reopens_after_viewer_exits() -> None:
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)

    with patch.object(viewer, "run") as run_viewer:
        controller.open()
        deadline = time.monotonic() + 1
        while controller.is_open() and time.monotonic() < deadline:
            time.sleep(0.01)
        controller.open()
        controller.wait_closed(timeout=1)

    assert run_viewer.call_count == 2


def test_viewer_parse_log_line_claude_uses_jsonl():
    viewer = TaskViewer("task", total_rounds=1, tool="claude")
    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
    )
    result = viewer._parse_log_line(line)
    assert result is not None
    assert "hi" in result


def test_viewer_parse_log_line_codex_uses_codex_parser():
    viewer = TaskViewer("task", total_rounds=1, tool="codex")
    result = viewer._parse_log_line("codex")
    assert result is None


def test_viewer_read_log_lines_returns_empty_for_missing_file():
    viewer = TaskViewer("task", total_rounds=1)
    result = viewer._read_log_lines(Path("/nonexistent/file.log"), 0)
    assert result == []


def test_viewer_read_log_lines_reads_from_offset(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("line1\nline2\n", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1)
    result = viewer._read_log_lines(log, 0)
    assert result == ["line1", "line2"]


def test_viewer_read_log_lines_respects_offset(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("line1\nline2\n", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1)
    offset = len("line1\n")
    result = viewer._read_log_lines(log, offset)
    assert result == ["line2"]


def test_viewer_read_log_lines_ignores_incomplete_trailing_line(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("line1\nline2", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1)
    result = viewer._read_log_lines(log, 0)
    assert result == ["line1"]


def test_viewer_render_header_with_no_round():
    viewer = TaskViewer("my-task", total_rounds=3)
    result = viewer._render_header_with(0)
    assert "my-task" in result
    assert "Round" not in result


def test_viewer_render_header_with_round():
    viewer = TaskViewer("my-task", total_rounds=3)
    result = viewer._render_header_with(2)
    assert "Round 2/3" in result


def test_viewer_render_footer_done():
    viewer = TaskViewer("task", total_rounds=1)
    viewer.mark_done()
    result = viewer._render_footer()
    assert result is not None
    assert "completed" in result


def test_viewer_render_footer_failed():
    viewer = TaskViewer("task", total_rounds=1)
    viewer.mark_failed()
    result = viewer._render_footer()
    assert result is not None
    assert "failed" in result


def test_viewer_render_footer_not_done():
    viewer = TaskViewer("task", total_rounds=1)
    result = viewer._render_footer()
    assert result is None


def test_viewer_body_lines_waiting_with_entries():
    viewer = TaskViewer("task", total_rounds=1)
    entries = [Entry(round_index=1, text="existing")]
    lines = viewer._render_body_lines_from(entries, 80, is_waiting=True)
    joined = "\n".join(lines)
    assert "existing" in joined
    assert "Waiting" in joined


def test_viewer_body_lines_waiting_without_entries():
    viewer = TaskViewer("task", total_rounds=1)
    lines = viewer._render_body_lines_from([], 80, is_waiting=False)
    assert len(lines) == 1
    assert "Waiting" in lines[0]


def test_viewer_controller_wait_closed_no_thread():
    viewer = TaskViewer("task", total_rounds=1)
    controller = ViewerController(viewer)
    controller.wait_closed()


def test_viewer_scroll_offset_increases_on_append(tmp_path: Path) -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, tmp_path / "round-1.log")
    viewer._scroll_offset = 5
    viewer._append_entry(Entry(round_index=1, text="new line"))
    assert viewer._scroll_offset == 6


def test_viewer_render_with_footer(tmp_path: Path) -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, tmp_path / "round-1.log")
    viewer._entries = [Entry(round_index=1, text="body")]
    viewer.mark_done()

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 5)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert "completed" in output


def test_viewer_render_with_scroll(tmp_path: Path) -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, tmp_path / "round-1.log")
    viewer._entries = [Entry(round_index=1, text=f"line {i}") for i in range(20)]
    viewer._scroll_offset = 10

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 5)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert "more above" in output


def test_viewer_render_narrow_terminal_uses_80_cols(tmp_path: Path) -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, tmp_path / "round-1.log")
    viewer._entries = [Entry(round_index=1, text="body text")]

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(10, 5)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert len(output.split("\n")[0]) <= 80


def test_viewer_drain_current_log_unlocked_no_current_log():
    viewer = TaskViewer("task", total_rounds=1)
    viewer._drain_current_log_unlocked()
    assert len(viewer._entries) == 0


def test_viewer_drain_uses_codex_parser(tmp_path: Path) -> None:
    log = tmp_path / "round-1.log"
    log.write_text("user\ncodex\nHello world\n", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1, tool="codex")
    viewer.start_round(1, log)
    viewer._drain_current_log()
    joined = "\n".join(e.text for e in viewer._entries)
    assert "[codex]" in joined


def test_viewer_read_log_lines_handles_os_error(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("data\n", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1)
    with patch.object(Path, "open", side_effect=OSError("permission denied")):
        result = viewer._read_log_lines(log, 0)
    assert result == []


def test_viewer_read_log_lines_returns_empty_for_empty_read(tmp_path: Path) -> None:
    log = tmp_path / "empty.log"
    log.write_text("", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=1)
    result = viewer._read_log_lines(log, 0)
    assert result == []


def test_viewer_scroll_up_increments_offset():
    viewer = TaskViewer("task", total_rounds=1)
    viewer._scroll_up(3)
    assert viewer._scroll_offset == 3


def test_viewer_scroll_down_decrements_offset():
    viewer = TaskViewer("task", total_rounds=1)
    viewer._scroll_offset = 5
    viewer._scroll_down(2)
    assert viewer._scroll_offset == 3


def test_viewer_scroll_down_clamps_to_zero():
    viewer = TaskViewer("task", total_rounds=1)
    viewer._scroll_offset = 1
    viewer._scroll_down(5)
    assert viewer._scroll_offset == 0


def test_viewer_page_size():
    viewer = TaskViewer("task", total_rounds=1)
    with patch(
        "fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 30)
    ):
        size = viewer._page_size()
    assert size == 27


def test_viewer_render_with_scroll_new_output_below(tmp_path: Path) -> None:
    viewer = TaskViewer("task", total_rounds=1)
    viewer.start_round(1, tmp_path / "round-1.log")
    viewer._entries = [Entry(round_index=1, text=f"line {i}") for i in range(20)]
    viewer._scroll_offset = 5

    stdout = io.StringIO()
    with (
        patch("fa.core.logview_viewer.shutil.get_terminal_size", return_value=(80, 5)),
        patch("fa.core.logview_viewer.sys.stdout", stdout),
    ):
        viewer._render()

    output = stdout.getvalue()
    assert "new output below" in output


def test_viewer_drain_resets_offset_on_new_log(tmp_path: Path) -> None:
    log1 = tmp_path / "round-1.log"
    log2 = tmp_path / "round-2.log"
    log1.write_text("line1\n", encoding="utf-8")
    log2.write_text("line2\n", encoding="utf-8")
    viewer = TaskViewer("task", total_rounds=2, tool="claude")
    viewer.start_round(1, log1)
    viewer._drain_current_log()
    viewer.start_round(2, log2)
    viewer._drain_current_log()
    joined = "\n".join(e.text for e in viewer._entries if "Round" not in e.text)
    assert "line1" in joined
    assert "line2" in joined
