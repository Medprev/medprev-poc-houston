"""E5 — report front-matter contract + the write path every report goes
through. Nothing reaches reports/ without passing pii_gate.scan first."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from houston.dedup import REPORTS_DIR
from houston.models import Finding
from houston.pii_gate import scan

QUARANTINE_DIR = REPORTS_DIR / ".quarantine"


@dataclass
class Cost:
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    usd: float = 0.0


@dataclass
class Report:
    fingerprint: str
    source: str
    reason: str  # "new" | "regression" | "seeded"
    service: str | None
    environment: str
    window_from_ms: int
    window_to_ms: int
    observed_count: int
    first_seen_ms: int | None
    last_seen_ms: int | None
    severity: str
    state: str  # "new" | "promoted" | "discarded" | "seeded" | "incomplete"
    body: str
    cost: Cost = field(default_factory=Cost)
    issue: str | None = None

    @classmethod
    def from_finding(cls, finding: Finding, environment: str = "production",
                      state: str = "new", body: str = "") -> "Report":
        return cls(
            fingerprint=finding.fingerprint,
            source=finding.source,
            reason="regression" if finding.regressed else "new",
            service=finding.service,
            environment=environment,
            window_from_ms=0,
            window_to_ms=0,
            observed_count=finding.observed_count,
            first_seen_ms=finding.first_seen_ms,
            last_seen_ms=finding.last_seen_ms,
            severity=finding.severity,
            state=state,
            body=body,
        )

    def to_markdown(self) -> str:
        front_matter = {
            "fingerprint": self.fingerprint,
            "source": self.source,
            "reason": self.reason,
            "service": self.service,
            "environment": self.environment,
            "window": {"from": self.window_from_ms, "to": self.window_to_ms},
            "observed": {
                "count": self.observed_count,
                "first_seen": self.first_seen_ms,
                "last_seen": self.last_seen_ms,
            },
            "severity": self.severity,
            "state": self.state,
            "cost": {
                "input_tokens": self.cost.input_tokens,
                "output_tokens": self.cost.output_tokens,
                "duration_s": self.cost.duration_s,
                "usd": self.cost.usd,
            },
            "issue": self.issue,
        }
        yaml_block = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_block}---\n\n{self.body}\n"


@dataclass
class WriteResult:
    written: bool
    path: Path
    pii_hits: list[str]


def write_report(report: Report) -> WriteResult:
    """The only path anything reaches reports/ through. Gates on the full
    rendered markdown (front-matter + body), not the body alone — a stray
    PII in a structured field is still a leak."""
    markdown = report.to_markdown()
    hits = scan(markdown)
    if hits:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        path = QUARANTINE_DIR / f"{report.fingerprint}.md"
        path.write_text(markdown)
        return WriteResult(written=False, path=path, pii_hits=hits)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report.fingerprint}.md"
    path.write_text(markdown)
    return WriteResult(written=True, path=path, pii_hits=[])


def read_report(path: Path) -> dict:
    text = path.read_text()
    _, front_matter_raw, _ = text.split("---", 2)
    return yaml.safe_load(front_matter_raw)
