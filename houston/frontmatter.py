"""E5 — report front-matter contract + the read and write paths every report
goes through. Nothing reaches reports/ without passing pii_gate.scan first.

`to_markdown` renders a `Report` and `from_markdown` parses one back, so the
rendered shape — the `---` fences, the nested `window`/`observed`/`cost`
blocks, the injected `**Link do Datadog:**` line — is known here and nowhere
else: `split_document` is the only implementation of the `---` rule in the
package, and the write-back functions at the bottom of this module patch
documents on top of it.
Callers that used to split for themselves now get the whole report, body
included, as one typed value (ADR-0033)."""
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from houston.models import Finding
from houston.pii_gate import scan
from houston.report_state import ReportState, check_fix_state, check_state
from houston.report_store import DEFAULT_STORE, ReportStore

# A PII hit is not "nothing happened": the investigation ran and was paid
# for. The full text goes to the gitignored quarantine, and this state is
# what stays in reports/ so dedup stops re-selecting the finding and the
# spend stays visible to metrics (ADR-0015).
QUARANTINED_STATE = ReportState.QUARANTINED.value

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


def _cost_block(cost: Cost) -> dict:
    """The rendered shape of one cost. Two blocks carry it -- the
    investigation's `cost` and the fix agent's `fix_cost` -- and a fix
    attempt is recorded by patching the document, so this is the one place
    that knows the key names and their order."""
    return {
        "input_tokens": cost.input_tokens,
        "output_tokens": cost.output_tokens,
        "cache_read_input_tokens": cost.cache_read_input_tokens,
        "cache_creation_input_tokens": cost.cache_creation_input_tokens,
        "duration_s": cost.duration_s,
        "usd": cost.usd,
        "model": cost.model,
    }


def _cost_from(block: dict | None) -> Cost:
    block = block or {}
    return Cost(
        input_tokens=block.get("input_tokens") or 0,
        output_tokens=block.get("output_tokens") or 0,
        duration_s=block.get("duration_s") or 0.0,
        usd=block.get("usd") or 0.0,
        cache_read_input_tokens=block.get("cache_read_input_tokens") or 0,
        cache_creation_input_tokens=block.get("cache_creation_input_tokens") or 0,
        model=block.get("model"),
    )


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
    # How many `houston fix` runs the numbers below are made of. Without it
    # a retry that fails behind an open PR leaves no trace at all -- the
    # state stands still by design (#34) and the only evidence would be a
    # delta inside an accumulated total. It is also what makes a double
    # write of one run detectable, since nothing on disk identifies a run.
    fix_attempts: int = 0
    # What `houston fix` spent on this finding, kept apart from `cost`
    # (the investigation) because the two runs are billed on different
    # pinned tiers -- sonnet/high for the fix, sonnet/medium for the
    # investigation -- and a dollar figure is uninterpretable without the
    # model that produced it (ADR-0023). None until a fix runs.
    fix_cost: Cost | None = None

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
            # Coerced, not passed through: a `ReportState` member satisfies
            # the `str` annotation and makes `yaml.safe_dump` raise
            # RepresenterError at write time, after the run is paid for.
            "state": str(self.state),
            "cost": _cost_block(self.cost),
            "issue": self.issue,
            "datadog_url": self.datadog_url,
            "fix_pr": self.fix_pr,
            "fix_state": str(self.fix_state) if self.fix_state is not None else None,
        }
        # Conditional, unlike every key above it, because presence is the
        # signal: `metrics.compute` reads `if r.fix_cost` as "a fix ran on
        # this finding". An unconditional zeroed block would report a fix
        # run on all 153 committed reports, 150 of which never had one.
        if self.fix_cost is not None:
            front_matter["fix_attempts"] = self.fix_attempts
            front_matter["fix_cost"] = _cost_block(self.fix_cost)
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
            cost=_cost_from(front_matter.get("cost")),
            issue=front_matter.get("issue"),
            datadog_url=front_matter.get("datadog_url"),
            fix_pr=front_matter.get("fix_pr"),
            fix_state=front_matter.get("fix_state"),
            fix_attempts=front_matter.get("fix_attempts") or 0,
            fix_cost=(
                _cost_from(front_matter["fix_cost"])
                if front_matter.get("fix_cost") else None
            ),
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
    writing nothing meant paying for the same investigation on every run.

    Refuses a state outside the vocabulary before rendering anything: a
    typo used to reach disk, parse back as itself, and become its own row
    in `houston metrics`'s by-state table."""
    check_state(report.state)
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


