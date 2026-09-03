"""E5 — report front-matter contract + the write path every report goes
through. Nothing reaches reports/ without passing pii_gate.scan first."""
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from houston.dedup import REPORTS_DIR
from houston.models import Finding
from houston.pii_gate import scan

QUARANTINE_DIR = REPORTS_DIR / ".quarantine"

# A PII hit is not "nothing happened": the investigation ran and was paid
# for. The full text goes to the gitignored quarantine, and this state is
# what stays in reports/ so dedup stops re-selecting the finding and the
# spend stays visible to metrics (ADR-0015).
QUARANTINED_STATE = "quarantined"


@dataclass
class Cost:
    input_tokens: int = 0  # total billed input, cache included
    output_tokens: int = 0
    duration_s: float = 0.0
    usd: float = 0.0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Report:
    fingerprint: str
    source: str
    reason: str  # the diagnostic label: error_type, monitor name, k8s Reason
    novelty: str  # "new" | "regression" — whether the window is the first sighting
    service: str | None
    environment: str
    window_from_ms: int
    window_to_ms: int
    observed_count: int
    first_seen_ms: int | None
    last_seen_ms: int | None
    severity: str
    state: str  # "new" | "promoted" | "discarded" | "seeded" | "incomplete" | "quarantined"
    body: str
    cost: Cost = field(default_factory=Cost)
    issue: str | None = None
    datadog_url: str | None = None
    fix_pr: str | None = None
    fix_state: str | None = None  # "attempted" | "pr_open" | "merged" | "rejected" | "incomplete"

    @classmethod
    def from_finding(cls, finding: Finding, environment: str = "production",
                      state: str = "new", body: str = "") -> "Report":
        return cls(
            fingerprint=finding.fingerprint,
            source=finding.source,
            reason=finding.reason,
            novelty="regression" if finding.regressed else "new",
            service=finding.service,
            environment=environment,
            window_from_ms=finding.window_from_ms,
            window_to_ms=finding.window_to_ms,
            observed_count=finding.observed_count,
            first_seen_ms=finding.first_seen_ms,
            last_seen_ms=finding.last_seen_ms,
            severity=finding.severity,
            state=state,
            body=body,
            datadog_url=finding.datadog_url,
        )

    def to_markdown(self) -> str:
        front_matter = {
            "fingerprint": self.fingerprint,
            "source": self.source,
            "reason": self.reason,
            "novelty": self.novelty,
            "service": self.service,
            "environment": self.environment,
            "window": {"from": self.window_from_ms, "to": self.window_to_ms},
            "observed": {
                "count": self.observed_count,  # within window, not cumulative
                "first_seen": self.first_seen_ms,
                "last_seen": self.last_seen_ms,
            },
            "severity": self.severity,
            "state": self.state,
            "cost": {
                "input_tokens": self.cost.input_tokens,
                "output_tokens": self.cost.output_tokens,
                "cache_read_input_tokens": self.cost.cache_read_input_tokens,
                "cache_creation_input_tokens": self.cost.cache_creation_input_tokens,
                "duration_s": self.cost.duration_s,
                "usd": self.cost.usd,
            },
            "issue": self.issue,
            "datadog_url": self.datadog_url,
            "fix_pr": self.fix_pr,
            "fix_state": self.fix_state,
        }
        yaml_block = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
        # Injected here, not asked from the model: this is the authoritative
        # URL the collector already computed, not something the agent should
        # construct or guess at investigation time.
        link_line = f"**Link do Datadog:** {self.datadog_url}\n\n" if self.datadog_url else ""
        return f"---\n{yaml_block}---\n\n{link_line}{self.body}\n"


@dataclass
class WriteResult:
    written: bool
    path: Path
    pii_hits: list[str]
    record_path: Path | None = None  # the reports/ stub left behind on a PII hit


def _quarantine_record(report: Report, hits: list[str]) -> Report:
    body = (
        f"Investigação concluída, relatório retido pelo gate de PII "
        f"({', '.join(hits)}) sobre o arquivo renderizado. O texto completo "
        f"ficou em reports/.quarantine/{report.fingerprint}.md, fora do git.\n\n"
        "Este registro existe para dois motivos: a dedup para de reselecionar "
        "o achado (que já foi investigado e pago), e o custo continua "
        "contabilizado em `houston metrics`.\n\n"
        "Para retomar: leia o arquivo em quarentena, decida se o achado virou "
        "issue (`state: promoted`) ou não (`state: discarded`), ou apague este "
        "registro para que o achado volte à fila de investigação."
    )
    return replace(report, state=QUARANTINED_STATE, body=body)


def write_report(report: Report) -> WriteResult:
    """The only path anything reaches reports/ through. Gates on the full
    rendered markdown (front-matter + body), not the body alone — a stray
    PII in a structured field is still a leak.

    A hit routes the full text to reports/.quarantine/ (gitignored) and
    leaves a redacted, PII-free record in reports/ — see ADR-0015 for why
    writing nothing meant paying for the same investigation on every run."""
    markdown = report.to_markdown()
    hits = scan(markdown)
    if hits:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        path = QUARANTINE_DIR / f"{report.fingerprint}.md"
        path.write_text(markdown)
        return WriteResult(
            written=False, path=path, pii_hits=hits,
            record_path=_write_quarantine_record(report, hits),
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report.fingerprint}.md"
    path.write_text(markdown)
    return WriteResult(written=True, path=path, pii_hits=[])


def _write_quarantine_record(report: Report, hits: list[str]) -> Path | None:
    """Writes the redacted stub, itself gated. If even the stub's structured
    fields trip the gate, they are the leak: drop them and keep only what
    dedup and metrics need. If that still trips, nothing is written and the
    caller sees record_path=None."""
    for candidate in (
        _quarantine_record(report, hits),
        replace(
            _quarantine_record(report, hits),
            service=None, reason="redacted", datadog_url=None,
        ),
    ):
        markdown = candidate.to_markdown()
        if scan(markdown):
            continue
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"{candidate.fingerprint}.md"
        path.write_text(markdown)
        return path
    return None


def read_report(path: Path) -> dict:
    text = path.read_text()
    _, front_matter_raw, _ = text.split("---", 2)
    return yaml.safe_load(front_matter_raw)
