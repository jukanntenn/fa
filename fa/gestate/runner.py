from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from fa.core.logview import _LIVE_VIEWER_TOOLS, TaskViewer, ViewerController
from fa.core.tty import _main_session_cbreak, _read_main_session_key
from fa.gestate.prompting import _build_tool_cmd_for_prompt


def _run_tool_with_optional_viewer(
    *,
    tool: str,
    prompt: str,
    log_path: Path,
    logger: logging.Logger,
    viewer: TaskViewer | None,
    round_index: int,
    viewer_controller: ViewerController | None = None,
    prompt_path: Path | None = None,
) -> int | None:
    cmd, prompt_stdin = _build_tool_cmd_for_prompt(tool, prompt, prompt_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if viewer is None or tool not in _LIVE_VIEWER_TOOLS:
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                result = subprocess.run(
                    cmd,
                    input=prompt_stdin,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        except OSError:
            return None
        return int(result.returncode)

    return_code: int | None = None

    def _worker() -> None:
        nonlocal return_code
        started_at = time.monotonic()
        viewer_log_path = log_path.with_name(f"{log_path.stem}-viewer.log")
        viewer.start_round(round_index, log_path, viewer_log_path)
        try:
            try:
                with log_path.open("w", encoding="utf-8") as log_file:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE
                        if prompt_stdin is not None
                        else subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    proc.communicate(input=prompt_stdin)
                    return_code = int(proc.returncode)
            except OSError:
                return_code = None
        finally:
            viewer.end_round(time.monotonic() - started_at)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    if not sys.stdin.isatty():
        worker.join()
    else:
        assert viewer_controller is not None
        logger.info("Agent running. Press Ctrl+L to open the log viewer.")
        while worker.is_alive():
            if viewer_controller.is_open():
                time.sleep(0.2)
                continue
            with _main_session_cbreak():
                key = _read_main_session_key()
            if key == "\x0c":
                viewer_controller.open()
    worker.join()
    viewer._drain_current_log()
    return return_code
