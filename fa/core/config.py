from __future__ import annotations

from pathlib import Path

FA_DIR_NAME = ".fa"
TASKS_DIR_NAME = "tasks"
ARCHIVE_DIR_NAME = "archive"
LOGS_DIR_NAME = "logs"
AGENT_LOGS_DIR_NAME = "agents"
POLICIES_DIR_NAME = "policies"
TEMPLATES_DIR_NAME = "templates"
TASK_FILE_NAME = "task.md"
TASK_JSON_FILE_NAME = "task.json"
PROMPT_TEMPLATE_NAME = "task_prompt.j2"
FA_LOG_FILE_NAME = "fa.log"

TOOL_COMMANDS: dict[str, list[str]] = {
    "iflow": ["iflow", "--prompt", "{prompt}", "-y", "--debug"],
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
    "iflow": "$",
    "opencode": "--agent",
    "kilo": "--agent",
    "codex": "$",
}

VALID_STATUSES = {"pending", "running", "completed"}


def package_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"
