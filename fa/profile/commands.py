from __future__ import annotations

import typer

from fa.profile.storage import list_profiles, load_profile

profile_app = typer.Typer(help="Profile commands")


@profile_app.command("list")
def list_cmd() -> None:
    profiles = list_profiles()
    if not profiles:
        typer.echo("No profiles found")
        return
    for name in profiles:
        typer.echo(name)


@profile_app.command("show")
def show(name: str) -> None:
    try:
        profile = load_profile(name)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Error: invalid profile: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Profile: {profile.name}")
    for phase_name, cfg in profile.phases.items():
        typer.echo(f"\n  [{phase_name}]")
        if cfg.tool:
            typer.echo(f"    tool = {cfg.tool}")
        if cfg.model:
            typer.echo(f"    model = {cfg.model}")
        if cfg.agent:
            typer.echo(f"    agent = {cfg.agent}")
        if cfg.extra_args:
            typer.echo(f"    extra_args = {cfg.extra_args}")
        if cfg.env:
            typer.echo(f"    env = {cfg.env}")
