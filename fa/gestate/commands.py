from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import typer

from fa.core.config import AGENT_LOGS_DIR_NAME, LOGS_DIR_NAME
from fa.core.logview import LIVE_VIEWER_TOOLS, TaskViewer, ViewerController
from fa.gestate.artifacts import (
    _capture_artifact_snapshot,
    _format_artifact_diff,
    _print_round_artifact_diff,
)
from fa.gestate.prompting import _build_tool_cmd_for_prompt, _is_task_id, _read_stdin
from fa.gestate.review import _build_review_prompt
from fa.gestate.runner import _run_tool_with_optional_viewer
from fa.gestate.tasks import (
    _approve_task_descendants,
    _extract_text_from_create_log,
    _find_created_task,
    _find_new_parent_task,
    _parse_task_reference,
    _resolve_execution_candidates,
    _resolve_task_descendants,
    _validate_task,
)
from fa.profile.storage import resolve_profile_phase
from fa.task.model import Task
from fa.task.runner import run_tasks
from fa.task.storage import all_tasks, fa_dir, find_task, relative_path, save_task

__all__ = [
    "_approve_task_descendants",
    "_build_review_prompt",
    "_build_tool_cmd_for_prompt",
    "_capture_artifact_snapshot",
    "_extract_text_from_create_log",
    "_find_created_task",
    "_find_new_parent_task",
    "_format_artifact_diff",
    "_is_task_id",
    "_parse_task_reference",
    "_print_round_artifact_diff",
    "_read_stdin",
    "_resolve_execution_candidates",
    "_resolve_task_descendants",
    "_run_runnable_task_tree",
    "_run_tool_with_optional_viewer",
    "_validate_task",
    "gestate",
]


