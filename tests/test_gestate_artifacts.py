from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.gestate import commands as gestate_commands


def test_format_artifact_diff_reports_modified_created_and_deleted_files() -> None:
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
    assert "+++ after/child/new/plan.md" in diff


def test_capture_artifact_snapshot_only_reads_specs_and_plans() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        (root / "spec.md").write_text("spec", encoding="utf-8")
        (root / "plan.md").write_text("plan", encoding="utf-8")
        (root / "notes.txt").write_text("notes", encoding="utf-8")
        child = root / "child"
        child.mkdir()
        (child / "plan.md").write_text("child plan", encoding="utf-8")

        snapshot = gestate_commands._capture_artifact_snapshot(root)

    assert set(snapshot) == {"spec.md", "plan.md", "child/plan.md"}


def test_print_round_artifact_diff_reports_no_changes() -> None:
    with patch("fa.gestate.commands.typer.echo") as echo:
        gestate_commands._print_round_artifact_diff(
            2, {"spec.md": "same"}, {"spec.md": "same"}
        )

    echo.assert_called_with("Round 2: no artifact changes")


def test_gestate_failed_tool_run_with_no_changes_prints_no_change_and_converges() -> (
    None
):
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("demo")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer",
                    return_value=None,
                ),
                patch("fa.gestate.commands.typer.echo") as echo,
            ):
                gestate_commands.gestate(
                    str(task.id), tool="codex", max_rounds=1, run=False
                )

    echo.assert_any_call("Round 1: no artifact changes")
    echo.assert_any_call("Converged after 1 round(s)")


def test_gestate_nonzero_tool_run_with_no_changes_prints_no_change_and_converges() -> (
    None
):
    with TemporaryDirectory() as tempdir:
        with patch("fa.task.storage.find_project_root", return_value=Path(tempdir)):
            from fa.task.storage import create_task

            task = create_task("demo")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")

            with (
                patch(
                    "fa.gestate.commands._run_tool_with_optional_viewer", return_value=1
                ),
                patch("fa.gestate.commands.typer.echo") as echo,
            ):
                gestate_commands.gestate(
                    str(task.id), tool="codex", max_rounds=1, run=False
                )

    echo.assert_any_call("Round 1: no artifact changes")
    echo.assert_any_call("Converged after 1 round(s)")


def test_artifact_files_returns_only_spec_and_plan_sorted_by_posix() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        (root / "spec.md").write_text("spec", encoding="utf-8")
        (root / "plan.md").write_text("plan", encoding="utf-8")
        (root / "notes.txt").write_text("ignore", encoding="utf-8")
        child = root / "alpha"
        child.mkdir()
        (child / "spec.md").write_text("child spec", encoding="utf-8")
        child2 = root / "zeta"
        child2.mkdir()
        (child2 / "plan.md").write_text("child plan", encoding="utf-8")

        from fa.gestate.artifacts import _artifact_files

        files = _artifact_files(root)

    relative_names = [f.relative_to(root).as_posix() for f in files]
    assert relative_names == ["alpha/spec.md", "plan.md", "spec.md", "zeta/plan.md"]


def test_artifact_files_ignores_non_target_files() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        (root / "readme.md").write_text("readme", encoding="utf-8")
        (root / "data.json").write_text("{}", encoding="utf-8")

        from fa.gestate.artifacts import _artifact_files

        files = _artifact_files(root)

    assert files == []


def test_format_artifact_diff_returns_empty_for_identical_snapshots() -> None:
    snapshot = {"spec.md": "same content\n", "plan.md": "also same\n"}

    diff = gestate_commands._format_artifact_diff(snapshot, snapshot)

    assert diff == ""


def test_format_artifact_diff_returns_empty_for_both_empty() -> None:
    diff = gestate_commands._format_artifact_diff({}, {})
    assert diff == ""


def test_format_artifact_diff_returns_empty_for_empty_content_change() -> None:
    before: dict[str, str | None] = {"spec.md": None}
    after: dict[str, str | None] = {"spec.md": ""}

    diff = gestate_commands._format_artifact_diff(before, after)

    assert diff == ""


def test_print_round_artifact_diff_prints_changes() -> None:
    before = {"spec.md": "old\n"}
    after = {"spec.md": "new\n"}

    with patch("fa.gestate.commands.typer.echo") as echo:
        gestate_commands._print_round_artifact_diff(3, before, after)

    echo.assert_called_once()
    call_args = echo.call_args[0][0]
    assert "Round 3 artifact diff" in call_args
    assert "--- before/spec.md" in call_args
