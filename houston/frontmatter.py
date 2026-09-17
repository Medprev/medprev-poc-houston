"""E5 — report front-matter contract + the read and write paths every report
goes through. Nothing reaches reports/ without passing pii_gate.scan first.

`to_markdown` renders a `Report` and `from_markdown` parses one back, so the
rendered shape — the `---` fences, the nested `window`/`observed`/`cost`
blocks, the injected `**Link do Datadog:**` line — is known here and nowhere
else: `split_document` is the only implementation of the `---` rule in the
package, and `pipeline.update_front_matter` patches documents on top of it.
Callers that used to split for themselves now get the whole report, body
included, as one typed value (ADR-0033)."""
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from houston.models import Finding
from houston.pii_gate import scan
from houston.report_store import DEFAULT_STORE, ReportStore

# A PII hit is not "nothing happened": the investigation ran and was paid
# for. The full text goes to the gitignored quarantine, and this state is
# what stays in reports/ so dedup stops re-selecting the finding and the
# spend stays visible to metrics (ADR-0015).
QUARANTINED_STATE = "quarantined"

# Rendered into the body by `to_markdown` and taken back out by
# `from_markdown`. One literal, so the injection has an inverse: keeping a
# previous one in a parsed body is what duplicated the line on every re-run
# of the backfill script.
LINK_LINE_PREFIX = "**Link do Datadog:**"


@dataclass
class Cost:
    input_tokens: int = 0  # total billed input, cache included
    output_tokens: int = 0
    duration_s: float = 0.0
    usd: float = 0.0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    # Which model was billed. `usd` is meaningless without it: the same
    # investigation costs 2.5x more per token on Opus than on Sonnet, and
    # ADR-0023 had to recover the model from price arithmetic because no
    # report carried it. None only for reports written without an agent
    # run (seeded).
    model: str | None = None


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
                "model": self.cost.model,
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
        link_line = (
            f"{LINK_LINE_PREFIX} {self.datadog_url}\n\n" if self.datadog_url else ""
        )
        return f"---\n{yaml_block}---\n\n{link_line}{self.body}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Report":
        """The inverse of `to_markdown`: one rendered report in, one typed
        `Report` out, body included.

        Total by design. The committed corpus has real drift -- 16 of 153
        reports predate ADR-0019 and carry no `novelty`, and none carries the
        `cost.model` ADR-0023 added -- so an absent key takes the field's
        documented default rather than raising. `to_markdown` is therefore
        not byte-identical on a parsed legacy report: it renders the keys that
        report never had. Patching a report in place has to preserve the
        document instead of re-rendering it.

        `body` comes back stripped, without the injected link line -- the
        inverse of the injection `to_markdown` performs, so a re-render does
        not stack a second copy of it."""
        front_matter, raw_body = split_document(text)
        body = "\n".join(
            line for line in raw_body.strip().splitlines()
            if not line.startswith(LINK_LINE_PREFIX)
        ).strip()
        window = front_matter.get("window") or {}
        observed = front_matter.get("observed") or {}
        cost = front_matter.get("cost") or {}
        return cls(
            fingerprint=front_matter.get("fingerprint", ""),
            source=front_matter.get("source", ""),
            reason=front_matter.get("reason", ""),
            novelty=front_matter.get("novelty", ""),
            service=front_matter.get("service"),
            environment=front_matter.get("environment", "production"),
            window_from_ms=window.get("from") or 0,
            window_to_ms=window.get("to") or 0,
            observed_count=observed.get("count") or 0,
            first_seen_ms=observed.get("first_seen"),
            last_seen_ms=observed.get("last_seen"),
            severity=front_matter.get("severity", ""),
            state=front_matter.get("state", ""),
            body=body,
            cost=Cost(
                input_tokens=cost.get("input_tokens") or 0,
                output_tokens=cost.get("output_tokens") or 0,
                duration_s=cost.get("duration_s") or 0.0,
                usd=cost.get("usd") or 0.0,
                cache_read_input_tokens=cost.get("cache_read_input_tokens") or 0,
                cache_creation_input_tokens=cost.get("cache_creation_input_tokens") or 0,
                model=cost.get("model"),
            ),
            issue=front_matter.get("issue"),
            datadog_url=front_matter.get("datadog_url"),
            fix_pr=front_matter.get("fix_pr"),
            fix_state=front_matter.get("fix_state"),
        )


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


def write_report(report: Report, store: ReportStore = DEFAULT_STORE) -> WriteResult:
    """The only path anything reaches reports/ through. Gates on the full
    rendered markdown (front-matter + body), not the body alone — a stray
    PII in a structured field is still a leak.

    A hit routes the full text to reports/.quarantine/ (gitignored) and
    leaves a redacted, PII-free record in reports/ — see ADR-0015 for why
    writing nothing meant paying for the same investigation on every run."""
    markdown = report.to_markdown()
    hits = scan(markdown)
    if hits:
        path = store.write_quarantined(report.fingerprint, markdown)
        return WriteResult(
            written=False, path=path, pii_hits=hits,
            record_path=_write_quarantine_record(report, hits, store),
        )

    path = store.write(report.fingerprint, markdown)
    return WriteResult(written=True, path=path, pii_hits=[])


def _write_quarantine_record(
    report: Report, hits: list[str], store: ReportStore,
) -> Path | None:
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
        return store.write(candidate.fingerprint, markdown)
    return None


def split_document(text: str) -> tuple[dict, str]:
    """Splits a rendered report into its front-matter mapping and its raw
    body, both exactly as written. The one implementation of the `---` rule.

    `split("---", 2)` stops after two splits, so a `---` inside the body
    stays in the body. Nothing is normalized: this is the document view,
    for callers that must see the keys a file actually carries (or patch it
    without re-rendering). Callers that want the report as a value want
    `Report.from_markdown` instead."""
    _, front_matter_raw, body = text.split("---", 2)
    return yaml.safe_load(front_matter_raw) or {}, body


def load_report(path: Path) -> Report:
    """Reads one report file. The counterpart of `write_report`."""
    return Report.from_markdown(path.read_text())
