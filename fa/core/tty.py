from __future__ import annotations

import contextlib
import select
import sys


@contextlib.contextmanager
def _main_session_cbreak():
    if not sys.stdin.isatty():
        yield
        return
    original_tty = None
    try:
        import termios as termios_module
        import tty as tty_module

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
