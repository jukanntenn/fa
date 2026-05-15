from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    LOGS_DIR_NAME,
    build_tool_cmd,
    tool_extra_env,
)
from fa.core.logview import _LIVE_VIEWER_TOOLS, TaskViewer, ViewerController
from fa.core.quota import check_glm_quota_and_wait
from fa.core.subprocess import run_tool
from fa.core.tty import _read_main_session_key, cbreak_session
from fa.task.model import Task
from fa.task.prompt import build_task_prompt, infer_attempt, infer_memory_sequence
from fa.task.storage import all_tasks, auto_complete_parent_of, fa_dir, save_task


@dataclass(frozen=True)
class PromptRunContext:
    memory_count: int
    attempt: int
    feedback_count: int
    mode: str


def _prompt_run_context(task: Task, attempt_mode: bool) -> PromptRunContext:
    inferred_attempt = infer_attempt(task)
    return PromptRunContext(
        memory_count=infer_memory_sequence(task) - 1,
        attempt=inferred_attempt if attempt_mode else 1,
        feedback_count=inferred_attempt - 1 if attempt_mode else 0,
        mode="attempt" if attempt_mode else "fresh",
    )


def _prepare_round(
    task: Task,
    parent: Task | None,
    attempt_mode: bool,
    ctx: PromptRunContext,
    log_dir: Path,
    round_index: int,
    rounds: int,
    tool: str,
    logger: logging.Logger,
) -> tuple[str, Path]:
    prompt = build_task_prompt(task, parent, is_attempt_run=attempt_mode)
    _save_prompt(log_dir, round_index, ctx.attempt, attempt_mode, prompt)
    logger.debug(
        "Prompt rendered | mode=%s | attempt=%d | memory_files=%d | feedback_files=%d | chars=%d",
        ctx.mode,
        ctx.attempt,
        ctx.memory_count,
        ctx.feedback_count,
        len(prompt),
    )
    logger.info(
        "Task [%d] round %d/%d started | tool=%s",
        task.id,
        round_index,
        rounds,
        tool,
    )
    log_path = log_dir / f"round-{round_index}-{tool}.log"
    return prompt, log_path


def _should_run_round(
    task_id: int,
    round_index: int,
    rounds: int,
    glm_plan: bool,
    logger: logging.Logger,
) -> bool:
    if not glm_plan:
        return True
    if check_glm_quota_and_wait(logger):
        return True
    logger.error(
        "Task [%d] round %d/%d skipped - GLM quota check failed",
        task_id,
        round_index,
        rounds,
    )
    return False


def _run_task_interactive(
    task: Task,
    parent: Task | None,
    tool: str,
    rounds: int,
    logger: logging.Logger,
    extra_env: dict[str, str] | None,
    attempt_mode: bool,
    glm_plan: bool,
    log_dir: Path,
    open_viewer: bool = False,
) -> bool:
    viewer = TaskViewer(slug=task.slug, total_rounds=rounds, tool=tool)
    viewer_controller = ViewerController(viewer)
    failed = False

    def _execute_rounds() -> None:
        nonlocal failed
        ctx = _prompt_run_context(task, attempt_mode)
        for round_index in range(1, rounds + 1):
            if not _should_run_round(task.id, round_index, rounds, glm_plan, logger):
                failed = True
                viewer.mark_failed()
                return
            prompt, log_path = _prepare_round(
                task,
                parent,
                attempt_mode,
                ctx,
                log_dir,
                round_index,
                rounds,
                tool,
                logger,
            )
            viewer_log_path = log_path.with_name(f"{log_path.stem}-viewer.log")
            viewer.start_round(round_index, log_path, viewer_log_path)
            cmd = build_tool_cmd(tool, prompt)
            env = {**os.environ, **extra_env} if extra_env else None
            log_path.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            try:
                with log_path.open("w", encoding="utf-8") as file:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        env=env,
                    )
                    proc.wait()
                    code = int(proc.returncode)
            except OSError:
                code = 1
            elapsed = time.monotonic() - t0
            viewer.end_round(elapsed)
            logger.info(
                "Task [%d] round %d/%d completed in %ds | exit_code=%d",
                task.id,
                round_index,
                rounds,
                int(elapsed),
                code,
            )
            if code != 0:
                failed = True
                viewer.mark_failed()
                return
        viewer.mark_done()

    worker = threading.Thread(target=_execute_rounds, daemon=True)
    worker.start()
    if not sys.stdin.isatty():
        worker.join()
    else:
        logger.info("Agent running. Press Ctrl+L to open the log viewer.")
        if open_viewer:
            viewer_controller.open()
        with cbreak_session():
            while worker.is_alive():
                if viewer_controller.is_open():
                    time.sleep(0.2)
                    continue
                key = _read_main_session_key()
                if key == "\x0c":
                    viewer_controller.open()
    worker.join()
    viewer_controller.wait_closed()
    viewer._drain_current_log()
    return failed


