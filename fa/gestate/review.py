from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fa.task.model import Task
from fa.task.storage import relative_path


def _build_review_prompt(task: Task, round_num: int, max_rounds: int) -> str:
    from fa.core.config import package_template_dir

    env = Environment(
        loader=FileSystemLoader(str(package_template_dir())),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("gestate_review.j2")
    spec_files = sorted(task.path.rglob("spec.md"))
    plan_files = sorted(task.path.rglob("plan.md"))
    return template.render(
        task=task.to_dict(),
        task_dir=relative_path(task.path),
        spec_files=[relative_path(p) for p in spec_files],
        plan_files=[relative_path(p) for p in plan_files],
        round=round_num,
        max_rounds=max_rounds,
    )
