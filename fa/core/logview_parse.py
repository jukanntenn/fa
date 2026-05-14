from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("fa")

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"

_STREAM_JSON_TOOLS = {"claude", "ccr"}
_LIVE_VIEWER_TOOLS = {"claude", "ccr", "codex"}


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


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _update_sgr_depth(params: str, depth: list[int]) -> None:
    codes = params.split(";") if params else ["0"]
    i = 0
    while i < len(codes):
        code = codes[i] or "0"
        if code == "0":
            depth[0] = 0
        elif code in {
            "22",
            "23",
            "24",
            "25",
            "27",
            "28",
            "29",
            "39",
            "49",
        }:
            depth[0] = max(0, depth[0] - 1)
        elif code in {"38", "48"}:
            if i + 1 < len(codes) and codes[i + 1] == "5":
                i += 2
            elif i + 1 < len(codes) and codes[i + 1] == "2":
                i += 4
            depth[0] += 1
        else:
            depth[0] += 1
        i += 1


def _truncate_to_visible(line: str, max_cols: int) -> str:
    if max_cols <= 0:
        return ""
    result: list[str] = []
    visible = 0
    i = 0
    sgr_depth = [0]
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
                _update_sgr_depth(seq[2:-1], sgr_depth)
            i = j + 1
            continue
        result.append(ch)
        visible += 1
        i += 1
    text = "".join(result)
    if sgr_depth[0]:
        text += _RESET
    return text


def parse_jsonl_line(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Failed to parse JSONL line: %s", raw[:500])
        return f"{_DIM}[raw] {_truncate(raw)}{_RESET}"
    msg_type = obj.get("type")
    if msg_type == "system":
        return None
    if msg_type == "result":
        return _format_result(obj)
    if msg_type == "assistant":
        return _format_assistant(obj)
    if msg_type == "user":
        return _format_user(obj)
    return f"{_DIM}[unknown: {msg_type}]{_RESET}"


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
    return f"{_DIM}[tool result]{_RESET}\n{_truncate(str(content), 2000, preserve_newlines=True)}"


def _format_assistant(obj: dict) -> str | None:
    message = obj.get("message", {})
    contents = message.get("content", [])
    if not contents:
        return None
    parts: list[str] = []
    for item in contents:
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text", "")
            if text.strip():
                parts.append(_truncate(text, 4000, preserve_newlines=True))
        elif item_type == "tool_use":
            name = item.get("name", "unknown")
            inp = item.get("input", {})
            summary = _tool_input_summary(name, inp)
            parts.append(f"{_BOLD}{_CYAN}[tool: {name}]{_RESET} {summary}")
        elif item_type == "thinking":
            thinking = item.get("thinking", "")
            if thinking.strip():
                parts.append(f"{_DIM}[thinking...] {_truncate(thinking, 100)}{_RESET}")
        elif item_type == "tool_result":
            parts.append(_format_tool_result(item))
    return "\n".join(parts) if parts else None


def _format_user(obj: dict) -> str | None:
    message = obj.get("message", {})
    contents = message.get("content", [])
    if not contents:
        return None
    parts: list[str] = []
    for item in contents:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            parts.append(_format_tool_result(item))
    return "\n".join(parts) if parts else None


def _format_result(obj: dict) -> str:
    subtype = obj.get("subtype", "unknown")
    duration_ms = obj.get("duration_ms")
    result_text = obj.get("result", "")
    duration_str = ""
    if duration_ms is not None:
        duration_str = f" in {duration_ms / 1000:.1f}s"
    result = str(result_text).strip()
    if subtype == "success":
        return f"{_BOLD}{_GREEN}[completed{duration_str}]{_RESET}\n{result}"
    return f"{_BOLD}{_RED}[failed{duration_str}]{_RESET}\n{result}"


def parse_codex_line(line: str, state: dict[str, str] | None = None) -> str | None:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped:
        return None
    if state is None:
        state = {}
    if stripped == "user":
        state["section"] = "user"
        state.pop("exec_command_seen", None)
        state.pop("exec_output_seen", None)
        return None
    if stripped == "codex":
        state["section"] = "codex"
        if state.get("exec_output_seen") == "1":
            state.pop("exec_command_seen", None)
            state.pop("exec_output_seen", None)
        return None
    if stripped == "exec":
        state["section"] = "exec"
        state.pop("exec_command_seen", None)
        state.pop("exec_output_seen", None)
        return None
    if stripped.startswith("OpenAI Codex "):
        state["section"] = "metadata"
        state.pop("exec_command_seen", None)
        state.pop("exec_output_seen", None)
        if state.get("codex_header_seen") == "1":
            return None
        state["codex_header_seen"] = "1"
        return f"{_DIM}[codex] {_truncate(stripped, 160)}{_RESET}"
    if stripped == "--------":
        return None
    if state.get("exec_command_seen") == "1" and raw.startswith(" "):
        lowered = stripped.lower()
        state["exec_output_seen"] = "1"
        if stripped.startswith("succeeded in "):
            return f"{_BOLD}{_GREEN}[exec succeeded] {_truncate(stripped, 160)}{_RESET}"
        if "failed" in lowered or "error" in lowered or "timed out" in lowered:
            return f"{_BOLD}{_RED}[exec failed] {_truncate(stripped, 200)}{_RESET}"
        return _truncate(raw, 4000, preserve_newlines=True)
    if state.get("exec_output_seen") == "1":
        return _truncate(raw, 4000, preserve_newlines=True)

    section = state.get("section", "metadata")
    lowered = stripped.lower()
    if section in {"metadata", "user"} and (
        "api error" in lowered
        or "error:" in lowered
        or lowered.startswith("failed")
        or "timed out" in lowered
    ):
        return f"{_BOLD}{_RED}[codex error]{_RESET} {_truncate(stripped, 4000, preserve_newlines=True)}"
    if section == "user":
        return None
    if section == "metadata" and ":" in stripped:
        metadata_prefixes = (
            "workdir:",
            "model:",
            "provider:",
            "approval:",
            "sandbox:",
            "reasoning effort:",
            "reasoning summaries:",
            "session id:",
        )
        if lowered.startswith(metadata_prefixes):
            return None
    if section == "exec":
        if state.get("exec_command_seen") != "1":
            state["exec_command_seen"] = "1"
            state.pop("exec_output_seen", None)
            return f"{_BOLD}{_CYAN}[tool: exec]{_RESET} {_truncate(stripped, 220)}"
        return _truncate(raw, 4000, preserve_newlines=True)
    if section == "codex":
        return f"{_BOLD}{_CYAN}[codex]{_RESET} {_truncate(stripped, 4000, preserve_newlines=True)}"
    return None


def _tool_input_summary(name: str, inp: dict) -> str:
    if name == "Read" and "file_path" in inp:
        return inp["file_path"]
    if name == "Edit" and "file_path" in inp:
        old = _truncate(inp.get("old_string", ""), 60)
        return f"{inp['file_path']}: {old}"
    if name == "Write" and "file_path" in inp:
        return inp["file_path"]
    if name == "Bash" and "command" in inp:
        return _truncate(inp["command"], 100)
    if name == "Grep" and "pattern" in inp:
        return inp["pattern"]
    if name == "Glob" and "pattern" in inp:
        return inp["pattern"]
    keys = list(inp.keys())[:3]
    return ", ".join(f"{k}=..." for k in keys)
