from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
