from __future__ import annotations

import typer

from fa.policy.runner import run_policies_by_ids
from fa.policy.storage import list_policy_files

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
    glm_plan: bool = False,
) -> None:
    from fa.cli import app_state

    if not policy_ids:
        raise typer.Exit(code=0)
    code = run_policies_by_ids(
        app_state.logger, policy_ids, tool=tool, rounds=rounds, glm_plan=glm_plan
    )
    if code != 0:
        raise typer.Exit(code=code)


@policy_app.command("run-all")
def run_all(tool: str = "codex", rounds: int = 3, glm_plan: bool = False) -> None:
    from fa.cli import app_state

    ids = [path.stem for path in list_policy_files()]
    code = run_policies_by_ids(
        app_state.logger, ids, tool=tool, rounds=rounds, glm_plan=glm_plan
    )
    if code != 0:
        raise typer.Exit(code=code)
