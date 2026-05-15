from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.gestate.commands import gestate
from fa.task import storage


def test_gestate_empty_input_exits() -> None:
    import typer

    with (
        patch("fa.cli.app_state"),
        patch("fa.gestate.commands._read_stdin", return_value=""),
    ):
        try:
            gestate(arg=None)
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_gestate_task_id_not_found() -> None:
    import typer

    with (
        patch("fa.cli.app_state"),
        patch("fa.gestate.commands._is_task_id", return_value=True),
    ):
        try:
            gestate(arg="99999")
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_gestate_task_id_found_but_invalid() -> None:
    import typer

    with TemporaryDirectory() as tempdir:
        with (
            patch.object(storage, "find_project_root", return_value=Path(tempdir)),
            patch("fa.cli.app_state") as mock_state,
            patch("fa.gestate.commands._is_task_id", return_value=True),
            patch("fa.gestate.commands.find_task") as mock_find,
        ):
            mock_state.logger = MagicMock()
            task = storage.create_task("bad-task")
            mock_find.return_value = task
            try:
                gestate(arg=str(task.id))
            except typer.Exit as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("Expected typer.Exit")


# ─── _format_artifact_diff ─────────────────────────────────────
def test_format_artifact_diff_reports_modified_created_and_deleted_files() -> None:
    from fa.gestate import commands as gestate_commands

    before = {"spec.md": "old\n", "child/plan.md": "remove\n"}
    after = {"spec.md": "new\n", "child/new/plan.md": "add\n"}

    diff = gestate_commands._format_artifact_diff(before, after)

    assert "--- before/spec.md" in diff
    assert "+++ after/spec.md" in diff
    assert "-old" in diff
    assert "+new" in diff
    assert "--- before/child/plan.md" in diff
    assert "+++ after/child/plan.md" in diff
    assert "--- before/child/new/plan.md" in diff


def test_format_artifact_diff_empty_before_and_after() -> None:
    from fa.gestate import commands as gestate_commands

    diff = gestate_commands._format_artifact_diff({}, {})
    assert diff == ""


def test_format_artifact_diff_all_new_files() -> None:
    from fa.gestate import commands as gestate_commands

    before = {}
    after = {"spec.md": "content\n", "plan.md": "plan\n"}

    diff = gestate_commands._format_artifact_diff(before, after)

    assert "+++ after/spec.md" in diff
    assert "+content" in diff
    assert "+++ after/plan.md" in diff
    assert "+plan" in diff


def test_format_artifact_diff_all_deleted_files() -> None:
    from fa.gestate import commands as gestate_commands

    before = {"old.md": "content\n"}
    after = {}

    diff = gestate_commands._format_artifact_diff(before, after)

    assert "--- before/old.md" in diff
    assert "-content" in diff


# ─── _parse_task_reference ─────────────────────────────────────
def test_parse_task_reference_from_fenced_json() -> None:
    from fa.gestate import commands as gestate_commands

    text = """
Created the task:
```json
{ "task_id": 42, "task_path": "/tmp/project/.fa/tasks/42-demo" }
```
"""

    result = gestate_commands._parse_task_reference(text)

    assert result == (42, Path("/tmp/project/.fa/tasks/42-demo"))


def test_parse_task_reference_with_malformed_json() -> None:
    from fa.gestate import commands as gestate_commands

    text = "```json\n{invalid json}\n```"
    result = gestate_commands._parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_non_integer_task_id() -> None:
    from fa.gestate import commands as gestate_commands

    text = '{"task_id": "not-an-int"}'
    result = gestate_commands._parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_missing_task_id() -> None:
    from fa.gestate import commands as gestate_commands

    text = '{"some_field": "value"}'
    result = gestate_commands._parse_task_reference(text)
    assert result is None


def test_parse_task_reference_with_task_path() -> None:
    from fa.gestate import commands as gestate_commands

    text = '{"task_id": 123, "task_path": "/some/path"}'
    result = gestate_commands._parse_task_reference(text)
    assert result == (123, Path("/some/path"))
