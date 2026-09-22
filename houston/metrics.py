"""E6 — houston metrics. Every number here comes from front-matter; nothing
is typed by hand, same pattern as medprev-qa-agent."""
from dataclasses import dataclass, field

from houston.frontmatter import Report, load_report
from houston.report_store import DEFAULT_STORE, ReportStore

# A report in one of these is work the phase still owes: `new` needs a human
# decision, `incomplete` needs a rerun, `quarantined` needs a human to read
# the quarantined text. `seeded` does not block — it is pre-existing debt
# recorded deliberately (ADR-0010, ADR-0015).
BLOCKING_STATES = ("new", "incomplete", "quarantined")


@dataclass
class Metrics:
    total: int
    by_state: dict[str, int]
    false_positive_rate: float | None  # None when no promoted+discarded yet
    promoted_count: int
    discarded_count: int
    pending_new: int
    pending_incomplete: int
    quarantined_count: int
    input_tokens_p50: float
    input_tokens_p95: float
    duration_s_p50: float
    duration_s_p95: float
    usd_total: float  # investigation spend only -- see fix_usd_total
    usd_mean: float
    usd_p50: float
    usd_p95: float
    with_issue_link: int  # reports carrying an issue URL Houston's promote flow put there
    usd_by_state: dict[str, float] = field(default_factory=dict)
    # `houston fix` bills a second agent run, on its own pinned tier, after
    # the investigation is already paid for. Summed apart from `usd_total`
    # because a per-finding investigation cost that silently included a fix
    # run would stop answering the question this PoC exists to answer
    # (ADR-0001).
    fix_usd_total: float = 0.0
    with_fix_run: int = 0
    # Shadow-mode triage (ADR-0035): what it billed, and how its verdict
    # lines up with the human decision on reports that have one, keyed
    # (decision, state). `noise_on_promoted` is the one cell that decides
    # whether triage may ever skip an investigation: a finding a human
    # filed as an issue that triage would have called noise.
    triaged: int = 0
    triage_usd_total: float = 0.0
    triage_agreement: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def noise_on_promoted(self) -> int:
        return self.triage_agreement.get(("likely_noise", "promoted"), 0)

    @property
    def usd_grand_total(self) -> float:
        return self.usd_total + self.fix_usd_total


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def load_all_reports(store: ReportStore = DEFAULT_STORE) -> list[Report]:
    return [load_report(p) for p in store.iter_paths()]


def compute(reports: list[Report]) -> Metrics:
    by_state: dict[str, int] = {}
    usd_by_state: dict[str, float] = {}
    for r in reports:
        by_state[r.state] = by_state.get(r.state, 0) + 1
        if r.cost.usd:
            usd_by_state[r.state] = usd_by_state.get(r.state, 0.0) + r.cost.usd

    promoted = by_state.get("promoted", 0)
    discarded = by_state.get("discarded", 0)
    decided = promoted + discarded
    fp_rate = (discarded / decided) if decided > 0 else None

    input_tokens = [float(r.cost.input_tokens) for r in reports if r.cost.input_tokens]
    durations = [float(r.cost.duration_s) for r in reports if r.cost.duration_s]
    # Spend is the number this PoC exists to establish (ADR-0001), so it is
    # aggregated here rather than added up by hand from the report files.
    spends = [r.cost.usd for r in reports]
    paid = [v for v in spends if v]
    fix_spends = [r.fix_cost.usd for r in reports if r.fix_cost]
    triaged = [r for r in reports if r.triage]
    agreement: dict[tuple[str, str], int] = {}
    for r in triaged:
        if r.state in ("promoted", "discarded"):
            key = (r.triage.decision, r.state)
            agreement[key] = agreement.get(key, 0) + 1

    return Metrics(
        total=len(reports),
        by_state=by_state,
        false_positive_rate=fp_rate,
        promoted_count=promoted,
        discarded_count=discarded,
        pending_new=by_state.get("new", 0),
        pending_incomplete=by_state.get("incomplete", 0),
        quarantined_count=by_state.get("quarantined", 0),
        input_tokens_p50=_percentile(input_tokens, 0.50),
        input_tokens_p95=_percentile(input_tokens, 0.95),
        duration_s_p50=_percentile(durations, 0.50),
        duration_s_p95=_percentile(durations, 0.95),
        usd_total=sum(spends),
        usd_mean=(sum(paid) / len(paid)) if paid else 0.0,
        usd_p50=_percentile(paid, 0.50),
        usd_p95=_percentile(paid, 0.95),
        with_issue_link=sum(1 for r in reports if r.issue),
        usd_by_state=usd_by_state,
        fix_usd_total=sum(fix_spends),
        with_fix_run=len(fix_spends),
        triaged=len(triaged),
        triage_usd_total=sum(r.triage.usd for r in triaged),
        triage_agreement=agreement,
    )


def can_close_phase(reports: list[Report]) -> tuple[bool, int]:
    """Refuses while any report still owes work: `new` (undecided),
    `incomplete` (the investigation failed) or `quarantined` (the text is
    outside git, unread). Counting only `new` let a phase close on a run
    where every single investigation had timed out — the pending count it
    returns is the blocker."""
    pending = sum(1 for r in reports if r.state in BLOCKING_STATES)
    return pending == 0, pending
