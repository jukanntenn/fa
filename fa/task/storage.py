from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fa.core.config import (
    ARCHIVE_DIR_NAME,
    TASK_JSON_FILE_NAME,
    TASKS_DIR_NAME,
)
from fa.core.project import ensure_fa_structure, find_project_root
from fa.task.model import Task


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _task_name(task_id: int, slug: str, date: datetime | None = None) -> str:
    value = date or datetime.now()
    return f"{task_id}-{value.strftime('%m-%d')}-{slug}"


def project_root() -> Path:
    return find_project_root()


def fa_dir() -> Path:
    return ensure_fa_structure(project_root())


def tasks_dir() -> Path:
    return fa_dir() / TASKS_DIR_NAME


def archive_dir() -> Path:
    return tasks_dir() / ARCHIVE_DIR_NAME


def all_tasks(*, include_archive: bool = False) -> dict[int, Task]:
    root = tasks_dir()
    result: dict[int, Task] = {}
    for task_json in root.rglob(TASK_JSON_FILE_NAME):
        if not include_archive and ARCHIVE_DIR_NAME in task_json.parts:
            continue
        data = _read_json(task_json)
        if not data:
            continue
        try:
            task = Task.from_dict(data, task_json.parent)
        except (ValueError, KeyError, TypeError):
            continue
        result[task.id] = task
    return result


def all_task_ids(include_archive: bool = False) -> set[int]:
    return set(all_tasks(include_archive=include_archive).keys())


def find_task(task_id: int) -> Task | None:
    return all_tasks().get(task_id)


def _children_of(task_id: int, tasks: dict[int, Task]) -> list[Task]:
    return [t for t in tasks.values() if t.parent_id == task_id]


def find_children(parent_id: int) -> list[Task]:
    return _children_of(parent_id, all_tasks())


def resolve_to_leaves(task_ids: list[int], tasks: dict[int, Task]) -> list[int]:
    leaves: list[int] = []
    seen: set[int] = set()

    def visit(task_id: int) -> None:
        children = sorted(
            _children_of(task_id, tasks),
            key=lambda t: t.id,
        )
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


def next_task_id(parent_id: int | None = None) -> int:
    tasks = all_tasks(include_archive=True)
    used_ids = set(tasks.keys())
    if not used_ids:
        return 1
    parent_task = tasks.get(parent_id) if parent_id is not None else None
    if (
        parent_id is None
        or parent_task is None
        or ARCHIVE_DIR_NAME in parent_task.path.parts
    ):
        return max(used_ids) + 1
    candidate = parent_id + 1
    while candidate in used_ids:
        candidate += 1
    return candidate


def create_task(slug: str, parent_id: int | None = None) -> Task:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]*", slug):
        raise ValueError("slug must be alphanumeric with hyphens")
    task_id = next_task_id(parent_id)
    parent_task = find_task(parent_id) if parent_id is not None else None
    if parent_id is not None and parent_task is None:
        raise FileNotFoundError(f"task {parent_id} not found")
    base = parent_task.path if parent_task else tasks_dir()
    task_path = base / _task_name(task_id, slug)
    task_path.mkdir(parents=True, exist_ok=False)
    task = Task.new(task_id, slug, parent_id, task_path)
    _write_json(task.path / TASK_JSON_FILE_NAME, task.to_dict())
    return task


def save_task(task: Task) -> None:
    _write_json(task.path / TASK_JSON_FILE_NAME, task.to_dict())


def parse_id_range(value: str) -> list[int]:
    ids: set[int] = set()
    for piece in value.split(","):
        item = piece.strip()
        if not item:
            continue
        if "-" in item:
            start_raw, end_raw = item.split("-", 1)
            start, end = int(start_raw), int(end_raw)
            ids.update(range(start, end + 1))
        else:
            ids.add(int(item))
    return sorted(ids)


def relative_path(path: Path) -> str:
    return str(path.relative_to(project_root()))


def auto_complete_parent_of(
    tasks: dict[int, Task],
    task: Task,
    logger: logging.Logger | None = None,
) -> None:
    if not task.parent_id:
        return
    parent = tasks.get(task.parent_id)
    if parent is None or parent.status in {"completed", "draft"}:
        return
    children = _children_of(parent.id, tasks)
    if children and all(c.status == "completed" for c in children):
        parent.complete()
        save_task(parent)
        if logger:
            logger.info(
                "Parent task [%d] auto-completed (all children done)", parent.id
            )


def auto_complete_all_eligible_parents(tasks: dict[int, Task]) -> None:
    for task in tasks.values():
        auto_complete_parent_of(tasks, task)
