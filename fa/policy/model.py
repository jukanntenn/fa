from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyReport:
    path: str
    template: str


@dataclass
class PolicyScopes:
    required: list[str]
    exclude: list[str]


@dataclass
class Policy:
    id: str
    name: str
    description: str
    objective: str
    specs: list[str]
    scopes: PolicyScopes
    report: PolicyReport
    agent: str = "rectifier"

    @classmethod
    def from_dict(cls, data: dict, fallback_id: str) -> "Policy":
        scopes = data.get("scopes", {})
        report = data.get("report", {})
        return cls(
            id=str(data.get("id", fallback_id)),
            name=str(data.get("name", fallback_id)),
            description=str(data.get("description", "")),
            objective=str(data.get("objective", "")),
            specs=list(data.get("specs") or []),
            scopes=PolicyScopes(
                required=list(scopes.get("required") or []),
                exclude=list(scopes.get("exclude") or []),
            ),
            report=PolicyReport(
                path=str(
                    report.get(
                        "path",
                        ".fa/reports/{{ policy.id }}/{{ date }}_{{ time }}/round-{{ round }}.md",
                    )
                ),
                template=str(report.get("template", "")),
            ),
            agent=str(data.get("agent", "rectifier")),
        )
