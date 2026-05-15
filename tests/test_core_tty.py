from __future__ import annotations

import sys
from unittest.mock import patch

from fa.core.tty import _read_main_session_key, cbreak_session


@patch("sys.stdin.isatty", return_value=False)
def test_cbreak_session_non_tty(mock_isatty):
    with cbreak_session():
        pass


@patch("sys.stdin.isatty", return_value=True)
def test_cbreak_session_import_error(mock_isatty):
    with patch.dict("sys.modules", {"termios": None, "tty": None}):
        with cbreak_session():
            pass


@patch("sys.stdin.isatty", return_value=True)
@patch("termios.tcgetattr", side_effect=Exception("error"))
@patch("termios.tcsetattr")
@patch("tty.setcbreak")
def test_cbreak_session_tcgetattr_error(
    mock_setcbreak, mock_tcsetattr, mock_tcgetattr, mock_isatty
):
    with cbreak_session():
        pass
    mock_setcbreak.assert_not_called()


@patch("sys.stdin.isatty", return_value=True)
@patch("sys.stdin.fileno", return_value=0)
@patch("termios.tcgetattr")
@patch("termios.tcsetattr")
@patch("tty.setcbreak")
def test_cbreak_session_success(
    mock_setcbreak, mock_tcsetattr, mock_tcgetattr, mock_stdin_fileno, mock_isatty
):
    mock_tcgetattr.return_value = [0, 0, 0]
    with cbreak_session():
        pass
    mock_tcgetattr.assert_called_once_with(0)
    mock_setcbreak.assert_called_once_with(0)
    mock_tcsetattr.assert_called_once()


@patch("sys.stdin.isatty", return_value=False)
def test_read_main_session_key_non_tty(mock_isatty):
    result = _read_main_session_key()
    assert result is None


@patch("sys.stdin.isatty", return_value=True)
@patch("select.select", return_value=([], [], []))
def test_read_main_session_key_no_readable(mock_select, mock_isatty):
    result = _read_main_session_key()
    assert result is None


@patch("sys.stdin.isatty", return_value=True)
@patch("select.select", return_value=([sys.stdin], [], []))
@patch("sys.stdin.read", return_value="a")
def test_read_main_session_key_success(mock_read, mock_select, mock_isatty):
    result = _read_main_session_key()
    assert result == "a"


@patch("sys.stdin.isatty", return_value=True)
@patch("select.select", side_effect=OSError("error"))
def test_read_main_session_key_oserror(mock_select, mock_isatty):
    result = _read_main_session_key()
    assert result is None
