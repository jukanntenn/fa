from __future__ import annotations

from pathlib import Path

from fa.core.env import load_dotenv

FA_DIR_NAME = ".fa"
TASKS_DIR_NAME = "tasks"
ARCHIVE_DIR_NAME = "archive"
LOGS_DIR_NAME = "logs"
AGENT_LOGS_DIR_NAME = "agents"
POLICIES_DIR_NAME = "policies"
TEMPLATES_DIR_NAME = "templates"
TASK_JSON_FILE_NAME = "task.json"
PROMPT_TEMPLATE_NAME = "task_prompt.j2"
FA_LOG_FILE_NAME = "fa.log"

TOOL_COMMANDS: dict[str, list[str]] = {
    "kilo": [
        "kilo",
        "run",
        "--auto",
        "{prompt}",
        "--print-logs",
        "--log-level",
        "DEBUG",
    ],
    "claude": [
        "claude",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "{prompt}",
    ],
    "ccr": [
        "ccr",
        "code",
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "{prompt}",
    ],
    "opencode": ["opencode", "run", "{prompt}", "--print-logs", "--log-level", "DEBUG"],
    "codex": ["codex", "exec", "-s", "danger-full-access", "{prompt}"],
}

TOOL_AGENT_ARG: dict[str, str] = {
    "claude": "--agent",
    "ccr": "--agent",
    "opencode": "--agent",
    "kilo": "--agent",
    "codex": "$",
}


def _render_cmd_template(template: list[str], prompt: str) -> tuple[list[str], int]:
    prompt_idx = template.index("{prompt}")
    return [part.format(prompt=prompt) for part in template], prompt_idx


def _build_agent_cmd(
    template: list[str], prompt: str, agent: str, arg_style: str
) -> tuple[list[str], int]:
    if arg_style == "$":
        return _render_cmd_template(template, f"${agent} {prompt}")
    cmd, prompt_idx = _render_cmd_template(template, prompt)
    cmd[prompt_idx:prompt_idx] = [arg_style, agent]
    return cmd, prompt_idx + 2


def build_tool_cmd(
    tool: str,
    prompt: str,
    *,
    agent: str | None = None,
    model: str | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    template = TOOL_COMMANDS[tool]
    if agent is not None:
        cmd, prompt_idx = _build_agent_cmd(
            template, prompt, agent, TOOL_AGENT_ARG.get(tool, "--agent")
        )
    else:
        cmd, prompt_idx = _render_cmd_template(template, prompt)

    inserts: list[str] = []
    if model is not None:
        inserts.extend(["--model", model])
    if extra_args:
        inserts.extend(extra_args)
    if inserts:
        cmd[prompt_idx:prompt_idx] = inserts

    return cmd


def tool_extra_env(tool: str) -> dict[str, str] | None:
    if tool != "codex":
        return None
    dotenv = load_dotenv(Path.cwd() / ".env")
    if "CODEX_API_KEY" in dotenv:
        return {"CODEX_API_KEY": dotenv["CODEX_API_KEY"]}
    return None


def package_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"
