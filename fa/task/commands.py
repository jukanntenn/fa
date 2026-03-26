from __future__ import annotations

import shutil
from datetime import datetime

import typer

from fa.task.runner import build_execution_plan, run_tasks
from fa.task.storage import (
    all_tasks,
    archive_dir,
    create_task,
    find_task,
    parse_id_range,
    relative_path,
    save_task,
)

task_app = typer.Typer(help="Task commands")


@task_app.command("create")
def create(slug: str, parent: int | None = typer.Option(None, "--parent")) -> None:
    try:
        task = create_task(slug, parent)
    except ValueError as exc:
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created task {task.id}: {relative_path(task.path)}")


@task_app.command("list")
def list_tasks(status: str | None = typer.Option(None, "--status")) -> None:
    tasks = all_tasks()
    if status is not None:
        items = [task for task in tasks.values() if task.status == status]
    else:
        items = list(tasks.values())
    for task in sorted(items, key=lambda item: item.id):
        typer.echo(f"[{task.id}] {task.slug} ({task.status})")


@task_app.command("info")
def info(task_id: int) -> None:
    task = find_task(task_id)
    if task is None:
        typer.echo(f"Error: task {task_id} not found", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"ID: {task.id}")
    typer.echo(f"Slug: {task.slug}")
    typer.echo(f"Parent ID: {task.parent_id}")
    typer.echo(f"Status: {task.status}")
    typer.echo(f"Depends On: {task.depends_on}")
    typer.echo(f"Related To: {task.related_to}")
    typer.echo(f"Created At: {task.created_at}")
    typer.echo(f"Completed At: {task.completed_at}")
    typer.echo(f"Path: {relative_path(task.path)}")


@task_app.command("done")
def done(id_range: str) -> None:
    has_error = False
    for task_id in parse_id_range(id_range):
        task = find_task(task_id)
        if task is None:
            has_error = True
            typer.echo(f"Error: task {task_id} not found", err=True)
            continue
        task.status = "completed"
        task.completed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        save_task(task)
    if has_error:
        raise typer.Exit(code=1)


@task_app.command("rm")
def rm(id_range: str, force: bool = typer.Option(False, "-f")) -> None:
    ids = parse_id_range(id_range)
    if not force:
        confirm = typer.confirm("Confirm delete?", default=False)
        if not confirm:
            raise typer.Exit(code=0)
    has_error = False
    for task_id in ids:
        task = find_task(task_id)
        if task is None:
            has_error = True
            typer.echo(f"Error: task {task_id} not found", err=True)
            continue
        shutil.rmtree(task.path)
    if has_error:
        raise typer.Exit(code=1)


@task_app.command("archive")
def archive(id_range: str) -> None:
    ids = parse_id_range(id_range)
    now = datetime.now()
    month_dir = archive_dir() / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    has_error = False
    for task_id in ids:
        task = find_task(task_id)
        if task is None:
            has_error = True
            typer.echo(f"Error: task {task_id} not found", err=True)
            continue
        if task.status != "completed":
            has_error = True
            typer.echo(f"Error: task {task_id} is not completed", err=True)
            continue
        shutil.move(str(task.path), str(month_dir / task.path.name))
    if has_error:
        raise typer.Exit(code=1)


@task_app.command("run")
def run(
    start: int | None = typer.Option(None, "--start"),
    end: int | None = typer.Option(None, "--end"),
    tool: str = typer.Option("iflow", "--tool"),
    rounds: int = typer.Option(3, "--rounds"),
    policies: str | None = typer.Option(None, "--policies"),
    glm_plan: bool = typer.Option(False, "--glm-plan"),
    attempt: bool = typer.Option(False, "--attempt"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    from fa.cli import app_state

    logger = app_state.logger

    # Get pending tasks and build execution plan
    tasks = all_tasks()
    pending = sorted(task.id for task in tasks.values() if task.status == "pending")
    if start is not None:
        pending = [task_id for task_id in pending if task_id >= start]
    if end is not None:
        pending = [task_id for task_id in pending if task_id <= end]

    if not pending:
        logger.info("No pending tasks to run.")
        return

    plan = build_execution_plan(tasks, pending)

    # Show execution plan and confirm
    if not yes:
        typer.echo(f"\nTasks to execute ({len(plan)} total, {rounds} round(s)):\n")
        for task_id in plan:
            task = tasks.get(task_id)
            if task:
                parent_info = f" (parent: {task.parent_id})" if task.parent_id else ""
                typer.echo(f"  [{task_id}] {task.slug}{parent_info}")
        typer.echo("")
        if not typer.confirm("Proceed?", default=True):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    exit_code = run_tasks(
        logger=logger,
        start=start,
        end=end,
        tool=tool,
        rounds=rounds,
        glm_plan=glm_plan,
        attempt_mode=attempt,
    )
    if policies:
        from fa.policy.runner import run_policies_by_ids

        ids = [item.strip() for item in policies.split(",") if item.strip()]
        policy_result = run_policies_by_ids(logger, ids, tool=tool, rounds=rounds)
        if policy_result != 0:
            exit_code = 1
    if exit_code != 0:
        raise typer.Exit(code=exit_code)
