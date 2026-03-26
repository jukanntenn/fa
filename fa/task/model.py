from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


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
        return cls(
            id=int(data["id"]),
            slug=str(data["slug"]),
            parent_id=data.get("parent_id"),
            status=str(data.get("status", "pending")),
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

    @staticmethod
    def new(task_id: int, slug: str, parent_id: int | None, path: Path) -> "Task":
        return Task(
            id=task_id,
            slug=slug,
            parent_id=parent_id,
            status="pending",
            depends_on=[],
            related_to=[],
            created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            completed_at=None,
            path=path,
        )
