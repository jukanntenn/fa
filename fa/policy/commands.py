from __future__ import annotations

import typer

from fa.policy.runner import run_policies_by_ids
from fa.policy.storage import list_policy_files
from fa.profile.storage import resolve_profile_phase

policy_app = typer.Typer(help="Policy commands")


@policy_app.command("list")
def list_policies() -> None:
    for path in list_policy_files():
        typer.echo(path.stem)


@policy_app.command("run")
def run(
    policy_ids: list[str],
    tool: str = "codex",
    rounds: int = 3,
    profile: str | None = None,
) -> None:
    from fa.cli import app_state

    if not policy_ids:
        raise typer.Exit(code=0)

    run_model = None
    run_extra_args = None
    run_extra_env = None
    if isinstance(profile, str):
        resolved = resolve_profile_phase(profile, "policy-run", fallback_tool=tool)
        tool = resolved.tool or tool
        run_model = resolved.model
        run_extra_args = resolved.extra_args
        run_extra_env = resolved.extra_env

    code = run_policies_by_ids(
        app_state.logger,
        policy_ids,
        tool=tool,
        rounds=rounds,
        model=run_model,
        extra_args=run_extra_args,
        extra_env=run_extra_env,
    )
    if code != 0:
        raise typer.Exit(code=code)


@policy_app.command("run-all")
def run_all(tool: str = "codex", rounds: int = 3, profile: str | None = None) -> None:
    from fa.cli import app_state

    ids = [path.stem for path in list_policy_files()]

    run_model = None
    run_extra_args = None
    run_extra_env = None
    if isinstance(profile, str):
        resolved = resolve_profile_phase(profile, "policy-run", fallback_tool=tool)
        tool = resolved.tool or tool
        run_model = resolved.model
        run_extra_args = resolved.extra_args
        run_extra_env = resolved.extra_env

    code = run_policies_by_ids(
        app_state.logger,
        ids,
        tool=tool,
        rounds=rounds,
        model=run_model,
        extra_args=run_extra_args,
        extra_env=run_extra_env,
    )
    if code != 0:
        raise typer.Exit(code=code)
