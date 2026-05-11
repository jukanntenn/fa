from __future__ import annotations

import logging
import os
import select
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fa.core.config import AGENT_LOGS_DIR_NAME, LOGS_DIR_NAME, TOOL_COMMANDS
from fa.core.logview import _STREAM_JSON_TOOLS
from fa.core.quota import check_glm_quota
from fa.task.model import Task
from fa.task.prompt import build_task_prompt, infer_attempt, infer_memory_sequence
from fa.task.storage import all_tasks, fa_dir, find_children, save_task


def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        env[key.strip()] = value.strip()
    return env


def _auto_complete_parent(task: Task, logger: logging.Logger) -> None:
    """Auto-complete parent task if all children are done."""
    if not task.parent_id:
        return
    all_t = all_tasks()
    siblings = find_children(task.parent_id)
    if all(s.status == "completed" for s in siblings):
        parent_task = all_t.get(task.parent_id)
        if parent_task and parent_task.status != "completed":
            parent_task.transition_to("completed")
            parent_task.completed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
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
    live_view: bool = False,
) -> int:
    cmd = _tool_cmd(tool, prompt)
    logger.debug("Executing agent tool command: %s", cmd)
    env = {**os.environ, **extra_env} if extra_env else None
    supports_live = live_view and tool in _STREAM_JSON_TOOLS
    if live_view and not supports_live:
        logger.info("Live log viewing not supported for tool '%s'", tool)
    try:
        if supports_live:
            return _run_tool_with_live(cmd, log_file, logger, env)
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


def _run_tool_with_live(
    cmd: list[str],
    log_file: Path,
    logger: logging.Logger,
    env: dict[str, str] | None,
) -> int:
    from fa.core.logview import tail_log

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as file:
        proc = subprocess.Popen(
            cmd,
            stdout=file,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

    live_requested = threading.Event()
    original_tty_settings = None

    def _watch_stdin() -> None:
        nonlocal original_tty_settings
        if not sys.stdin.isatty():
            return
        import tty as tty_module

        try:
            original_tty_settings = tty_module.tcgetattr(sys.stdin.fileno())
            tty_module.setcbreak(sys.stdin.fileno())
        except Exception:
            return
        while proc.poll() is None and not live_requested.is_set():
            try:
                readable, _, _ = select.select([sys.stdin], [], [], 0.2)
                if readable:
                    ch = sys.stdin.read(1)
                    if ch == "\x0c":  # Ctrl+L
                        live_requested.set()
                        break
            except Exception:
                break

    watcher = threading.Thread(target=_watch_stdin, daemon=True)
    watcher.start()

    hint_printed = False
    while proc.poll() is None:
        if not hint_printed:
            logger.info("Press Ctrl+L to view live logs, or wait for completion...")
            hint_printed = True
        if live_requested.wait(timeout=0.5):
            live_requested.clear()
            if original_tty_settings is not None:
                import tty as tty_module

                try:
                    tty_module.tcsetattr(
                        sys.stdin.fileno(),
                        tty_module.TCSADRAIN,
                        original_tty_settings,
                    )
                except Exception:
                    pass
            tail_log(log_file)
            live_requested.clear()
            try:
                if sys.stdin.isatty():
                    import tty as tty_module

                    tty_module.setcbreak(sys.stdin.fileno())
            except Exception:
                pass

    if original_tty_settings is not None:
        import tty as tty_module

        try:
            tty_module.tcsetattr(
                sys.stdin.fileno(), tty_module.TCSADRAIN, original_tty_settings
            )
        except Exception:
            pass

    watcher.join(timeout=1)
    return int(proc.returncode)


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


def _count_feedback_files(task: Task) -> int:
    return len(sorted(task.path.glob("feedback-*.md")))


def run_tasks(
    logger: logging.Logger,
    ids: list[int],
    force: bool,
    tool: str,
    rounds: int,
    glm_plan: bool,
    attempt_mode: bool,
    live_view: bool = False,
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
        memory_count = infer_memory_sequence(task) - 1
        attempt = infer_attempt(task) if attempt_mode else 1
        feedback_count = _count_feedback_files(task) if attempt_mode else 0
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
            code = _run_tool(
                tool, prompt, log_path, logger, extra_env=extra_env, live_view=live_view
            )
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
        task.transition_to("completed")
        task.completed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        save_task(task)
        logger.info('Task [%d] "%s" completed', task.id, task.slug)
        _auto_complete_parent(task, logger)
    return 1 if has_failure else 0
