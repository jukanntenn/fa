from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from fa.task.model import InvalidTransition, Task
from fa.task.runner import build_execution_plan, run_tasks
from fa.task.storage import (
    all_tasks,
    archive_dir,
    auto_complete_all_eligible_parents,
    create_task,
    find_task,
    parse_id_range,
    relative_path,
    resolve_to_leaves,
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
        try:
            task.complete()
        except InvalidTransition:
            has_error = True
            typer.echo(
                f"Error: task {task_id} is '{task.status}', "
                "can only complete tasks that are approved/running/failed",
                err=True,
            )
            continue
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


def _dedupe_archive_roots(tasks: list[Task]) -> list[Task]:
    selected_paths = {task.path.resolve() for task in tasks}
    kept_paths: set[Path] = set()
    kept_tasks: list[Task] = []
    for task in sorted(tasks, key=lambda item: (len(item.path.parts), item.id)):
        task_path = task.path.resolve()
        if any(
            ancestor in selected_paths and ancestor in kept_paths
            for ancestor in task_path.parents
        ):
            continue
        kept_paths.add(task_path)
        kept_tasks.append(task)
    return sorted(kept_tasks, key=lambda item: item.id)


@task_app.command("archive")
def archive(id_range: Annotated[str | None, typer.Argument()] = None) -> None:
    now = datetime.now()
    month_dir = archive_dir() / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    has_error = False

    if id_range is None:
        completed_tasks = sorted(
            [task for task in all_tasks().values() if task.status == "completed"],
            key=lambda task: task.id,
        )
        if not completed_tasks:
            typer.echo("No completed tasks to archive")
            return
        for task in _dedupe_archive_roots(completed_tasks):
            shutil.move(str(task.path), str(month_dir / task.path.name))
        return

    tasks_to_archive: list[Task] = []
    for task_id in parse_id_range(id_range):
        task = find_task(task_id)
        if task is None:
            has_error = True
            typer.echo(f"Error: task {task_id} not found", err=True)
            continue
        if task.status != "completed":
            has_error = True
            typer.echo(f"Error: task {task_id} is not completed", err=True)
            continue
        tasks_to_archive.append(task)
    for task in _dedupe_archive_roots(tasks_to_archive):
        shutil.move(str(task.path), str(month_dir / task.path.name))
    if has_error:
        raise typer.Exit(code=1)


@task_app.command("run")
def run(
    ids: str | None = typer.Option(None, "--ids"),
    force: bool = typer.Option(False, "--force"),
    tool: str = typer.Option("codex", "--tool"),
    rounds: int = typer.Option(3, "--rounds"),
    policies: str | None = typer.Option(None, "--policies"),
    glm_plan: bool = typer.Option(False, "--glm-plan"),
    attempt: bool = typer.Option(False, "--attempt"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    from fa.cli import app_state

    logger = app_state.logger

    # Validate flags
    if force and ids is None:
        typer.echo("Error: --force requires --ids to be specified", err=True)
        raise typer.Exit(code=1)

    # Get all tasks
    tasks = all_tasks()

    # Auto-complete parents whose children are all done (EC1)
    auto_complete_all_eligible_parents(tasks)
    tasks = all_tasks()

    # Build candidate list
    if ids is not None:
        raw_ids = parse_id_range(ids)
        missing = [tid for tid in raw_ids if tid not in tasks]
        if missing:
            typer.echo(
                "Error: task(s) not found: " + ",".join(str(m) for m in missing),
                err=True,
            )
            raise typer.Exit(code=1)
        candidates = resolve_to_leaves(raw_ids, tasks)
        if force:
            # EC7: --force skips completed children, doesn't re-run them
            candidates = [cid for cid in candidates if tasks[cid].status != "completed"]
        elif attempt:
            # EC5: --attempt --ids filters by feedback files
            candidates = [
                cid
                for cid in candidates
                if tasks[cid].status in {"approved", "failed"}
                and list(tasks[cid].path.glob("feedback-*.md"))
            ]
        else:
            not_runnable = [
                cid
                for cid in candidates
                if tasks[cid].status not in {"approved", "failed"}
            ]
            if not_runnable:
                typer.echo(
                    "Error: task(s) "
                    + ",".join(str(n) for n in not_runnable)
                    + " are not approved/failed. Use --force to override.",
                    err=True,
                )
                raise typer.Exit(code=1)
    elif attempt:
        leaf_ids = resolve_to_leaves(sorted(tasks.keys()), tasks)
        candidates = [
            tid
            for tid in leaf_ids
            if tid in tasks
            and tasks[tid].status in {"approved", "failed"}
            and list(tasks[tid].path.glob("feedback-*.md"))
        ]
    else:
        leaf_ids = resolve_to_leaves(sorted(tasks.keys()), tasks)
        candidates = [
            tid for tid in leaf_ids if tasks[tid].status in {"approved", "failed"}
        ]

    if not candidates:
        logger.info("No tasks to run.")
        return

    plan = build_execution_plan(tasks, candidates)

    # Show execution plan and confirm
    if not yes:
        typer.echo(f"\nTasks to execute ({len(plan)} total, {rounds} round(s)):\n")
        for task_id in plan:
            task = tasks.get(task_id)
            if not task:
                continue
            parent_info = ""
            if task.parent_id:
                parent_task = tasks.get(task.parent_id)
                if parent_task:
                    parent_info = f" (parent: [{parent_task.id}] {parent_task.slug})"
            typer.echo(f"  [{task_id}] {task.slug}{parent_info}")
        typer.echo("")
        if not typer.confirm("Proceed?", default=True):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    exit_code = run_tasks(
        logger=logger,
        ids=plan,
        force=force or attempt,
        tool=tool,
        rounds=rounds,
        glm_plan=glm_plan,
        attempt_mode=attempt,
    )
    if policies:
        from fa.policy.runner import run_policies_by_ids

        policy_ids = [item.strip() for item in policies.split(",") if item.strip()]
        policy_result = run_policies_by_ids(
            logger, policy_ids, tool=tool, rounds=rounds
        )
        if policy_result != 0:
            exit_code = 1
    if exit_code != 0:
        raise typer.Exit(code=exit_code)
