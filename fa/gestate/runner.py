from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fa.core.logview import LIVE_VIEWER_TOOLS, TaskViewer, ViewerController
from fa.core.tty import poll_keyboard_for_viewer
from fa.gestate.prompting import _build_tool_cmd_for_prompt


def _run_tool_simple(
    cmd: list[str],
    prompt_stdin: str | None,
    log_path: Path,
    env: dict[str, str] | None,
) -> int | None:
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            result = subprocess.run(
                cmd,
                input=prompt_stdin,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                env=env,
            )
    except OSError:
        return None
    return int(result.returncode)


def _run_tool_with_viewer(
    cmd: list[str],
    prompt_stdin: str | None,
    log_path: Path,
    env: dict[str, str] | None,
    viewer: TaskViewer,
    round_index: int,
    viewer_controller: ViewerController | None,
    logger: logging.Logger,
) -> int | None:
    return_code: int | None = None

    def _worker() -> None:
        nonlocal return_code
        started_at = time.monotonic()
        viewer_log_path = log_path.with_name(f"{log_path.stem}-viewer.log")
        viewer.start_round(round_index, log_path, viewer_log_path)
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
                    env=env,
                )
                proc.communicate(input=prompt_stdin)
                return_code = int(proc.returncode)
        except OSError:
            return_code = None
        finally:
            viewer.end_round(time.monotonic() - started_at)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    if not sys.stdin.isatty() or viewer_controller is None:
        worker.join()
    else:
        logger.info("Agent running. Press Ctrl+L to open the log viewer.")
        poll_keyboard_for_viewer(worker, viewer_controller, open_viewer=False)
    worker.join()
    viewer.drain()
    return return_code


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
    model: str | None = None,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> int | None:
    cmd, prompt_stdin = _build_tool_cmd_for_prompt(
        tool, prompt, prompt_path, model=model, extra_args=extra_args
    )
    env = {**os.environ, **extra_env} if extra_env else None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if viewer is None or tool not in LIVE_VIEWER_TOOLS:
        return _run_tool_simple(cmd, prompt_stdin, log_path, env)
    return _run_tool_with_viewer(
        cmd, prompt_stdin, log_path, env, viewer, round_index, viewer_controller, logger
    )
