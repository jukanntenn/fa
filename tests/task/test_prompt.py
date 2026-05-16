from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fa.core.config import package_template_dir
from fa.task import prompt
from fa.task.model import Task


def test_infer_memory_sequence_returns_one_without_files(tmp_path: Path) -> None:
    task = Task.new(1, "demo", None, tmp_path)

    assert prompt.infer_memory_sequence(task) == 1


def test_infer_memory_sequence_counts_existing_files(tmp_path: Path) -> None:
    task_path = tmp_path
    task_path.joinpath("memory-1.md").write_text("a", encoding="utf-8")
    task_path.joinpath("memory-2.md").write_text("b", encoding="utf-8")
    task = Task.new(1, "demo", None, task_path)

    assert prompt.infer_memory_sequence(task) == 3


def test_infer_attempt_returns_one_without_files(tmp_path: Path) -> None:
    task = Task.new(1, "demo", None, tmp_path)

    assert prompt.infer_attempt(task) == 1


def test_infer_attempt_counts_existing_files(tmp_path: Path) -> None:
    task_path = tmp_path
    task_path.joinpath("feedback-1.md").write_text("a", encoding="utf-8")
    task_path.joinpath("feedback-2.md").write_text("b", encoding="utf-8")
    task = Task.new(1, "demo", None, task_path)

    assert prompt.infer_attempt(task) == 3


def test_task_template_prefers_override_template(tmp_path: Path) -> None:
    override_dir = tmp_path / ".fa" / "templates"
    override_dir.mkdir(parents=True)
    template_name = "task_prompt.j2"
    override_dir.joinpath(template_name).write_text("override", encoding="utf-8")
    with patch.object(prompt, "fa_dir", return_value=tmp_path / ".fa"):
        env, selected = prompt.task_template()

        assert selected == template_name
        assert env.get_template(template_name).render() == "override"


def test_task_template_falls_back_to_packaged_template(tmp_path: Path) -> None:
    fa_path = tmp_path / ".fa"
    (fa_path / "templates").mkdir(parents=True)
    with patch.object(prompt, "fa_dir", return_value=fa_path):
        env, selected = prompt.task_template()

        assert selected == "task_prompt.j2"
        loader = env.loader
        assert loader is not None
        loaded_dir = Path(loader.searchpath[0])
        assert loaded_dir == package_template_dir()


def test_build_task_prompt_raises_on_missing_template(tmp_path: Path) -> None:
    from jinja2 import TemplateNotFound

    task = Task.new(1, "demo", None, tmp_path)
    (tmp_path / "spec.md").write_text("# spec", encoding="utf-8")
    (tmp_path / "plan.md").write_text("# plan", encoding="utf-8")
    mock_env = type(
        "MockEnv",
        (),
        {
            "get_template": lambda self, name: (_ for _ in ()).throw(
                TemplateNotFound(name)
            )
        },
    )()
    with (
        patch.object(
            prompt, "task_template", return_value=(mock_env, "nonexistent.j2")
        ),
        patch.object(prompt, "relative_path", side_effect=lambda p: str(p)),
    ):
        with pytest.raises(FileNotFoundError, match="template not found"):
            prompt.build_task_prompt(task, None, False)


def test_build_task_prompt_with_parent(tmp_path: Path) -> None:
    parent = Task.new(1, "parent", None, tmp_path / "parent")
    parent.path.mkdir(parents=True)
    (parent.path / "spec.md").write_text("# parent spec", encoding="utf-8")
    child = Task.new(2, "child", parent.id, tmp_path / "child")
    child.path.mkdir(parents=True)
    (child.path / "spec.md").write_text("# child spec", encoding="utf-8")
    (child.path / "plan.md").write_text("# child plan", encoding="utf-8")
    with patch.object(prompt, "relative_path", side_effect=lambda p: str(p)):
        result = prompt.build_task_prompt(child, parent, False)
    assert "child" in result


def test_build_prompt_context_parent_counts(tmp_path: Path) -> None:
    parent_path = tmp_path / "parent"
    parent_path.mkdir()
    for i in range(1, 4):
        (parent_path / f"memory-{i}.md").write_text(f"mem {i}", encoding="utf-8")
    for i in range(1, 3):
        (parent_path / f"feedback-{i}.md").write_text(f"fb {i}", encoding="utf-8")
    parent = Task.new(1, "parent", None, parent_path)

    child_path = tmp_path / "child"
    child_path.mkdir()
    child = Task.new(2, "child", parent.id, child_path)

    with patch.object(prompt, "relative_path", side_effect=lambda p: str(p)):
        ctx = prompt._build_prompt_context(child, parent, is_attempt_run=False)
    assert ctx["parent_memory_count"] == 3
    assert ctx["parent_feedback_count"] == 2


def test_template_env_returns_environment_with_strict_undefined(tmp_path: Path) -> None:
    from jinja2 import StrictUndefined

    env = prompt.template_env(tmp_path)
    assert env.undefined is StrictUndefined
    assert env.autoescape is False
    assert env.trim_blocks is True
    assert env.lstrip_blocks is True


def test_numbered_paths(tmp_path: Path) -> None:
    original = prompt.relative_path
    prompt.relative_path = lambda p: str(p)
    try:
        result = prompt._numbered_paths(tmp_path, "memory", 4)
    finally:
        prompt.relative_path = original

    assert len(result) == 3
    assert all("memory-" in r for r in result)
    assert result[0].endswith("memory-1.md")
    assert result[1].endswith("memory-2.md")
    assert result[2].endswith("memory-3.md")


def test_numbered_paths_empty(tmp_path: Path) -> None:
    original = prompt.relative_path
    prompt.relative_path = lambda p: str(p)
    try:
        result = prompt._numbered_paths(tmp_path, "memory", 1)
    finally:
        prompt.relative_path = original

    assert result == []
