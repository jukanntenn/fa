from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_STATUSES = {"draft", "approved", "running", "failed", "completed"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved"},
    "approved": {"running", "completed"},
    "running": {"completed", "failed"},
    "failed": {"running", "completed"},
    "completed": set(),
}

STATUS_ALIASES: dict[str, str] = {"pending": "draft"}

_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S"


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid transition: {current} → {target}")


@dataclass
class Task:
    id: int
    slug: str
    parent_id: int | None
    status: str
    depends_on: list[int]
    related_to: list[int]
    created_at: str
    completed_at: str | None
    path: Path

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path) -> "Task":
        raw_status = str(data.get("status", "draft"))
        status = STATUS_ALIASES.get(raw_status, raw_status)
        return cls(
            id=int(data["id"]),
            slug=str(data["slug"]),
            parent_id=data.get("parent_id"),
            status=status,
            depends_on=list(data.get("depends_on", [])),
            related_to=list(data.get("related_to", [])),
            created_at=str(data["created_at"]),
            completed_at=data.get("completed_at"),
            path=path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "parent_id": self.parent_id,
            "status": self.status,
            "depends_on": self.depends_on,
            "related_to": self.related_to,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def transition_to(self, target: str) -> None:
        if target not in VALID_STATUSES:
            raise ValueError(f"unknown status: {target}")
        if target not in VALID_TRANSITIONS.get(self.status, set()):
            raise InvalidTransition(self.status, target)
        self.status = target

    def complete(self) -> None:
        self.transition_to("completed")
        self.completed_at = datetime.now().strftime(_TIMESTAMP_FMT)

    @staticmethod
    def new(task_id: int, slug: str, parent_id: int | None, path: Path) -> "Task":
        return Task(
            id=task_id,
            slug=slug,
            parent_id=parent_id,
            status="draft",
            depends_on=[],
            related_to=[],
            created_at=datetime.now().strftime(_TIMESTAMP_FMT),
            completed_at=None,
            path=path,
        )