def _run_runnable_task_tree(
    task: Task,
    logger: logging.Logger,
    tool: str,
    rounds: int,
    *,
    open_viewer: bool = False,
    model: str | None = None,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    candidates = _resolve_execution_candidates(task)
    if not candidates:
        logger.info("No runnable tasks to run after gestate.")
        typer.echo("No runnable tasks to run after gestate.")
        return 0
    from fa.task.runner import build_execution_plan

    plan = build_execution_plan(all_tasks(), candidates)
    typer.echo(f"Running task(s) after gestate: {','.join(str(i) for i in plan)}")
    return run_tasks(
        logger=logger,
        ids=plan,
        force=False,
        tool=tool,
        rounds=rounds,
        attempt_mode=False,
        open_viewer=open_viewer,
        model=model,
        extra_args=extra_args,
        extra_env=extra_env,
    )


def _build_log_paths(log_dir: Path, prefix: str) -> tuple[Path, Path]:
    return log_dir / f"{prefix}.log", log_dir / f"{prefix}-prompt.md"


@dataclass(frozen=True)
class _ResolvedProfile:
    tool: str
    create_model: str | None
    create_extra_args: list[str] | None
    create_extra_env: dict[str, str] | None
    run_tool: str
    run_model: str | None
    run_extra_args: list[str] | None
    run_extra_env: dict[str, str] | None


def _resolve_gestate_profile(
    profile: str | None, tool: str, run_tool: str
) -> _ResolvedProfile:
    if not isinstance(profile, str):
        return _ResolvedProfile(
            tool=tool,
            create_model=None,
            create_extra_args=None,
            create_extra_env=None,
            run_tool=run_tool,
            run_model=None,
            run_extra_args=None,
            run_extra_env=None,
        )
    create_resolved = resolve_profile_phase(
        profile, "gestate-create", fallback_tool=tool
    )
    tool = create_resolved.tool or tool
    review_resolved = resolve_profile_phase(
        profile, "gestate-review", fallback_tool=tool
    )
    tool = review_resolved.tool or tool
    run_resolved = resolve_profile_phase(profile, "gestate-run", fallback_tool=run_tool)
    return _ResolvedProfile(
        tool=tool,
        create_model=create_resolved.model,
        create_extra_args=create_resolved.extra_args,
        create_extra_env=create_resolved.extra_env,
        run_tool=run_resolved.tool or run_tool,
        run_model=run_resolved.model,
        run_extra_args=run_resolved.extra_args,
        run_extra_env=run_resolved.extra_env,
    )


def gestate(
    arg: str | None = typer.Argument(None, help="Intent brief or task ID"),
    tool: str = typer.Option("claude", "--tool", help="AI tool to use"),
    max_rounds: int = typer.Option(10, "--max-rounds", help="Max convergence rounds"),
    run: bool = typer.Option(
        True, "--run/--no-run", help="Run runnable task(s) after gestation"
    ),
    run_tool: str = typer.Option(
        "claude", "--run-tool", help="AI tool to use for task execution"
    ),
    run_rounds: int = typer.Option(
        3, "--run-rounds", help="Execution rounds for each task"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="Profile name for tool configuration"
    ),
) -> None:
    from fa.cli import app_state

    logger = cast(logging.Logger, app_state.logger)

    resolved = _resolve_gestate_profile(profile, tool, run_tool)
    tool = resolved.tool
    run_tool = resolved.run_tool
    create_model = resolved.create_model
    create_extra_args = resolved.create_extra_args
    create_extra_env = resolved.create_extra_env
    run_model = resolved.run_model
    run_extra_args = resolved.run_extra_args
    run_extra_env = resolved.run_extra_env

    if arg is not None:
        input_text = arg.strip()
    else:
        input_text = _read_stdin()

    if not input_text:
        typer.echo("Error: empty input", err=True)
        raise typer.Exit(code=1)

    create_phase_rounds = 0 if _is_task_id(input_text) else 1
    viewer = (
        TaskViewer(
            slug="gestate",
            total_rounds=max_rounds + create_phase_rounds,
            tool=tool,
        )
        if tool in LIVE_VIEWER_TOOLS
        else None
    )
    viewer_controller = ViewerController(viewer) if viewer is not None else None
    had_tool_failure = False
    task: Task | None = None

    if create_phase_rounds == 0:
        task = find_task(int(input_text.strip()))
        if task is None:
            typer.echo(f"Error: task {input_text} not found", err=True)
            raise typer.Exit(code=1)
    else:
        preexisting_ids = frozenset(all_tasks().keys())
        prompt = f"/gestating {input_text}"
        gestate_log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / "gestate"
        gestate_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path, prompt_path = _build_log_paths(
            gestate_log_dir, f"gestate-create-{timestamp}"
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        logger.info("Creating task from intent brief using tool=%s", tool)
        result_code = _run_tool_with_optional_viewer(
            tool=tool,
            prompt=prompt,
            log_path=log_path,
            logger=logger,
            viewer=viewer,
            round_index=1,
            viewer_controller=viewer_controller,
            prompt_path=prompt_path,
            model=create_model,
            extra_args=create_extra_args,
            extra_env=create_extra_env,
        )
        if result_code is None:
            typer.echo(f"Error: tool '{tool}' execution failed", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        if result_code != 0:
            typer.echo(f"Error: tool '{tool}' exited with code {result_code}", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        task = _find_created_task(preexisting_ids, log_path, tool)
        if task is None:
            typer.echo("Error: no new task created by gestating tool", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        typer.echo(f"Created task {task.id}: {relative_path(task.path)}")

    assert task is not None
    issues = _validate_task(task)
    critical = False
    for issue in issues:
        typer.echo(f"Warning: {issue}", err=True)
        if "status" in issue or "missing" in issue:
            critical = True
    if critical:
        if viewer is not None:
            viewer.mark_failed()
        raise typer.Exit(code=1)

    log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / f"gestate-{task.id}"
    log_dir.mkdir(parents=True, exist_ok=True)
    review_round_offset = create_phase_rounds

    for round_num in range(1, max_rounds + 1):
        before_snapshot = _capture_artifact_snapshot(task.path)
        prompt = _build_review_prompt(task, round_num, max_rounds)
        _, prompt_path = _build_log_paths(log_dir, f"round-{round_num}")
        prompt_path.write_text(prompt, encoding="utf-8")
        log_path = log_dir / f"round-{round_num}-{tool}.log"
        logger.info(
            "Task [%d] gestate round %d/%d started | tool=%s",
            task.id,
            round_num,
            max_rounds,
            tool,
        )
        result_code = _run_tool_with_optional_viewer(
            tool=tool,
            prompt=prompt,
            log_path=log_path,
            logger=logger,
            viewer=viewer,
            round_index=review_round_offset + round_num,
            viewer_controller=viewer_controller,
            prompt_path=prompt_path,
        )
        if result_code is None:
            had_tool_failure = True
            logger.warning("Tool '%s' execution failed in round %d", tool, round_num)
            after_snapshot = _capture_artifact_snapshot(task.path)
            _print_round_artifact_diff(round_num, before_snapshot, after_snapshot)
            if before_snapshot == after_snapshot:
                typer.echo(f"Converged after {round_num} round(s)")
                break
            continue
        if result_code != 0:
            had_tool_failure = True
            logger.warning(
                "Tool '%s' exited with code %d in round %d",
                tool,
                result_code,
                round_num,
            )
        after_snapshot = _capture_artifact_snapshot(task.path)
        _print_round_artifact_diff(round_num, before_snapshot, after_snapshot)
        if before_snapshot == after_snapshot:
            typer.echo(f"Converged after {round_num} round(s)")
            break
    else:
        typer.echo(f"Max rounds ({max_rounds}) reached")

    will_try_auto_run = run and not had_tool_failure
    if viewer is not None:
        if had_tool_failure:
            viewer.mark_failed()
        elif not will_try_auto_run:
            viewer.mark_done()

    task.status = "approved"
    save_task(task)

    approved_count, descendant_count, approval_failed = _approve_task_descendants(task)
    if descendant_count:
        typer.echo(f"{approved_count}/{descendant_count} subtask(s) approved")

    if approval_failed:
        if viewer is not None:
            viewer.mark_failed()
        raise typer.Exit(code=1)

    typer.echo(f"Task {task.id} approved")

    if run:
        if had_tool_failure:
            typer.echo(
                "Warning: gestate review had tool failures; skipping automatic task execution",
                err=True,
            )
        else:
            handoff_open_viewer = bool(
                viewer_controller is not None and viewer_controller.is_open()
            )
            should_close_viewer = handoff_open_viewer
            handoff_open_viewer = handoff_open_viewer and run_tool in LIVE_VIEWER_TOOLS
            if should_close_viewer:
                assert viewer_controller is not None
                viewer_controller.close()
                viewer_controller.wait_closed()
            exit_code = _run_runnable_task_tree(
                task,
                logger,
                run_tool,
                run_rounds,
                open_viewer=handoff_open_viewer,
                model=run_model,
                extra_args=run_extra_args,
                extra_env=run_extra_env,
            )
            if exit_code != 0:
                raise typer.Exit(code=exit_code)
