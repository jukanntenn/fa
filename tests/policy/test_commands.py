from __future__ import annotations

from unittest.mock import patch

from fa.policy import commands


def test_list_policies_prints_stems(capsys) -> None:
    from pathlib import Path

    mock_files = [Path("/policies/a.yaml"), Path("/policies/b.yaml")]
    with patch("fa.policy.commands.list_policy_files", return_value=mock_files):
        commands.list_policies()
    output = capsys.readouterr().out
    assert "a" in output
    assert "b" in output


def test_run_with_empty_ids_exits(capsys) -> None:
    import typer

    try:
        commands.run([])
    except typer.Exit as exc:
        assert exc.exit_code == 0
    else:
        raise AssertionError("Expected typer.Exit")


def test_run_delegates_to_runner() -> None:
    with (
        patch("fa.cli.app_state") as mock_state,
        patch("fa.policy.commands.run_policies_by_ids", return_value=0) as mock_run,
    ):
        commands.run(["policy-a"], tool="codex", rounds=3, profile=None)
        mock_run.assert_called_once_with(
            mock_state.logger,
            ["policy-a"],
            tool="codex",
            rounds=3,
            model=None,
            extra_args=None,
            extra_env=None,
        )


def test_run_exits_on_nonzero() -> None:
    import typer

    with (
        patch("fa.cli.app_state"),
        patch("fa.policy.commands.run_policies_by_ids", return_value=1),
    ):
        try:
            commands.run(["policy-a"])
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")


def test_run_all_delegates_to_runner() -> None:
    from pathlib import Path

    with (
        patch("fa.cli.app_state") as mock_state,
        patch(
            "fa.policy.commands.list_policy_files",
            return_value=[Path("/policies/x.yaml")],
        ),
        patch("fa.policy.commands.run_policies_by_ids", return_value=0) as mock_run,
    ):
        commands.run_all(tool="claude", rounds=5, profile=None)
        mock_run.assert_called_once_with(
            mock_state.logger,
            ["x"],
            tool="claude",
            rounds=5,
            model=None,
            extra_args=None,
            extra_env=None,
        )


def test_run_all_exits_on_nonzero() -> None:
    from pathlib import Path

    import typer

    with (
        patch("fa.cli.app_state"),
        patch(
            "fa.policy.commands.list_policy_files",
            return_value=[Path("/policies/x.yaml")],
        ),
        patch("fa.policy.commands.run_policies_by_ids", return_value=1),
    ):
        try:
            commands.run_all()
        except typer.Exit as exc:
            assert exc.exit_code == 1
        else:
            raise AssertionError("Expected typer.Exit")
