from __future__ import annotations

import typer

from fa.nudge.runner import run_nudge_loop
from fa.profile.storage import resolve_profile_phase


def nudge(
    tool: str = typer.Option("claude", "--tool", help="Tool for nudging phase"),
    gestate_tool: str = typer.Option(
        "claude", "--gestate-tool", help="Tool for gestate execution phase"
    ),
    max_iterations: int = typer.Option(
        100, "--max-iterations", help="Max iterations before circuit breaker"
    ),
    quota_threshold: float = typer.Option(
        90.0, "--quota-threshold", help="GLM quota %% threshold"
    ),
    quota_buffer: int = typer.Option(
        1800, "--quota-buffer", help="Buffer seconds after reset"
    ),
    prompt: str = typer.Option("/nudging", "--prompt", help="Custom prompt prefix"),
    gestate_max_rounds: int = typer.Option(10, "--gestate-max-rounds"),
    gestate_run_rounds: int = typer.Option(1, "--gestate-run-rounds"),
    gestate_run: bool = typer.Option(True, "--gestate-run/--no-gestate-run"),
    profile: str | None = typer.Option(
        None, "--profile", help="Profile name for tool configuration"
    ),
) -> None:
    from fa.cli import app_state

    logger = app_state.logger

    nudge_tool = tool
    nudge_model = None
    nudge_extra_args = None
    nudge_extra_env = None
    if isinstance(profile, str):
        resolved = resolve_profile_phase(profile, "nudge", fallback_tool=tool)
        nudge_tool = resolved.tool or tool
        nudge_model = resolved.model
        nudge_extra_args = resolved.extra_args
        nudge_extra_env = resolved.extra_env

    typer.echo(f"Starting nudge loop (max {max_iterations} iterations)")
    code = run_nudge_loop(
        logger=logger,
        tool=nudge_tool,
        gestate_tool=gestate_tool,
        prompt=prompt,
        max_iterations=max_iterations,
        quota_threshold=quota_threshold,
        quota_buffer_seconds=quota_buffer,
        gestate_max_rounds=gestate_max_rounds,
        gestate_run_rounds=gestate_run_rounds,
        gestate_run=gestate_run,
        model=nudge_model,
        extra_args=nudge_extra_args,
        extra_env=nudge_extra_env,
        profile=profile,
    )
    raise typer.Exit(code=code)
