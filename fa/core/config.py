from __future__ import annotations

from pathlib import Path


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


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
        env[key.strip()] = _strip_quotes(value.strip())
    return env


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
    "codex": ["codex", "exec", "--full-auto", "{prompt}"],
}

TOOL_AGENT_ARG: dict[str, str] = {
    "claude": "--agent",
    "ccr": "--agent",
    "opencode": "--agent",
    "kilo": "--agent",
    "codex": "$",
}


def build_tool_cmd(tool: str, prompt: str, *, agent: str | None = None) -> list[str]:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    template = TOOL_COMMANDS[tool]
    if agent is not None:
        arg_style = TOOL_AGENT_ARG.get(tool, "--agent")
        if arg_style == "$":
            agent_prompt = f"${agent} {prompt}"
            return [part.format(prompt=agent_prompt) for part in template]
        cmd = [part.format(prompt=prompt) for part in template]
        idx = template.index("{prompt}")
        cmd[idx:idx] = [arg_style, agent]
        return cmd
    return [part.format(prompt=prompt) for part in template]


def tool_extra_env(tool: str) -> dict[str, str] | None:
    if tool != "codex":
        return None
    dotenv = _load_dotenv(Path.cwd() / ".env")
    if "CODEX_API_KEY" in dotenv:
        return {"CODEX_API_KEY": dotenv["CODEX_API_KEY"]}
    return None


VALID_STATUSES = {"draft", "approved", "running", "failed", "completed"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved"},
    "approved": {"running", "completed"},
    "running": {"completed", "failed"},
    "failed": {"running", "completed"},
    "completed": set(),
}

STATUS_ALIASES: dict[str, str] = {"pending": "draft"}


def package_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"
