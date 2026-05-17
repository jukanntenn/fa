from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from fa.profile.commands import profile_app

runner = CliRunner()


def test_list_no_profiles():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("fa.profile.storage.profiles_dir", return_value=Path(tmpdir)):
            result = runner.invoke(profile_app, ["list"])
            assert result.exit_code == 0
            assert "No profiles found" in result.output


def test_list_with_profiles():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        (base / "alpha.toml").write_text("[phases]", encoding="utf-8")
        (base / "beta.toml").write_text("[phases]", encoding="utf-8")
        with patch("fa.profile.storage.profiles_dir", return_value=base):
            result = runner.invoke(profile_app, ["list"])
            assert result.exit_code == 0
            assert "alpha" in result.output
            assert "beta" in result.output


def test_show_existing_profile():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        toml_content = '[phases.nudge]\ntool = "claude"\nmodel = "sonnet"\n'
        (base / "test.toml").write_text(toml_content, encoding="utf-8")
        with patch("fa.profile.storage.profiles_dir", return_value=base):
            result = runner.invoke(profile_app, ["show", "test"])
            assert result.exit_code == 0
            assert "Profile: test" in result.output
            assert "tool = claude" in result.output
            assert "model = sonnet" in result.output


def test_show_missing_profile():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("fa.profile.storage.profiles_dir", return_value=Path(tmpdir)):
            result = runner.invoke(profile_app, ["show", "nonexistent"])
            assert result.exit_code == 1
            assert "Error:" in result.output
