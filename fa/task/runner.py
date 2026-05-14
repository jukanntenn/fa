from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    LOGS_DIR_NAME,
    TOOL_COMMANDS,
    _load_dotenv,
)
from fa.core.logview import _LIVE_VIEWER_TOOLS, TaskViewer, ViewerController
from fa.core.quota import check_glm_quota
from fa.core.tty import _main_session_cbreak, _read_main_session_key
from fa.task.model import Task
from fa.task.prompt import build_task_prompt, infer_attempt, infer_memory_sequence
from fa.task.storage import all_tasks, fa_dir, find_children, save_task


def _auto_complete_parent(task: Task, logger: logging.Logger) -> None:
    """Auto-complete parent task if all children are done."""
    if not task.parent_id:
        return
    all_t = all_tasks()
    siblings = find_children(task.parent_id)
    if all(s.status == "completed" for s in siblings):
        parent_task = all_t.get(task.parent_id)
        if parent_task and parent_task.status != "completed":
            parent_task.complete()
            save_task(parent_task)
            logger.info(
                "Parent task [%d] auto-completed (all children done)", parent_task.id
            )


def _tool_cmd(tool: str, prompt: str) -> list[str]:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    template = TOOL_COMMANDS[tool]
    return [part.format(prompt=prompt) for part in template]


def _run_tool(
    tool: str,
    prompt: str,
    log_file: Path,
    logger: logging.Logger,
    extra_env: dict[str, str] | None = None,
) -> int:
    cmd = _tool_cmd(tool, prompt)
    logger.debug("Executing agent tool command: %s", cmd)
    env = {**os.environ, **extra_env} if extra_env else None
    try:
        with log_file.open("w", encoding="utf-8") as file:
            completed = subprocess.run(
                cmd,
                stdout=file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                env=env,
            )
    except OSError:
        return 1
    return int(completed.returncode)


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
        memory_count = infer_memory_sequence(task) - 1
        attempt = infer_attempt(task) if attempt_mode else 1
        feedback_count = infer_attempt(task) - 1 if attempt_mode else 0
        mode = "attempt" if attempt_mode else "fresh"
        for round_index in range(1, rounds + 1):
            if glm_plan and not check_glm_quota(logger):
                logger.error(
                    "Task [%d] round %d/%d skipped - GLM quota check failed",
                    task.id,
                    round_index,
                    rounds,
                )
                failed = True
                viewer.mark_failed()
                return
            prompt = build_task_prompt(task, parent, is_attempt_run=attempt_mode)
            _save_prompt(log_dir, round_index, attempt, attempt_mode, prompt)
            logger.debug(
                "Prompt rendered | mode=%s | attempt=%d | memory_files=%d | feedback_files=%d | chars=%d",
                mode,
                attempt,
                memory_count,
                feedback_count,
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
            viewer_log_path = log_path.with_name(f"{log_path.stem}-viewer.log")
            viewer.start_round(round_index, log_path, viewer_log_path)
            cmd = _tool_cmd(tool, prompt)
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
                    logger.info("Agent running. Press Ctrl+L to open the log viewer.")
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
        with _main_session_cbreak():
            while True:
                if not worker.is_alive():
                    break
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

    # Load .env from cwd for codex
    extra_env: dict[str, str] | None = None
    if tool == "codex":
        dotenv = _load_dotenv(Path.cwd() / ".env")
        if "CODEX_API_KEY" in dotenv:
            extra_env = {"CODEX_API_KEY": dotenv["CODEX_API_KEY"]}

    plan = ids
    logger.info("Execution plan: %d tasks %s", len(plan), plan)
    has_failure = False
    open_viewer_for_next_live_task = open_viewer
    for task_id in plan:
        task = all_tasks().get(task_id)
        if task is None:
            logger.error("Task [%d] not found", task_id)
            has_failure = True
            continue
        parent = all_tasks().get(task.parent_id) if task.parent_id else None
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
            if failed:
                has_failure = True
        else:
            memory_count = infer_memory_sequence(task) - 1
            attempt = infer_attempt(task) if attempt_mode else 1
            feedback_count = infer_attempt(task) - 1 if attempt_mode else 0
            mode = "attempt" if attempt_mode else "fresh"
            for round_index in range(1, rounds + 1):
                if glm_plan and not check_glm_quota(logger):
                    logger.error(
                        "Task [%d] round %d/%d skipped - GLM quota check failed",
                        task.id,
                        round_index,
                        rounds,
                    )
                    failed = True
                    break
                prompt = build_task_prompt(task, parent, is_attempt_run=attempt_mode)
                _save_prompt(log_dir, round_index, attempt, attempt_mode, prompt)
                logger.debug(
                    "Prompt rendered | mode=%s | attempt=%d | memory_files=%d | feedback_files=%d | chars=%d",
                    mode,
                    attempt,
                    memory_count,
                    feedback_count,
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
                t0 = time.monotonic()
                code = _run_tool(tool, prompt, log_path, logger, extra_env=extra_env)
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
                    failed = True
                    has_failure = True
                    break
        if failed:
            task.status = "failed"
            task.completed_at = None
            save_task(task)
            logger.info('Task [%d] "%s" failed', task.id, task.slug)
            continue
        task.complete()
        save_task(task)
        logger.info('Task [%d] "%s" completed', task.id, task.slug)
        _auto_complete_parent(task, logger)
    return 1 if has_failure else 0
