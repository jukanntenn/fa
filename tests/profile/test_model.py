from __future__ import annotations

from fa.profile.model import PhaseConfig, Profile


def test_phase_config_defaults():
    cfg = PhaseConfig()
    assert cfg.tool is None
    assert cfg.model is None
    assert cfg.agent is None
    assert cfg.extra_args == []
    assert cfg.env == {}


def test_phase_config_with_values():
    cfg = PhaseConfig(
        tool="claude", model="sonnet", extra_args=["--foo"], env={"K": "V"}
    )
    assert cfg.tool == "claude"
    assert cfg.model == "sonnet"
    assert cfg.extra_args == ["--foo"]
    assert cfg.env == {"K": "V"}


def test_profile_construction():
    phases = {"nudge": PhaseConfig(tool="claude")}
    profile = Profile(name="test", phases=phases)
    assert profile.name == "test"
    assert "nudge" in profile.phases


def test_profile_phase_returns_config():
    phases = {"nudge": PhaseConfig(tool="claude", model="sonnet")}
    profile = Profile(name="test", phases=phases)
    result = profile.phase("nudge")
    assert result is not None
    assert result.tool == "claude"
    assert result.model == "sonnet"


def test_profile_phase_returns_none_for_missing():
    profile = Profile(name="test", phases={})
    assert profile.phase("nonexistent") is None


def test_profile_empty_phases():
    profile = Profile(name="empty", phases={})
    assert profile.phases == {}
    assert profile.phase("anything") is None
