from __future__ import annotations

import json
from pathlib import Path

from fa.gestate.tasks import _extract_text_from_create_log


def test_extract_text_handles_oserror():
    log_path = Path("/nonexistent/path/log.txt")
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""


def test_extract_text_non_claude_tool_returns_raw_text(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text("raw text content\nmore content", encoding="utf-8")
    result = _extract_text_from_create_log(log_path, "codex")
    assert result == "raw text content\nmore content"


def test_extract_text_with_result_type(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text(
        json.dumps({"type": "result", "result": "task done"}), encoding="utf-8"
    )
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == "task done"


def test_extract_text_with_assistant_message(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hello from assistant"}]
                },
            }
        ),
        encoding="utf-8",
    )
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == "hello from assistant"


def test_extract_text_skips_invalid_json_lines(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text("not valid json\n", encoding="utf-8")
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""


def test_extract_text_skips_non_dict_objects(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text("null\n", encoding="utf-8")
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""


def test_extract_text_skips_message_without_dict(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text(
        json.dumps({"type": "assistant", "message": "not a dict"}), encoding="utf-8"
    )
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""


def test_extract_text_skips_content_without_list(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text(
        json.dumps({"type": "assistant", "message": {"content": "not a list"}}),
        encoding="utf-8",
    )
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""


def test_extract_text_skips_unknown_message_type(tmp_path):
    log_path = tmp_path / "log.txt"
    log_path.write_text(
        json.dumps({"type": "user", "content": "hello"}), encoding="utf-8"
    )
    result = _extract_text_from_create_log(log_path, "claude")
    assert result == ""
