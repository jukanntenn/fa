from __future__ import annotations

from unittest.mock import patch

from fa import cli


def test_init_command_creates_fa_dir(capsys, tmp_path) -> None:
    with (
        patch("fa.cli.app_state") as mock_state,
        patch.object(mock_state, "project_root", tmp_path),
        patch(
            "fa.cli.ensure_fa_structure", return_value=tmp_path / ".fa"
        ) as mock_ensure,
    ):
        cli.init()
    mock_ensure.assert_called_once_with(tmp_path)
    output = capsys.readouterr().out
    assert "Initialized" in output


def test_main_invokes_app() -> None:
    with patch.object(cli, "app") as mock_app:
        cli.main()
    mock_app.assert_called_once()
