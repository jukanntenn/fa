from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from fa.core.config import build_tool_cmd


def run_tool_subprocess(
    cmd: list[str],
    log_file: Path,
    extra_env: dict[str, str] | None = None,
    stdin: int | None = None,
) -> int:
    env = {**os.environ, **extra_env} if extra_env else None
    try:
        with log_file.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=stdin,
                text=True,
                check=False,
                env=env,
            )
    except OSError:
        return 1
    return int(result.returncode)


def run_tool(
    tool: str,
    prompt: str,
    log_file: Path,
    logger: logging.Logger,
    *,
    agent: str | None = None,
    extra_env: dict[str, str] | None = None,
    stdin: int | None = None,
) -> int:
    cmd = build_tool_cmd(tool, prompt, agent=agent)
    logger.debug("Executing agent tool command: %s", cmd)
    return run_tool_subprocess(cmd, log_file, extra_env, stdin=stdin)