def _run_task_batch(
    task: Task,
    parent: Task | None,
    tool: str,
    rounds: int,
    logger: logging.Logger,
    extra_env: dict[str, str] | None,
    attempt_mode: bool,
    glm_plan: bool,
    log_dir: Path,
) -> bool:
    ctx = _prompt_run_context(task, attempt_mode)
    for round_index in range(1, rounds + 1):
        if not _should_run_round(task.id, round_index, rounds, glm_plan, logger):
            return True
        prompt, log_path = _prepare_round(
            task, parent, attempt_mode, ctx, log_dir, round_index, rounds, tool, logger
        )
        t0 = time.monotonic()
        code = run_tool(tool, prompt, log_path, logger, extra_env=extra_env)
        elapsed = int(time.monotonic() - t0)
        logger.info(
            "Task [%d] round %d/%d completed in %ds | exit_code=%d",
            task.id,
            round_index,
            rounds,
            elapsed,
            code,
        )
        if code != 0:
            return True
    return False


def _task_log_dir(task: Task) -> Path:
    logs_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME
    relative = task.path.relative_to(fa_dir() / "tasks")
    path = logs_dir / relative
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_prompt(
    log_dir: Path,
    round_index: int,
    attempt: int,
    is_attempt_run: bool,
    prompt: str,
) -> Path:
    if is_attempt_run and attempt > 1:
        name = f"round-{round_index}-attempt-{attempt}-prompt.md"
    else:
        name = f"round-{round_index}-prompt.md"
    path = log_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")
    return path


def build_execution_plan(
    tasks: dict[int, Task], selected_pending_ids: list[int]
) -> list[int]:
    selected_set = set(selected_pending_ids)
    children: dict[int, list[int]] = {}
    for task in tasks.values():
        if task.parent_id is None:
            continue
        if task.id in selected_set:
            children.setdefault(task.parent_id, []).append(task.id)
    for child_ids in children.values():
        child_ids.sort()

    output: list[int] = []
    appended: set[int] = set()
    seen_parents: set[int] = set()

    for task_id in selected_pending_ids:
        task = tasks[task_id]
        if task.parent_id is not None:
            parent_id = task.parent_id
            if parent_id in seen_parents:
                if task_id not in appended:
                    output.append(task_id)
                    appended.add(task_id)
                continue
            for child_id in children.get(parent_id, []):
                if child_id not in appended:
                    output.append(child_id)
                    appended.add(child_id)
            seen_parents.add(parent_id)
        else:
            if task_id not in appended:
                output.append(task_id)
                appended.add(task_id)
    return output


def run_tasks(
    logger: logging.Logger,
    ids: list[int],
    force: bool,
    tool: str,
    rounds: int,
    glm_plan: bool,
    attempt_mode: bool,
    *,
    open_viewer: bool = False,
) -> int:
    tasks = all_tasks()

    # Reset status for force/attempt mode tasks
    if force:
        for task_id in ids:
            task = tasks.get(task_id)
            if task and task.status not in {"approved", "failed"}:
                task.status = "approved"
                task.completed_at = None
                save_task(task)

    extra_env = tool_extra_env(tool)

    plan = ids
    logger.info("Execution plan: %d tasks %s", len(plan), plan)
    has_failure = False
    open_viewer_for_next_live_task = open_viewer
    for task_id in plan:
        snapshot = all_tasks()
        task = snapshot.get(task_id)
        if task is None:
            logger.error("Task [%d] not found", task_id)
            has_failure = True
            continue
        parent = snapshot.get(task.parent_id) if task.parent_id else None
        try:
            build_task_prompt(task, parent, is_attempt_run=attempt_mode)
        except FileNotFoundError:
            logger.error(
                'Task [%d] "%s" skipped - template not found', task.id, task.slug
            )
            has_failure = True
            continue
        task.transition_to("running")
        save_task(task)
        logger.info('Task [%d] "%s" started', task.id, task.slug)
        failed = False
        log_dir = _task_log_dir(task)
        if tool in _LIVE_VIEWER_TOOLS:
            failed = _run_task_interactive(
                task=task,
                parent=parent,
                tool=tool,
                rounds=rounds,
                logger=logger,
                extra_env=extra_env,
                attempt_mode=attempt_mode,
                glm_plan=glm_plan,
                log_dir=log_dir,
                open_viewer=open_viewer_for_next_live_task,
            )
            open_viewer_for_next_live_task = False
        else:
            failed = _run_task_batch(
                task=task,
                parent=parent,
                tool=tool,
                rounds=rounds,
                logger=logger,
                extra_env=extra_env,
                attempt_mode=attempt_mode,
                glm_plan=glm_plan,
                log_dir=log_dir,
            )
        if failed:
            has_failure = True
            task.transition_to("failed")
            task.completed_at = None
            save_task(task)
            logger.info('Task [%d] "%s" failed', task.id, task.slug)
            continue
        task.complete()
        save_task(task)
        logger.info('Task [%d] "%s" completed', task.id, task.slug)
        auto_complete_parent_of(all_tasks(), task, logger=logger)
    return 1 if has_failure else 0
