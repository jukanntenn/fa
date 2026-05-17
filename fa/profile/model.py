from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PhaseConfig:
    tool: str | None = None
    model: str | None = None
    agent: str | None = None
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Profile:
    name: str
    phases: dict[str, PhaseConfig]

    def phase(self, phase_name: str) -> PhaseConfig | None:
        return self.phases.get(phase_name)
