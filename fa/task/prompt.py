from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from fa.core.config import PROMPT_TEMPLATE_NAME, TASK_FILE_NAME, package_template_dir
from fa.task.model import Task
from fa.task.storage import fa_dir, project_root, relative_path


def _template_env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def task_template() -> tuple[Environment, str]:
    override = fa_dir() / "templates"
    if (override / PROMPT_TEMPLATE_NAME).is_file():
        return _template_env(override), PROMPT_TEMPLATE_NAME
    return _template_env(package_template_dir()), PROMPT_TEMPLATE_NAME


def infer_memory_sequence(task: Task) -> int:
    memory_files = sorted(task.path.glob("memory-*.md"))
    return len(memory_files) + 1


def infer_attempt(task: Task) -> int:
    feedback_files = sorted(task.path.glob("feedback-*.md"))
    return len(feedback_files) + 1


def build_task_prompt(task: Task, parent: Task | None, is_attempt_run: bool) -> str:
    memory_sequence = infer_memory_sequence(task)
    attempt = infer_attempt(task) if is_attempt_run else 1

    # Memory files for current task (all existing memory files)
    memory_files = [
        relative_path(task.path / f"memory-{index}.md")
        for index in range(1, memory_sequence)
    ]

    # Feedback files for current task (only in attempt mode)
    feedback_files = [
        relative_path(task.path / f"feedback-{index}.md") for index in range(1, attempt)
    ]

    # Split feedback into history and latest
    history_feedback_files = feedback_files[:-1] if len(feedback_files) > 1 else []
    latest_feedback_file = feedback_files[-1] if feedback_files else None

    # Parent context counts
    if parent:
        parent_memory_files = sorted(parent.path.glob("memory-*.md"))
        parent_feedback_files = sorted(parent.path.glob("feedback-*.md"))
        parent_memory_count = len(parent_memory_files)
        parent_feedback_count = len(parent_feedback_files)
    else:
        parent_memory_count = 0
        parent_feedback_count = 0

    memory_output_path = relative_path(task.path / f"memory-{memory_sequence}.md")
    env, template_name = task_template()
    try:
        template = env.get_template(template_name)
    except TemplateNotFound as exc:
        raise FileNotFoundError("template not found") from exc
    return template.render(
        task=task.to_dict(),
        parent=parent.to_dict() if parent else None,
        task_file=relative_path(task.path / TASK_FILE_NAME),
        parent_file=relative_path(parent.path / TASK_FILE_NAME) if parent else None,
        attempt=attempt,
        is_attempt_run=is_attempt_run,
        memory_files=memory_files,
        history_feedback_files=history_feedback_files,
        latest_feedback_file=latest_feedback_file,
        parent_memory_count=parent_memory_count,
        parent_feedback_count=parent_feedback_count,
        memory_output_path=memory_output_path,
        specs_dir=str(project_root() / "specs"),
    )
