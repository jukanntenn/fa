from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import typer

from fa.task.model import Task
from fa.task.runner import build_execution_plan, run_tasks
from fa.task.storage import all_tasks, find_children, find_task, save_task


def _find_new_parent_task(preexisting_ids: frozenset[int]) -> Task | None:
    tasks = all_tasks()
    new_tasks = [t for tid, t in tasks.items() if tid not in preexisting_ids]
    if not new_tasks:
        return None
    no_parent = [t for t in new_tasks if t.parent_id is None]
    if no_parent:
        return min(no_parent, key=lambda t: t.id)
    return min(new_tasks, key=lambda t: t.id)


def _extract_text_from_create_log(log_path: Path, tool: str) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if tool not in {"claude", "ccr"}:
        return text

    collected: list[str] = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "result" and isinstance(obj.get("result"), str):
            collected.append(obj["result"])
            continue
        if obj.get("type") != "assistant":
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                collected.append(block["text"])
    return "\n".join(collected)


def _parse_task_reference(text: str) -> tuple[int, Path | None] | None:
    candidates = re.findall(r"```json\s*(.*?)```", text, flags=re.DOTALL)
    candidates.extend(re.findall(r"\{[^{}]*\"task_id\"[^{}]*\}", text, flags=re.DOTALL))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        task_id = obj.get("task_id")
        if not isinstance(task_id, int):
            continue
        task_path = obj.get("task_path")
        if isinstance(task_path, str) and task_path:
            return task_id, Path(task_path)
        return task_id, None
    return None


def _find_created_task(
    preexisting_ids: frozenset[int], log_path: Path, tool: str
) -> Task | None:
    text = _extract_text_from_create_log(log_path, tool)
    reference = _parse_task_reference(text)
    if reference is not None:
        task_id, task_path = reference
        task = find_task(task_id)
        if task is not None and task.id not in preexisting_ids:
            if task_path is None or task.path.resolve() == task_path.resolve():
                return task
    return _find_new_parent_task(preexisting_ids)


def _resolve_task_descendants(task: Task) -> list[Task]:
    descendants: list[Task] = []

    def visit(parent_id: int) -> None:
        for child in sorted(find_children(parent_id), key=lambda item: item.id):
            descendants.append(child)
            visit(child.id)

    visit(task.id)
    return descendants


def _approve_task_descendants(task: Task) -> tuple[int, int, bool]:
    descendants = _resolve_task_descendants(task)
    approved_count = 0
    approval_failed = False
    for child in descendants:
        if child.status == "draft":
            child.transition_to("approved")
            save_task(child)
            approved_count += 1
        elif child.status not in {"approved", "failed", "completed"}:
            typer.echo(
                f"Warning: subtask {child.id} is '{child.status}', skipped approval",
                err=True,
            )
            approval_failed = True
    return approved_count, len(descendants), approval_failed


def _resolve_to_leaves(task_ids: list[int]) -> list[int]:
    tasks = all_tasks()
    leaves: list[int] = []
    seen: set[int] = set()

    def visit(task_id: int) -> None:
        children = sorted(find_children(task_id), key=lambda item: item.id)
        if not children:
            if task_id not in seen:
                leaves.append(task_id)
                seen.add(task_id)
            return
        for child in children:
            visit(child.id)

    for task_id in task_ids:
        if task_id in tasks:
            visit(task_id)
    return leaves


def _resolve_execution_candidates(task: Task) -> list[int]:
    tasks = all_tasks()
    leaf_ids = _resolve_to_leaves([task.id])
    return sorted(
        task_id
        for task_id in leaf_ids
        if task_id in tasks and tasks[task_id].status in {"approved", "failed"}
    )


def _run_runnable_task_tree(
    task: Task,
    logger: logging.Logger,
    tool: str,
    rounds: int,
    glm_plan: bool,
    *,
    open_viewer: bool = False,
) -> int:
    tasks = all_tasks()
    candidates = _resolve_execution_candidates(task)
    if not candidates:
        logger.info("No runnable tasks to run after gestate.")
        typer.echo("No runnable tasks to run after gestate.")
        return 0
    plan = build_execution_plan(tasks, candidates)
    typer.echo(f"Running task(s) after gestate: {','.join(str(i) for i in plan)}")
    return run_tasks(
        logger=logger,
        ids=plan,
        force=False,
        tool=tool,
        rounds=rounds,
        glm_plan=glm_plan,
        attempt_mode=False,
        open_viewer=open_viewer,
    )


def _validate_task(task: Task) -> list[str]:
    issues: list[str] = []
    if task.status != "draft":
        issues.append(f"task {task.id} status is '{task.status}', expected 'draft'")
    all_t = all_tasks()
    has_children = any(t.parent_id == task.id for t in all_t.values())

    if has_children:
        if not (task.path / "spec.md").exists():
            issues.append(f"task {task.id} missing spec.md")
        for child in all_t.values():
            if child.parent_id == task.id and not (child.path / "plan.md").exists():
                issues.append(f"subtask {child.id} missing plan.md")
    elif task.parent_id is not None:
        if task.parent_id in all_t:
            if not (task.path / "plan.md").exists():
                issues.append(f"task {task.id} missing plan.md")
        else:
            if not (task.path / "spec.md").exists():
                issues.append(f"task {task.id} missing spec.md")
            if not (task.path / "plan.md").exists():
                issues.append(f"task {task.id} missing plan.md")
    else:
        if not (task.path / "spec.md").exists():
            issues.append(f"task {task.id} missing spec.md")
        if not (task.path / "plan.md").exists():
            issues.append(f"task {task.id} missing plan.md")
    return issues
