from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger("fa")

_BOLD = "\033[1m"
_DIM = "\033[2m"
RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"

STREAM_JSON_TOOLS = {"claude", "ccr"}
LIVE_VIEWER_TOOLS = {"claude", "ccr", "codex"}


def _truncate(text: str, max_len: int = 200, preserve_newlines: bool = False) -> str:
    if preserve_newlines:
        text = text.strip()
    else:
        text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


_ANSI_CSI_END = frozenset(chr(c) for c in range(0x40, 0x7F))
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

_SGR_RESET_CODES = frozenset({"22", "23", "24", "25", "27", "28", "29", "39", "49"})

_CODEX_METADATA_PREFIXES = (
    "workdir:",
    "model:",
    "provider:",
    "approval:",
    "sandbox:",
    "reasoning effort:",
    "reasoning summaries:",
    "session id:",
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _update_sgr_depth(params: str, depth: int) -> int:
    codes = params.split(";") if params else ["0"]
    i = 0
    while i < len(codes):
        code = codes[i] or "0"
        if code == "0":
            depth = 0
        elif code in _SGR_RESET_CODES:
            depth = max(0, depth - 1)
        elif code in {"38", "48"}:
            if i + 1 < len(codes) and codes[i + 1] == "5":
                i += 2
            elif i + 1 < len(codes) and codes[i + 1] == "2":
                i += 4
            depth += 1
        else:
            depth += 1
        i += 1
    return depth


def truncate_to_visible(line: str, max_cols: int) -> str:
    if max_cols <= 0:
        return ""
    result: list[str] = []
    visible = 0
    i = 0
    sgr_depth = 0
    while i < len(line):
        if visible >= max_cols:
            break
        ch = line[i]
        if ch == "\x1b" and i + 1 < len(line) and line[i + 1] == "[":
            j = i + 2
            while j < len(line) and line[j] not in _ANSI_CSI_END:
                j += 1
            if j >= len(line):
                break
            seq = line[i : j + 1]
            result.append(seq)
            if seq.endswith("m"):
                sgr_depth = _update_sgr_depth(seq[2:-1], sgr_depth)
            i = j + 1
            continue
        result.append(ch)
        visible += 1
        i += 1
    text = "".join(result)
    if sgr_depth:
        text += RESET
    return text


@dataclasses.dataclass
class _CodexState:
    section: str = "metadata"
    exec_command_seen: bool = False
    exec_output_seen: bool = False
    codex_header_seen: bool = False

    def reset_exec(self) -> None:
        self.exec_command_seen = False
        self.exec_output_seen = False


def parse_jsonl_line(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Failed to parse JSONL line: %s", raw[:500])
        return f"{_DIM}[raw] {_truncate(raw)}{RESET}"
    msg_type = obj.get("type")
    if msg_type == "system":
        return None
    if msg_type == "result":
        return _format_result(obj)
    if msg_type == "assistant":
        return _format_assistant(obj)
    if msg_type == "user":
        return _format_user(obj)
    return f"{_DIM}[unknown: {msg_type}]{RESET}"


def _extract_text_content(content: str | list) -> str:
    if isinstance(content, list):
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return " ".join(texts)
    return content


def _format_tool_result(item: dict) -> str:
    content = _extract_text_content(item.get("content", ""))
    return f"{_DIM}[tool result]{RESET}\n{_truncate(str(content), 2000, preserve_newlines=True)}"


def _format_content_item(item: dict) -> str | None:
    item_type = item.get("type")
    if item_type == "text":
        text = item.get("text", "")
        return _truncate(text, 4000, preserve_newlines=True) if text.strip() else None
    if item_type == "tool_use":
        name = item.get("name", "unknown")
        inp = item.get("input", {})
        summary = _tool_input_summary(name, inp)
        return f"{_BOLD}{_CYAN}[tool: {name}]{RESET} {summary}"
    if item_type == "thinking":
        thinking = item.get("thinking", "")
        return (
            f"{_DIM}[thinking...] {_truncate(thinking, 100)}{RESET}"
            if thinking.strip()
            else None
        )
    if item_type == "tool_result":
        return _format_tool_result(item)
    return None


def _format_message_contents(
    obj: dict,
    item_formatter: Callable[[Any], str | None],
) -> str | None:
    contents = obj.get("message", {}).get("content", [])
    if not contents:
        return None
    parts: list[str] = []
    for item in contents:
        formatted = item_formatter(item)
        if formatted is not None:
            parts.append(formatted)
    return "\n".join(parts) if parts else None


def _format_assistant(obj: dict) -> str | None:
    return _format_message_contents(obj, _format_content_item)


def _user_item_formatter(item: Any) -> str | None:
    if isinstance(item, dict) and item.get("type") == "tool_result":
        return _format_tool_result(item)
    return None


def _format_user(obj: dict) -> str | None:
    return _format_message_contents(obj, _user_item_formatter)


def _format_result(obj: dict) -> str:
    subtype = obj.get("subtype", "unknown")
    duration_ms = obj.get("duration_ms")
    result_text = obj.get("result", "")
    duration_str = f" in {duration_ms / 1000:.1f}s" if duration_ms is not None else ""
    result = str(result_text).strip()
    if subtype == "success":
        return f"{_BOLD}{_GREEN}[completed{duration_str}]{RESET}\n{result}"
    return f"{_BOLD}{_RED}[failed{duration_str}]{RESET}\n{result}"


def parse_codex_line(line: str, state: _CodexState | None = None) -> str | None:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped:
        return None
    if state is None:
        state = _CodexState()
    if stripped == "user":
        state.section = "user"
        state.reset_exec()
        return None
    if stripped == "codex":
        state.section = "codex"
        if state.exec_output_seen:
            state.reset_exec()
        return None
    if stripped == "exec":
        state.section = "exec"
        state.reset_exec()
        return None
    if stripped.startswith("OpenAI Codex "):
        state.section = "metadata"
        state.reset_exec()
        if state.codex_header_seen:
            return None
        state.codex_header_seen = True
        return f"{_DIM}[codex] {_truncate(stripped, 160)}{RESET}"
    if stripped == "--------":
        return None
    if state.exec_command_seen and raw.startswith(" "):
        lowered = stripped.lower()
        state.exec_output_seen = True
        if stripped.startswith("succeeded in "):
            return f"{_BOLD}{_GREEN}[exec succeeded] {_truncate(stripped, 160)}{RESET}"
        if "failed" in lowered or "error" in lowered or "timed out" in lowered:
            return f"{_BOLD}{_RED}[exec failed] {_truncate(stripped, 200)}{RESET}"
        return _truncate(raw, 4000, preserve_newlines=True)
    if state.exec_output_seen:
        return _truncate(raw, 4000, preserve_newlines=True)

    return _format_codex_section_line(state.section, stripped, raw, state)


def _format_codex_section_line(
    section: str,
    stripped: str,
    raw: str,
    state: _CodexState,
) -> str | None:
    lowered = stripped.lower()
    if section in {"metadata", "user"} and (
        "api error" in lowered
        or "error:" in lowered
        or lowered.startswith("failed")
        or "timed out" in lowered
    ):
        return f"{_BOLD}{_RED}[codex error]{RESET} {_truncate(stripped, 4000, preserve_newlines=True)}"
    if section == "user":
        return None
    if section == "metadata" and ":" in stripped:
        if lowered.startswith(_CODEX_METADATA_PREFIXES):
            return None
    if section == "exec":
        if not state.exec_command_seen:
            state.exec_command_seen = True
            state.exec_output_seen = False
            return f"{_BOLD}{_CYAN}[tool: exec]{RESET} {_truncate(stripped, 220)}"
        return _truncate(raw, 4000, preserve_newlines=True)
    if section == "codex":
        return f"{_BOLD}{_CYAN}[codex]{RESET} {_truncate(stripped, 4000, preserve_newlines=True)}"
    return None


def _tool_input_summary(name: str, inp: dict) -> str:
    if name in {"Read", "Write"} and "file_path" in inp:
        return inp["file_path"]
    if name == "Edit" and "file_path" in inp:
        old = _truncate(inp.get("old_string", ""), 60)
        return f"{inp['file_path']}: {old}"
    if name == "Bash" and "command" in inp:
        return _truncate(inp["command"], 100)
    if name in {"Grep", "Glob"} and "pattern" in inp:
        return inp["pattern"]
    keys = list(inp.keys())[:3]
    return ", ".join(f"{k}=..." for k in keys)


def _split_complete_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if not text.endswith("\n"):
        lines = lines[:-1]
    return [line for line in lines if line.strip()]
