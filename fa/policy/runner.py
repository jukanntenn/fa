from __future__ import annotations

import fnmatch
import subprocess
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from fa.core.config import AGENT_LOGS_DIR_NAME, LOGS_DIR_NAME, TOOL_COMMANDS
from fa.core.git import changed_files, is_git_repo
from fa.policy.model import Policy
from fa.policy.storage import load_policy, write_report
from fa.task.storage import fa_dir, project_root


def _iter_files(base: Path) -> list[Path]:
    if base.is_file():
        return [base]
    if base.is_dir():
        return [file for file in base.rglob("*") if file.is_file()]
    return []


def _expand_entry(entry: str) -> list[Path]:
    root = project_root()
    if entry.startswith("git:"):
        value = entry[4:]
        target = (root / value).resolve()
        if not is_git_repo(root):
            return _iter_files(target)
        candidates = changed_files(root)
        if target.is_dir():
            return [path for path in candidates if path.is_file() and target in path.parents]
        return [path for path in candidates if path == target]
    return _iter_files((root / entry).resolve())


def scoped_files(policy: Policy) -> list[str]:
    root = project_root()
    files: set[Path] = set()
    for entry in policy.scopes.required + policy.scopes.optional:
        files.update(_expand_entry(entry))
    relative = [str(path.relative_to(root)) for path in files if path.exists()]
    result: list[str] = []
    for value in sorted(relative):
        if any(fnmatch.fnmatch(value, pattern) for pattern in policy.scopes.exclude):
            continue
        result.append(value)
    return result


def _policy_prompt(policy: Policy, file_paths: list[str], report_path: str) -> str:
    lines = [
        f"# Policy: {policy.name}",
        "",
        "## Objective",
        "",
        policy.objective,
        "",
        "## Specs",
        "",
    ]
    lines.extend(f"- {item}" for item in policy.specs)
    lines.extend(["", "## Scope Files", ""])
    lines.extend(f"- {item}" for item in file_paths)
    lines.extend(["", "After completion, write report to:", report_path])
    return "\n".join(lines)


def _run_tool(tool: str, prompt: str, log_file: Path, logger) -> int:
    cmd = [piece.format(prompt=prompt) for piece in TOOL_COMMANDS[tool]]
    logger.debug("Executing agent tool command: %s", cmd)
    try:
        with log_file.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    except OSError:
        return 1
    return int(result.returncode)


def run_policy(logger, policy_id: str, tool: str, rounds: int) -> int:
    policy = load_policy(policy_id)
    files = scoped_files(policy)
    date = datetime.now().strftime("%Y-%m-%d")
    report_rel = Template(policy.report.path).render(policy=policy, date=date)
    report_path = (project_root() / report_rel).resolve()
    prompt = _policy_prompt(policy, files, report_rel)
    logs_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / f"policy-{policy.id}"
    logs_dir.mkdir(parents=True, exist_ok=True)
    has_failure = False
    for round_index in range(1, rounds + 1):
        log_file = logs_dir / f"round-{round_index}-{tool}.log"
        if _run_tool(tool, prompt, log_file, logger) != 0:
            has_failure = True
    report_content = Template(policy.report.template).render(
        policy=policy,
        date=date,
        files=files,
        success=not has_failure,
    )
    write_report(report_path, report_content)
    if has_failure:
        logger.error("Policy %s failed", policy.id)
        return 1
    logger.info("Policy %s completed", policy.id)
    return 0


def run_policies_by_ids(logger, policy_ids: list[str], tool: str, rounds: int) -> int:
    has_failure = False
    for policy_id in policy_ids:
        try:
            code = run_policy(logger, policy_id, tool=tool, rounds=rounds)
        except FileNotFoundError:
            logger.error("Policy %s not found", policy_id)
            code = 1
        if code != 0:
            has_failure = True
    return 1 if has_failure else 0
