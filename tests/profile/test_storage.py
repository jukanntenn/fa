from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fa.profile.storage import list_profiles, load_profile, resolve_profile_phase


@pytest.fixture
def profiles_tmp():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("fa.profile.storage.profiles_dir", return_value=Path(tmpdir)):
            yield Path(tmpdir)


def test_list_profiles_empty(profiles_tmp):
    assert list_profiles() == []


def test_list_profiles_returns_sorted_names(profiles_tmp):
    (profiles_tmp / "beta.toml").write_text("[phases]", encoding="utf-8")
    (profiles_tmp / "alpha.toml").write_text("[phases]", encoding="utf-8")
    (profiles_tmp / "gamma.toml").write_text("[phases]", encoding="utf-8")
    assert list_profiles() == ["alpha", "beta", "gamma"]


def test_load_profile_success(profiles_tmp):
    toml_content = """
[phases.nudge]
tool = "claude"
model = "sonnet"
extra_args = ["--verbose"]
env = { KEY = "VALUE" }

[phases.gestate-create]
tool = "codex"
"""
    (profiles_tmp / "test.toml").write_text(toml_content, encoding="utf-8")
    profile = load_profile("test")
    assert profile.name == "test"
    assert profile.phases["nudge"].tool == "claude"
    assert profile.phases["nudge"].model == "sonnet"
    assert profile.phases["nudge"].extra_args == ["--verbose"]
    assert profile.phases["nudge"].env == {"KEY": "VALUE"}
    assert profile.phases["gestate-create"].tool == "codex"


def test_load_profile_not_found(profiles_tmp):
    with pytest.raises(FileNotFoundError, match="Profile not found"):
        load_profile("nonexistent")


def test_load_profile_invalid_toml(profiles_tmp):
    (profiles_tmp / "bad.toml").write_text("not valid toml {{{{", encoding="utf-8")
    with pytest.raises(Exception):
        load_profile("bad")


def test_load_profile_missing_phases(profiles_tmp):
    (profiles_tmp / "minimal.toml").write_text("", encoding="utf-8")
    profile = load_profile("minimal")
    assert profile.name == "minimal"
    assert profile.phases == {}


def test_load_profile_partial_phase(profiles_tmp):
    (profiles_tmp / "partial.toml").write_text(
        '[phases.nudge]\ntool = "claude"\n', encoding="utf-8"
    )
    profile = load_profile("partial")
    cfg = profile.phase("nudge")
    assert cfg is not None
    assert cfg.tool == "claude"
    assert cfg.model is None
    assert cfg.agent is None
    assert cfg.extra_args == []
    assert cfg.env == {}


def test_resolve_profile_phase_none_profile():
    result = resolve_profile_phase(None, "nudge")
    assert result.tool is None
    assert result.model is None
    assert result.extra_args is None
    assert result.extra_env is None


def test_resolve_profile_phase_none_profile_with_fallback():
    result = resolve_profile_phase(None, "nudge", fallback_tool="claude")
    assert result.tool == "claude"
    assert result.model is None
    assert result.extra_args is None
    assert result.extra_env is None


def test_resolve_profile_phase_phase_found(profiles_tmp):
    (profiles_tmp / "test.toml").write_text(
        '[phases.nudge]\ntool = "claude"\nmodel = "sonnet"\n'
        'extra_args = ["--verbose"]\nenv = { KEY = "VALUE" }\n',
        encoding="utf-8",
    )
    result = resolve_profile_phase("test", "nudge")
    assert result.tool == "claude"
    assert result.model == "sonnet"
    assert result.extra_args == ["--verbose"]
    assert result.extra_env == {"KEY": "VALUE"}


def test_resolve_profile_phase_phase_found_with_fallback(profiles_tmp):
    (profiles_tmp / "test.toml").write_text(
        '[phases.nudge]\nmodel = "sonnet"\n', encoding="utf-8"
    )
    result = resolve_profile_phase("test", "nudge", fallback_tool="codex")
    assert result.tool == "codex"
    assert result.model == "sonnet"


def test_resolve_profile_phase_phase_not_found(profiles_tmp):
    (profiles_tmp / "test.toml").write_text(
        '[phases.other]\ntool = "claude"\n', encoding="utf-8"
    )
    result = resolve_profile_phase("test", "nudge")
    assert result.tool is None
    assert result.model is None
    assert result.extra_args is None
    assert result.extra_env is None


def test_resolve_profile_phase_phase_not_found_with_fallback(profiles_tmp):
    (profiles_tmp / "test.toml").write_text(
        '[phases.other]\ntool = "claude"\n', encoding="utf-8"
    )
    result = resolve_profile_phase("test", "nudge", fallback_tool="codex")
    assert result.tool == "codex"
    assert result.model is None


def test_resolve_profile_phase_profile_not_found(profiles_tmp):
    with pytest.raises(FileNotFoundError, match="Profile not found"):
        resolve_profile_phase("nonexistent", "nudge")


def test_resolve_profile_phase_empty_extra_args_normalized(profiles_tmp):
    (profiles_tmp / "test.toml").write_text(
        '[phases.nudge]\ntool = "claude"\nextra_args = []\n', encoding="utf-8"
    )
    result = resolve_profile_phase("test", "nudge")
    assert result.tool == "claude"
    assert result.extra_args is None
