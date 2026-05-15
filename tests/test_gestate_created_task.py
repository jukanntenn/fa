import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.gestate import commands as gestate_commands


def test_parse_task_reference_from_fenced_json() -> None:
    text = """
Created the task:
```json
{ "task_id": 42, "task_path": "/tmp/project/.fa/tasks/42-demo" }
```
"""

    result = gestate_commands._parse_task_reference(text)

    assert result == (42, Path("/tmp/project/.fa/tasks/42-demo"))


def test_parse_task_reference_from_plain_json() -> None:
    text = 'done { "task_id": 7, "task_path": "/tmp/project/.fa/tasks/7-demo" }'

    result = gestate_commands._parse_task_reference(text)

    assert result == (7, Path("/tmp/project/.fa/tasks/7-demo"))


def test_parse_task_reference_ignores_invalid_json() -> None:
    text = '```json\n{ "task_path": "/tmp/project/.fa/tasks/demo" }\n```'

    result = gestate_commands._parse_task_reference(text)

    assert result is None


def test_parse_task_reference_with_string_task_id_is_ignored() -> None:
    text = '```json\n{ "task_id": "42", "task_path": "/tmp/project/.fa/tasks/42-demo" }\n```'

    result = gestate_commands._parse_task_reference(text)

    assert result is None


def test_parse_task_reference_without_task_path_returns_none_path() -> None:
    text = '```json\n{ "task_id": 42 }\n```'

    result = gestate_commands._parse_task_reference(text)

    assert result == (42, None)


def test_parse_task_reference_ignores_non_dict_json() -> None:
    text = "```json\n[1, 2, 3]\n```"

    result = gestate_commands._parse_task_reference(text)

    assert result is None


def test_find_created_task_prefers_agent_returned_json_over_lowest_new_task() -> None:
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import all_tasks, create_task

            preexisting_ids = frozenset(all_tasks().keys())
            wrong_low_id = create_task("wrong-low-id")
            right_parent = create_task("right-parent")
            log_path = Path(tempdir) / "create.log"
            log_path.write_text(
                json.dumps(
                    {
                        "type": "result",
                        "result": json.dumps(
                            {
                                "task_id": right_parent.id,
                                "task_path": str(right_parent.path),
                            }
                        ),
                    }
                ),
                encoding="utf-8",
            )

            result = gestate_commands._find_created_task(
                preexisting_ids, log_path, "claude"
            )

    assert result is not None
    assert result.id == right_parent.id
    assert result.id != wrong_low_id.id


def test_find_created_task_falls_back_when_returned_task_is_invalid() -> None:
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import all_tasks, create_task

            preexisting_ids = frozenset(all_tasks().keys())
            fallback = create_task("fallback")
            create_task("other")
            log_path = Path(tempdir) / "create.log"
            log_path.write_text(
                json.dumps(
                    {
                        "type": "result",
                        "result": json.dumps(
                            {"task_id": 999, "task_path": "/tmp/missing"}
                        ),
                    }
                ),
                encoding="utf-8",
            )

            result = gestate_commands._find_created_task(
                preexisting_ids, log_path, "claude"
            )

    assert result is not None
    assert result.id == fallback.id


def test_extract_text_from_create_log_parses_ccr_jsonl() -> None:
    with TemporaryDirectory() as tempdir:
        log_path = Path(tempdir) / "create.log"
        log_path.write_text(
            "not json\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "assistant text"},
                            {"type": "tool_use", "name": "ignore"},
                        ]
                    },
                }
            )
            + "\n"
            + json.dumps({"type": "result", "result": "result text"}),
            encoding="utf-8",
        )

        text = gestate_commands._extract_text_from_create_log(log_path, "ccr")

    assert text == "assistant text\nresult text"


def test_gestate_create_writes_prompt_file_and_passes_path() -> None:
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            def fake_run(**kwargs: object) -> int:
                task = create_task("created")
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                return 0

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer",
                    side_effect=fake_run,
                ) as run_tool,
                patch("fa.gestate.commands._run_runnable_task_tree", return_value=0),
            ):
                gestate_commands.gestate(
                    "line 1\nline 2", tool="codex", max_rounds=1, run=False
                )

            create_call = run_tool.call_args_list[0]
            prompt_path = create_call.kwargs["prompt_path"]

            assert create_call.kwargs["prompt"] == "/gestating line 1\nline 2"
            assert prompt_path.name[-10:] == "-prompt.md"
            assert prompt_path.name.startswith("gestate-create-")
            assert (
                prompt_path.read_text(encoding="utf-8") == "/gestating line 1\nline 2"
            )


def test_gestate_review_passes_prompt_path_to_tool_runner() -> None:
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with patch(
                "fa.gestate.commands._run_tool_with_optional_viewer", return_value=0
            ) as run_tool:
                gestate_commands.gestate(
                    str(task.id), tool="codex", max_rounds=1, run=False
                )

            review_call = run_tool.call_args_list[0]
            prompt_path = review_call.kwargs["prompt_path"]

            assert prompt_path.name == "round-1-prompt.md"
            assert (
                prompt_path.read_text(encoding="utf-8") == review_call.kwargs["prompt"]
            )