# ---------------------------------------------------------------------------
# Write-back: the two transitions a human or the fix agent records on a
# report that already exists.
# ---------------------------------------------------------------------------

def _write_document(path: Path, front_matter: dict, body: str) -> None:
    """Writes a document back exactly as `split_document` read it, with the
    front-matter re-serialized and the body untouched.

    Values written this way bypass the gate on the same grounds ADR-0030
    already accepted for `issue`/`state`: a state the CLI chose, a cost the
    CLI parsed from the model runner's envelope. `fix_pr` is the narrower
    case -- `fix_agent._extract_pr_url` regexes it out of the model's own
    stdout, so it is model-influenced text under a tight URL shape, not
    code-constructed the way `issue` is. This does not re-run the PII gate
    over a body that already passed it at write time (ADR-0030's "Bad"
    section records the exception; ADR-0034 notes the `fix_pr` narrowing).

    Patches the document rather than re-rendering the `Report`: every one of
    the 153 committed reports gains keys on a re-render (none carries
    ADR-0023's `cost.model`, 16 predate ADR-0019's `novelty`), so a rewrite
    here would edit reports it was only meant to annotate."""
    yaml_block = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
    # Written beside the target and renamed over it: `write_text` truncates
    # first, and this path now runs on every fix attempt, over a body that
    # was already paid for and exists nowhere else.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(f"---\n{yaml_block}---{body}")
    os.replace(tmp, path)


def record_promotion(path: Path, issue_url: str) -> None:
    """The report now has an issue in the shared backlog."""
    front_matter, body = split_document(path.read_text())
    _write_document(
        path,
        {**front_matter, "issue": issue_url, "state": ReportState.PROMOTED.value},
        body,
    )


def _accumulated(previous: Cost, attempt: Cost) -> Cost:
    """Fix attempts add up. `_branch_name`/`_count_existing_attempts` in
    `fix_agent.py` exist because a finding gets retried (`-v2`, `-v3`), and
    every attempt bills whether or not it ends in a PR -- so the second one
    has to add to what the first spent, not replace it.

    `model` keeps the latest attempt's, which is the one the retry was
    priced on."""
    return Cost(
        input_tokens=previous.input_tokens + attempt.input_tokens,
        output_tokens=previous.output_tokens + attempt.output_tokens,
        duration_s=previous.duration_s + attempt.duration_s,
        usd=previous.usd + attempt.usd,
        cache_read_input_tokens=(
            previous.cache_read_input_tokens + attempt.cache_read_input_tokens
        ),
        cache_creation_input_tokens=(
            previous.cache_creation_input_tokens + attempt.cache_creation_input_tokens
        ),
        model=attempt.model or previous.model,
    )


def record_fix_attempt(
    path: Path, *, pr_url: str | None, state: str, cost: Cost,
) -> None:
    """One `houston fix` attempt, as the report sees it: how many runs it is
    now made of, what they spent, where the finding got to, and the PR if
    this run opened one.

    The rule is #34: an attempt that opened no PR leaves `fix_pr` alone --
    and leaves `fix_state` alone with it, because `incomplete` would
    describe the attempt while the field describes the finding. The untyped
    `update_front_matter(path, fix_pr=None, fix_state="incomplete")` this
    replaces could only say "erase it". The pointer is singular, so a retry
    that *does* open a second PR replaces the URL: the newest PR is the one
    the report points at. `cli.py`'s `notify` posts the previous one to its
    issue when it opened, so it is usually still reachable from there -- but
    that post is a best-effort `gh` call with `check=False`, not a guarantee,
    and the report itself never carries more than the latest URL (ADR-0034).

    Exactly one call per agent run -- `fix_attempts` counts calls, and
    nothing on disk identifies a run, so a second call for the same run
    would bill it twice.

    Reads the document rather than taking one the caller already read: an
    agent run of minutes sits between `fix_report`'s read and this write."""
    check_fix_state(state)
    front_matter, body = split_document(path.read_text())
    recorded_pr = front_matter.get("fix_pr")
    # Built in the order `to_markdown` renders them, so a report that had no
    # fix keys yet comes out of a patch in the same shape as one written
    # from a `Report`.
    fields: dict = {}
    if pr_url:
        fields["fix_pr"] = pr_url
    if pr_url or not recorded_pr:
        fields["fix_state"] = state
    fields["fix_attempts"] = (front_matter.get("fix_attempts") or 0) + 1
    fields["fix_cost"] = _cost_block(
        _accumulated(_cost_from(front_matter.get("fix_cost")), cost)
    )
    _write_document(path, {**front_matter, **fields}, body)
