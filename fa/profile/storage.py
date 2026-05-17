from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from fa.profile.model import PhaseConfig, Profile
from fa.task.storage import fa_dir


@dataclass
class ResolvedPhaseConfig:
    tool: str | None = None
    model: str | None = None
    extra_args: list[str] | None = None
    extra_env: dict[str, str] | None = None


def profiles_dir() -> Path:
    return fa_dir() / "profiles"


def list_profiles() -> list[str]:
    d = profiles_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.toml"))


def load_profile(name: str) -> Profile:
    path = profiles_dir() / f"{name}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"Profile not found: {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    phases: dict[str, PhaseConfig] = {}
    for phase_name, phase_data in raw.get("phases", {}).items():
        phases[phase_name] = PhaseConfig(
            tool=phase_data.get("tool"),
            model=phase_data.get("model"),
            agent=phase_data.get("agent"),
            extra_args=phase_data.get("extra_args", []),
            env=phase_data.get("env", {}),
        )
    return Profile(name=name, phases=phases)


def resolve_profile_phase(
    profile: str | None,
    phase_name: str,
    *,
    fallback_tool: str | None = None,
) -> ResolvedPhaseConfig:
    if profile is None:
        return ResolvedPhaseConfig(tool=fallback_tool)
    p = load_profile(profile)
    cfg = p.phase(phase_name)
    if cfg is None:
        return ResolvedPhaseConfig(tool=fallback_tool)
    return ResolvedPhaseConfig(
        tool=cfg.tool or fallback_tool,
        model=cfg.model,
        extra_args=cfg.extra_args or None,
        extra_env=cfg.env or None,
    )
