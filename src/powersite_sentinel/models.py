"""Small domain models used by Sentinel's rules and API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: Severity
    title: str
    summary: str
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        discriminator = self.evidence.get("path") or self.evidence.get("controller_uid") or "site"
        return f"{self.code}:{discriminator}"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "fingerprint": self.fingerprint,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class Score:
    name: str
    value: int
    status: str
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status,
            "explanation": self.explanation,
        }
