from __future__ import annotations

import fnmatch
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    LOGS_DIR_NAME,
    TOOL_AGENT_ARG,
    TOOL_COMMANDS,
)
from fa.core.git import changed_files, is_git_repo
from fa.core.quota import check_glm_quota
from fa.policy.model import Policy
from fa.policy.storage import load_policy
from fa.task.storage import fa_dir, project_root


def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        env[key.strip()] = value.strip()
    return env


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
            return [
                path for path in candidates if path.is_file() and target in path.parents
            ]
        return [path for path in candidates if path == target]
    return _iter_files((root / entry).resolve())


def scoped_files(policy: Policy) -> list[str]:
    root = project_root()
    files: set[Path] = set()
    for entry in policy.scopes.required:
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


def _run_tool(
    tool: str,
    prompt: str,
    log_file: Path,
    logger: logging.Logger,
    agent: str = "rectifier",
    extra_env: dict[str, str] | None = None,
) -> int:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    arg_style = TOOL_AGENT_ARG.get(tool, "--agent")
    template = TOOL_COMMANDS[tool]
    if arg_style == "$":
        prompt = f"${agent} {prompt}"
        cmd = [piece.format(prompt=prompt) for piece in template]
    else:
        cmd: list[str] = []
        for piece in template:
            if piece == "{prompt}":
                cmd.extend([arg_style, agent])
            cmd.append(piece.format(prompt=prompt))
    logger.debug("Executing agent tool command: %s", cmd)
    env = {**os.environ, **extra_env} if extra_env else None
    try:
        with log_file.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                env=env,
            )
    except OSError:
        return 1
    return int(result.returncode)


def _save_prompt(log_dir: Path, round_index: int, prompt: str) -> Path:
    path = log_dir / f"round-{round_index}-prompt.md"
    path.write_text(prompt, encoding="utf-8")
    return path


def run_policy(
    logger: logging.Logger,
    policy_id: str,
    tool: str,
    rounds: int,
    glm_plan: bool = False,
) -> int:
    # Load .env from cwd for codex
    extra_env: dict[str, str] | None = None
    if tool == "codex":
        dotenv = _load_dotenv(Path.cwd() / ".env")
        if "CODEX_API_KEY" in dotenv:
            extra_env = {"CODEX_API_KEY": dotenv["CODEX_API_KEY"]}

    logs_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / f"policy-{policy_id}"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.info('Policy "%s" started | rounds=%d | tool=%s', policy_id, rounds, tool)
    has_failure = False
    for round_index in range(1, rounds + 1):
        date = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S")
        if glm_plan and not check_glm_quota(logger):
            logger.error(
                'Policy "%s" round %d/%d skipped - GLM quota check failed',
                policy_id,
                round_index,
                rounds,
            )
            has_failure = True
            break
        policy = load_policy(
            policy_id,
            context={"date": date, "time": time_str, "round": round_index},
        )
        files = scoped_files(policy)
        logger.debug(
            'Policy "%s" scope resolved | round=%d | declarations=%s | files=%s',
            policy.id,
            round_index,
            policy.scopes.required,
            files,
        )
        report_rel = policy.report.path
        prompt = _policy_prompt(policy, files, report_rel)
        _save_prompt(logs_dir, round_index, prompt)
        logger.debug(
            "Prompt rendered | policy=%s | round=%d | scope_files=%d | chars=%d",
            policy.id,
            round_index,
            len(files),
            len(prompt),
        )
        log_file = logs_dir / f"round-{round_index}-{tool}.log"
        logger.info(
            'Policy "%s" round %d/%d started | tool=%s | files=%d',
            policy.id,
            round_index,
            rounds,
            tool,
            len(files),
        )
        t0 = time.monotonic()
        code = _run_tool(tool, prompt, log_file, logger, agent=policy.agent, extra_env=extra_env)
        elapsed = int(time.monotonic() - t0)
        logger.info(
            'Policy "%s" round %d/%d completed in %ds | exit_code=%d',
            policy.id,
            round_index,
            rounds,
            elapsed,
            code,
        )
        if code != 0:
            has_failure = True
    if has_failure:
        logger.error('Policy "%s" failed', policy_id)
        return 1
    logger.info('Policy "%s" completed', policy_id)
    return 0


def run_policies_by_ids(
    logger: logging.Logger,
    policy_ids: list[str],
    tool: str,
    rounds: int,
    glm_plan: bool = False,
) -> int:
    has_failure = False
    for policy_id in policy_ids:
        try:
            code = run_policy(
                logger, policy_id, tool=tool, rounds=rounds, glm_plan=glm_plan
            )
        except FileNotFoundError:
            logger.error("Policy %s not found", policy_id)
            code = 1
        if code != 0:
            has_failure = True
    return 1 if has_failure else 0
