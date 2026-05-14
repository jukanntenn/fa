from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from fa.task.model import InvalidTransition, Task


def test_from_dict_normalizes_status_alias() -> None:
    task = Task.from_dict(
        {
            "id": 1,
            "slug": "demo",
            "status": "pending",
            "created_at": "2026-05-13T00:00:00",
        },
        Path("/tmp/task"),
    )

    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []


def test_to_dict_excludes_path() -> None:
    task = Task(
        id=1,
        slug="demo",
        parent_id=None,
        status="draft",
        depends_on=[2],
        related_to=[3],
        created_at="2026-05-13T00:00:00",
        completed_at=None,
        path=Path("/tmp/task"),
    )

    assert task.to_dict() == {
        "id": 1,
        "slug": "demo",
        "parent_id": None,
        "status": "draft",
        "depends_on": [2],
        "related_to": [3],
        "created_at": "2026-05-13T00:00:00",
        "completed_at": None,
    }
    assert "path" not in task.to_dict()


def test_new_uses_draft_defaults_and_timestamp_format() -> None:
    task = Task.new(7, "demo", None, Path("/tmp/task"))

    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []
    datetime.strptime(task.created_at, "%Y-%m-%dT%H:%M:%S")


def test_transition_to_accepts_valid_transition() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    task.transition_to("approved")

    assert task.status == "approved"


def test_transition_to_rejects_invalid_transition() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    with pytest.raises(InvalidTransition):
        task.transition_to("completed")


def test_transition_to_rejects_unknown_status() -> None:
    task = Task.new(1, "demo", None, Path("/tmp/task"))

    with pytest.raises(ValueError):
        task.transition_to("unknown")
