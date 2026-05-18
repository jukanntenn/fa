from __future__ import annotations

import contextlib
import select
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fa.core.logview_viewer import ViewerController


@contextlib.contextmanager
def cbreak_session():
    if not sys.stdin.isatty():
        yield
        return
    try:
        import termios as termios_module
        import tty as tty_module
    except ImportError:
        yield
        return
    original_tty = None
    try:
        original_tty = termios_module.tcgetattr(sys.stdin.fileno())
        tty_module.setcbreak(sys.stdin.fileno())
    except Exception:
        yield
        return
    try:
        yield
    finally:
        if original_tty is not None:
            termios_module.tcsetattr(
                sys.stdin.fileno(), termios_module.TCSADRAIN, original_tty
            )


def _read_main_session_key() -> str | None:
    if not sys.stdin.isatty():
        return None
    try:
        readable, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not readable:
            return None
        return sys.stdin.read(1)
    except OSError:
        return None


def poll_keyboard_for_viewer(
    worker: threading.Thread,
    viewer_controller: ViewerController,
    open_viewer: bool,
) -> None:
    if open_viewer:
        viewer_controller.open()
    with cbreak_session():
        while worker.is_alive():
            if viewer_controller.is_open():
                time.sleep(0.2)
                continue
            key = _read_main_session_key()
            if key == "\x0c":
                viewer_controller.open()
