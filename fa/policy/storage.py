from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Template

from fa.core.config import POLICIES_DIR_NAME
from fa.policy.model import Policy
from fa.task.storage import fa_dir, project_root


def policies_dir() -> Path:
    return fa_dir() / POLICIES_DIR_NAME


def policy_file(policy_id: str) -> Path:
    return policies_dir() / f"{policy_id}.yml"


def list_policy_files() -> list[Path]:
    return sorted(policies_dir().glob("*.yml"))


def load_policy(policy_id: str, context: dict | None = None) -> Policy:
    path = policy_file(policy_id)
    if not path.is_file():
        raise FileNotFoundError(f"policy {policy_id} not found")
    raw = path.read_text(encoding="utf-8")
    render_ctx: dict = {
        "project_root": str(project_root()),
        "policy": {"id": policy_id},
    }
    if context:
        render_ctx.update(context)
    rendered = Template(raw).render(**render_ctx)
    data = yaml.safe_load(rendered) or {}
    if not isinstance(data, dict):
        raise ValueError("policy yaml must be an object")
    return Policy.from_dict(data, fallback_id=policy_id)


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def as_json(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
