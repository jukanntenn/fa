from __future__ import annotations

from unittest.mock import patch

from fa.gestate.review import _build_review_prompt
from fa.task import storage


def test_build_review_prompt_renders_template(storage_root):
    with patch.object(storage, "find_project_root", return_value=storage_root):
        task = storage.create_task("test-task")
        task.transition_to("approved")
        storage.save_task(task)

        (task.path / "spec.md").write_text("# Spec", encoding="utf-8")
        (task.path / "plan.md").write_text("# Plan", encoding="utf-8")

        result = _build_review_prompt(task, round_num=1, max_rounds=5)

    assert "Round 1 of 5" in result
    assert f"ID: {task.id}" in result
    assert "Slug: test-task" in result
    assert "gestate_review" not in result


def test_build_review_prompt_includes_spec_and_plan_files(storage_root):
    with patch.object(storage, "find_project_root", return_value=storage_root):
        task = storage.create_task("test-task2")
        task.transition_to("approved")
        storage.save_task(task)

        (task.path / "spec.md").write_text("# Spec Content", encoding="utf-8")
        (task.path / "plan.md").write_text("# Plan Content", encoding="utf-8")

        result = _build_review_prompt(task, round_num=2, max_rounds=3)

    assert "Spec:" in result
    assert "Plan:" in result
