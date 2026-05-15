from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from fa.task.commands import CandidateValidationError, _select_runnable_candidates
from fa.task.model import Task


def _task(task_id: int, status: str, path: Path) -> Task:
    return Task(
        id=task_id,
        slug=f"t-{task_id}",
        parent_id=None,
        status=status,
        depends_on=[],
        related_to=[],
        created_at="2026-01-01T00:00:00",
        completed_at=None,
        path=path,
    )


def test_force_returns_all_non_completed():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "approved", Path(tmp) / "1"),
            2: _task(2, "completed", Path(tmp) / "2"),
            3: _task(3, "failed", Path(tmp) / "3"),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2, 3], force=True, attempt=False
        )
        assert result == [1, 3]


def test_force_with_all_completed_returns_empty():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "completed", Path(tmp) / "1"),
            2: _task(2, "completed", Path(tmp) / "2"),
        }
        result = _select_runnable_candidates(tasks, [1, 2], force=True, attempt=False)
        assert result == []


def test_attempt_returns_only_with_feedback_files():
    with TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "1"
        p1.mkdir()
        (p1 / "feedback-1.md").touch()

        p2 = Path(tmp) / "2"
        p2.mkdir()
        (p2 / "feedback-2.md").touch()

        p3 = Path(tmp) / "3"
        p3.mkdir()

        tasks = {
            1: _task(1, "approved", p1),
            2: _task(2, "failed", p2),
            3: _task(3, "approved", p3),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2, 3], force=False, attempt=True
        )
        assert result == [1, 2]


def test_attempt_with_no_feedback_files_returns_empty():
    with TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "1"
        p1.mkdir()
        p2 = Path(tmp) / "2"
        p2.mkdir()

        tasks = {
            1: _task(1, "approved", p1),
            2: _task(2, "failed", p2),
        }
        result = _select_runnable_candidates(tasks, [1, 2], force=False, attempt=True)
        assert result == []


def test_attempt_excludes_non_approved_failed():
    with TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "1"
        p1.mkdir()
        (p1 / "feedback-1.md").touch()

        p2 = Path(tmp) / "2"
        p2.mkdir()
        (p2 / "feedback-2.md").touch()

        tasks = {
            1: _task(1, "draft", p1),
            2: _task(2, "completed", p2),
        }
        result = _select_runnable_candidates(tasks, [1, 2], force=False, attempt=True)
        assert result == []


def test_default_returns_all_when_all_approved_or_failed():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "approved", Path(tmp) / "1"),
            2: _task(2, "failed", Path(tmp) / "2"),
        }
        result = _select_runnable_candidates(tasks, [1, 2], force=False, attempt=False)
        assert result == [1, 2]


def test_default_silently_filters_non_runnable():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "approved", Path(tmp) / "1"),
            2: _task(2, "draft", Path(tmp) / "2"),
            3: _task(3, "completed", Path(tmp) / "3"),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2, 3], force=False, attempt=False
        )
        assert result == [1]


def test_strict_raises_on_non_runnable():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "approved", Path(tmp) / "1"),
            2: _task(2, "draft", Path(tmp) / "2"),
        }
        with pytest.raises(CandidateValidationError) as exc_info:
            _select_runnable_candidates(
                tasks, [1, 2], force=False, attempt=False, strict=True
            )
        assert "2" in str(exc_info.value)
        assert "not approved/failed" in str(exc_info.value)


def test_strict_passes_when_all_runnable():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "approved", Path(tmp) / "1"),
            2: _task(2, "failed", Path(tmp) / "2"),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2], force=False, attempt=False, strict=True
        )
        assert result == [1, 2]


def test_force_takes_precedence_over_strict():
    with TemporaryDirectory() as tmp:
        tasks = {
            1: _task(1, "draft", Path(tmp) / "1"),
            2: _task(2, "completed", Path(tmp) / "2"),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2], force=True, attempt=False, strict=True
        )
        assert result == [1]


def test_attempt_takes_precedence_over_strict():
    with TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "1"
        p1.mkdir()
        (p1 / "feedback-1.md").touch()

        tasks = {
            1: _task(1, "approved", p1),
            2: _task(2, "draft", Path(tmp) / "2"),
        }
        result = _select_runnable_candidates(
            tasks, [1, 2], force=False, attempt=True, strict=True
        )
        assert result == [1]
