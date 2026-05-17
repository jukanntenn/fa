from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fa.core.subprocess import run_tool, run_tool_subprocess


def test_run_tool_subprocess_success():
    with tempfile.TemporaryDirectory() as d:
        log_file = Path(d) / "test.log"
        result = run_tool_subprocess(["echo", "hello"], log_file)
        assert result == 0
        assert log_file.read_text() == "hello\n"


def test_run_tool_subprocess_oserror():
    with tempfile.TemporaryDirectory() as d:
        log_file = Path(d) / "test.log"
        result = run_tool_subprocess(["nonexistent_command_xyz"], log_file)
        assert result == 1


def test_run_tool_subprocess_with_stdin_devnull():
    with tempfile.TemporaryDirectory() as d:
        log_file = Path(d) / "test.log"
        result = run_tool_subprocess(
            ["echo", "hello"],
            log_file,
            stdin=subprocess.DEVNULL,
        )
        assert result == 0
        assert log_file.read_text() == "hello\n"


def test_run_tool_subprocess_with_extra_env():
    with tempfile.TemporaryDirectory() as d:
        log_file = Path(d) / "test.log"
        result = run_tool_subprocess(
            [
                "python",
                "-c",
                "import os; print(os.environ.get('TEST_VAR', 'not_found'))",
            ],
            log_file,
            extra_env={"TEST_VAR": "test_value"},
        )
        assert result == 0
        assert "test_value" in log_file.read_text()


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_calls_build_tool_cmd(mock_run_subprocess, mock_build_cmd, tmp_path):
    mock_build_cmd.return_value = ["echo", "test"]
    mock_run_subprocess.return_value = 0
    logger = MagicMock()
    result = run_tool("test_tool", "test prompt", tmp_path / "log.txt", logger)
    mock_build_cmd.assert_called_once_with(
        "test_tool", "test prompt", agent=None, model=None, extra_args=None
    )
    assert result == 0


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_with_agent(mock_run_subprocess, mock_build_cmd, tmp_path):
    mock_build_cmd.return_value = ["echo", "test"]
    mock_run_subprocess.return_value = 0
    logger = MagicMock()
    result = run_tool(
        "test_tool", "test prompt", tmp_path / "log.txt", logger, agent="rectifier"
    )
    mock_build_cmd.assert_called_once_with(
        "test_tool", "test prompt", agent="rectifier", model=None, extra_args=None
    )
    assert result == 0


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_logs_debug(mock_run_subprocess, mock_build_cmd, tmp_path):
    mock_build_cmd.return_value = ["echo", "test"]
    mock_run_subprocess.return_value = 0
    logger = MagicMock()
    run_tool("test_tool", "test prompt", tmp_path / "log.txt", logger)
    logger.debug.assert_called_once()


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_returns_nonzero_on_failure(
    mock_run_subprocess, mock_build_cmd, tmp_path
):
    mock_build_cmd.return_value = ["false"]
    mock_run_subprocess.return_value = 1
    logger = MagicMock()
    result = run_tool("test_tool", "test prompt", tmp_path / "log.txt", logger)
    assert result == 1


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_forwards_stdin(mock_run_subprocess, mock_build_cmd, tmp_path):
    mock_build_cmd.return_value = ["echo", "test"]
    mock_run_subprocess.return_value = 0
    logger = MagicMock()
    run_tool(
        "test_tool",
        "test prompt",
        tmp_path / "log.txt",
        logger,
        stdin=subprocess.DEVNULL,
    )
    mock_run_subprocess.assert_called_once_with(
        ["echo", "test"], tmp_path / "log.txt", None, stdin=subprocess.DEVNULL
    )


@patch("fa.core.subprocess.build_tool_cmd")
@patch("fa.core.subprocess.run_tool_subprocess")
def test_run_tool_default_stdin_is_none(mock_run_subprocess, mock_build_cmd, tmp_path):
    mock_build_cmd.return_value = ["echo", "test"]
    mock_run_subprocess.return_value = 0
    logger = MagicMock()
    run_tool("test_tool", "test prompt", tmp_path / "log.txt", logger)
    call_kwargs = mock_run_subprocess.call_args
    assert call_kwargs.kwargs.get("stdin") is None
