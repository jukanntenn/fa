from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from fa.core.config import AGENT_LOGS_DIR_NAME, LOGS_DIR_NAME, TOOL_COMMANDS
from fa.task.model import Task
from fa.task.prompt import build_task_prompt
from fa.task.storage import all_tasks, fa_dir, save_task


def _load_settings() -> dict | None:
    path = Path.home() / ".claude" / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def check_glm_quota(logger: logging.Logger) -> bool:
    settings = _load_settings()
    token = (settings or {}).get("env", {}).get("ANTHROPIC_AUTH_TOKEN")
    if not token:
        return True
    req = urllib.request.Request("https://open.bigmodel.cn/api/monitor/usage/quota/limit")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.load(response)
    except Exception as exc:
        logger.warning("Failed to check GLM quota: %s", exc)
        return True
    for item in data.get("data", {}).get("limits", []):
        if item.get("type") != "TOKENS_LIMIT":
            continue
        percentage = float(item.get("percentage", 0))
        next_reset = item.get("nextResetTime")
        if percentage < 70:
            return True
        if not next_reset:
            return False
        wait_until = int(next_reset / 1000) + 1800
        while time.time() < wait_until:
            time.sleep(10)
        return True
    return True


def _tool_cmd(tool: str, prompt: str) -> list[str]:
    template = TOOL_COMMANDS[tool]
    return [part.format(prompt=prompt) for part in template]


def _run_tool(tool: str, prompt: str, log_file: Path, logger: logging.Logger) -> int:
    cmd = _tool_cmd(tool, prompt)
    logger.debug("Executing agent tool command: %s", cmd)
    try:
        with log_file.open("w", encoding="utf-8") as file:
            completed = subprocess.run(
                cmd,
                stdout=file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    except OSError:
        return 1
    return int(completed.returncode)


def _task_log_dir(task: Task) -> Path:
    logs_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME
    relative = task.path.relative_to(fa_dir() / "tasks")
    path = logs_dir / relative
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_execution_plan(tasks: dict[int, Task], selected_pending_ids: list[int]) -> list[int]:
    selected_set = set(selected_pending_ids)
    children: dict[int, list[int]] = {}
    for task in tasks.values():
        if task.parent_id is None:
            continue
        children.setdefault(task.parent_id, []).append(task.id)
    for child_ids in children.values():
        child_ids.sort()

    output: list[int] = []
    appended: set[int] = set()
    parent_processed: set[int] = set()
    for task_id in selected_pending_ids:
        task = tasks[task_id]
        if task.parent_id is not None:
            parent_id = task.parent_id
            if parent_id in parent_processed:
                continue
            selected_children = [
                cid for cid in children.get(parent_id, []) if cid in selected_set
            ]
            for child_id in selected_children:
                if child_id not in appended:
                    output.append(child_id)
                    appended.add(child_id)
            if parent_id in tasks and parent_id not in appended:
                output.append(parent_id)
                appended.add(parent_id)
            parent_processed.add(parent_id)
            continue
        selected_children = [cid for cid in children.get(task_id, []) if cid in selected_set]
        if selected_children:
            for child_id in selected_children:
                if child_id not in appended:
                    output.append(child_id)
                    appended.add(child_id)
            if task_id not in appended:
                output.append(task_id)
                appended.add(task_id)
            parent_processed.add(task_id)
            continue
        if task_id not in appended:
            output.append(task_id)
            appended.add(task_id)
    return output


def run_tasks(
    logger: logging.Logger,
    start: int | None,
    end: int | None,
    tool: str,
    rounds: int,
    glm_plan: bool,
    attempt_mode: bool,
) -> int:
    tasks = all_tasks()
    pending = sorted(task.id for task in tasks.values() if task.status == "pending")
    if start is not None:
        pending = [task_id for task_id in pending if task_id >= start]
    if end is not None:
        pending = [task_id for task_id in pending if task_id <= end]
    if not pending:
        logger.info("No pending tasks to run.")
        return 0
    plan = build_execution_plan(tasks, pending)
    has_failure = False
    for task_id in plan:
        if glm_plan and not check_glm_quota(logger):
            logger.error("GLM quota check failed")
            has_failure = True
            continue
        task = all_tasks().get(task_id)
        if task is None:
            logger.error("Task %s not found", task_id)
            has_failure = True
            continue
        parent = all_tasks().get(task.parent_id) if task.parent_id else None
        try:
            prompt = build_task_prompt(task, parent, is_attempt_run=attempt_mode)
        except FileNotFoundError:
            logger.error("Template not found, skipping task %s", task.id)
            has_failure = True
            continue
        task.status = "running"
        save_task(task)
        failed = False
        log_dir = _task_log_dir(task)
        for round_index in range(1, rounds + 1):
            log_path = log_dir / f"round-{round_index}-{tool}.log"
            code = _run_tool(tool, prompt, log_path, logger)
            if code != 0:
                failed = True
                has_failure = True
                break
        if failed:
            task.status = "pending"
            task.completed_at = None
            save_task(task)
            continue
        task.status = "completed"
        task.completed_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        save_task(task)
    return 1 if has_failure else 0
