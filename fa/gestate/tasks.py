from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from fa.core.logview_parse import STREAM_JSON_TOOLS
from fa.task.model import Task
from fa.task.storage import (
    all_tasks,
    find_children,
    find_task,
    resolve_to_leaves,
    save_task,
)


def _find_new_parent_task(preexisting_ids: frozenset[int]) -> Task | None:
    tasks = all_tasks()
    new_tasks = [t for tid, t in tasks.items() if tid not in preexisting_ids]
    if not new_tasks:
        return None
    no_parent = [t for t in new_tasks if t.parent_id is None]
    if no_parent:
        return min(no_parent, key=lambda t: t.id)
    return min(new_tasks, key=lambda t: t.id)


def _extract_text_from_jsonl(text: str) -> str:
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


def _extract_text_from_create_log(log_path: Path, tool: str) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if tool not in STREAM_JSON_TOOLS:
        return text
    return _extract_text_from_jsonl(text)


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


def _resolve_execution_candidates(task: Task) -> list[int]:
    tasks = all_tasks()
    leaf_ids = resolve_to_leaves([task.id], tasks)
    return sorted(
        task_id
        for task_id in leaf_ids
        if task_id in tasks and tasks[task_id].status in {"approved", "failed"}
    )


def _validate_task(task: Task) -> list[str]:
    issues: list[str] = []
    if task.status != "draft":
        issues.append(f"task {task.id} status is '{task.status}', expected 'draft'")
    tasks_dict = all_tasks()
    children = find_children(task.id)
    has_children = bool(children)
    need_spec = (
        has_children or task.parent_id is None or task.parent_id not in tasks_dict
    )
    need_plan = not has_children

    if need_spec and not (task.path / "spec.md").exists():
        issues.append(f"task {task.id} missing spec.md")
    if need_plan and not (task.path / "plan.md").exists():
        issues.append(f"task {task.id} missing plan.md")

    for child in children:
        if not (child.path / "plan.md").exists():
            issues.append(f"subtask {child.id} missing plan.md")
    return issues
