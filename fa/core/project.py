from __future__ import annotations

from pathlib import Path

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    ARCHIVE_DIR_NAME,
    FA_DIR_NAME,
    LOGS_DIR_NAME,
    POLICIES_DIR_NAME,
    TASKS_DIR_NAME,
    TEMPLATES_DIR_NAME,
)


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        if (current / FA_DIR_NAME).is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    return (start or Path.cwd()).resolve()


def ensure_fa_structure(project_root: Path) -> Path:
    fa_dir = project_root / FA_DIR_NAME
    tasks_dir = fa_dir / TASKS_DIR_NAME
    (tasks_dir / ARCHIVE_DIR_NAME).mkdir(parents=True, exist_ok=True)
    logs_dir = fa_dir / LOGS_DIR_NAME
    (logs_dir / AGENT_LOGS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (fa_dir / POLICIES_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (fa_dir / TEMPLATES_DIR_NAME).mkdir(parents=True, exist_ok=True)
    return fa_dir
