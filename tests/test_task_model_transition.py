from __future__ import annotations

import pytest

from fa.task.model import InvalidTransition, Task


def test_transition_to_invalid_status(storage_root):
    task = Task.new(1, "test", None, storage_root / "t1")
    with pytest.raises(ValueError, match="unknown status"):
        task.transition_to("invalid_status")


def test_transition_to_invalid_transition(storage_root):
    task = Task.new(1, "test", None, storage_root / "t1")
    with pytest.raises(InvalidTransition):
        task.transition_to("completed")


def test_transition_to_valid_transition(storage_root):
    task = Task.new(1, "test", None, storage_root / "t1")
    task.transition_to("approved")
    assert task.status == "approved"
