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


def test_complete_sets_completed_at_and_status(storage_root) -> None:
    task = Task.new(1, "test", None, storage_root / "t1")
    task.transition_to("approved")
    task.complete()
    assert task.status == "completed"
    assert task.completed_at is not None


# ─── Task (extended) ───────────────────────────────────────────
def test_from_dict_normalizes_pending_status_alias_extended() -> None:
    task = Task.from_dict(
        {
            "id": 7,
            "slug": "demo-task",
            "parent_id": 3,
            "status": "pending",
            "depends_on": [1, 2],
            "related_to": [4],
            "created_at": "2026-05-13T12:00:00",
            "completed_at": None,
        },
        Path("/tmp/task"),
    )

    assert task.status == "draft"
    assert task.depends_on == [1, 2]
    assert task.related_to == [4]
    assert task.parent_id == 3
    assert task.path == Path("/tmp/task")


def test_from_dict_defaults_missing_optional_relationship_fields() -> None:
    task = Task.from_dict(
        {
            "id": 11,
            "slug": "defaults",
            "created_at": "2026-05-13T12:00:00",
        },
        Path("/tmp/defaults"),
    )

    assert task.parent_id is None
    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []
    assert task.completed_at is None


def test_to_dict_round_trips_serializable_fields() -> None:
    task = Task(
        id=9,
        slug="round-trip",
        parent_id=None,
        status="running",
        depends_on=[1],
        related_to=[2],
        created_at="2026-05-13T12:00:00",
        completed_at="2026-05-13T13:00:00",
        path=Path("/tmp/task"),
    )

    assert task.to_dict() == {
        "id": 9,
        "slug": "round-trip",
        "parent_id": None,
        "status": "running",
        "depends_on": [1],
        "related_to": [2],
        "created_at": "2026-05-13T12:00:00",
        "completed_at": "2026-05-13T13:00:00",
    }


def test_new_creates_draft_task_with_empty_relationships() -> None:
    task = Task.new(5, "new-task", 2, Path("/tmp/task"))

    assert task.id == 5
    assert task.slug == "new-task"
    assert task.parent_id == 2
    assert task.status == "draft"
    assert task.depends_on == []
    assert task.related_to == []
    assert task.completed_at is None
    assert task.path == Path("/tmp/task")
