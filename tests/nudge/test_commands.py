from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from fa.cli import app

runner = CliRunner()


def test_nudge_help_shows_options():
    result = runner.invoke(app, ["nudge", "--help"])
    assert result.exit_code == 0
    assert "--tool" in result.output
    assert "--gestate-tool" in result.output
    assert "--max-iterations" in result.output
    assert "--quota-threshold" in result.output
    assert "--quota-buffer" in result.output
    assert "--prompt" in result.output
    assert "--gestate-max-rounds" in result.output
    assert "--gestate-run-rounds" in result.output
    assert "--gestate-run" in result.output


def test_nudge_calls_run_nudge_loop_with_defaults():
    with patch("fa.nudge.commands.run_nudge_loop", return_value=0) as mock_loop:
        result = runner.invoke(app, ["nudge"])
        assert result.exit_code == 0
        mock_loop.assert_called_once()
        call_kwargs = mock_loop.call_args[1]
        assert call_kwargs["tool"] == "claude"
        assert call_kwargs["gestate_tool"] == "claude"
        assert call_kwargs["max_iterations"] == 100
        assert call_kwargs["quota_threshold"] == 90.0
        assert call_kwargs["quota_buffer_seconds"] == 1800
        assert call_kwargs["prompt"] == "/nudging"
        assert call_kwargs["gestate_max_rounds"] == 10
        assert call_kwargs["gestate_run_rounds"] == 1
        assert call_kwargs["gestate_run"] is True


def test_nudge_passes_custom_options():
    with patch("fa.nudge.commands.run_nudge_loop", return_value=0) as mock_loop:
        result = runner.invoke(
            app,
            [
                "nudge",
                "--tool",
                "codex",
                "--gestate-tool",
                "ccr",
                "--max-iterations",
                "5",
                "--quota-threshold",
                "80",
                "--quota-buffer",
                "600",
                "--prompt",
                "/custom",
                "--gestate-max-rounds",
                "3",
                "--gestate-run-rounds",
                "2",
                "--no-gestate-run",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_loop.call_args[1]
        assert call_kwargs["tool"] == "codex"
        assert call_kwargs["gestate_tool"] == "ccr"
        assert call_kwargs["max_iterations"] == 5
        assert call_kwargs["quota_threshold"] == 80.0
        assert call_kwargs["quota_buffer_seconds"] == 600
        assert call_kwargs["prompt"] == "/custom"
        assert call_kwargs["gestate_max_rounds"] == 3
        assert call_kwargs["gestate_run_rounds"] == 2
        assert call_kwargs["gestate_run"] is False


def test_nudge_propagates_exit_code():
    with patch("fa.nudge.commands.run_nudge_loop", return_value=1):
        result = runner.invoke(app, ["nudge"])
        assert result.exit_code == 1
