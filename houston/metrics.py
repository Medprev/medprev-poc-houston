"""E6 — houston metrics. Every number here comes from front-matter; nothing
is typed by hand, same pattern as medprev-qa-agent."""
from dataclasses import dataclass, field
from pathlib import Path

from houston.dedup import REPORTS_DIR
from houston.frontmatter import read_report

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
    usd_total: float
    usd_mean: float
    usd_p50: float
    usd_p95: float
    with_issue_link: int  # reports carrying an issue URL Houston's promote flow put there
    usd_by_state: dict[str, float] = field(default_factory=dict)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def load_all_reports(reports_dir: Path | None = None) -> list[dict]:
    directory = reports_dir or REPORTS_DIR
    if not directory.exists():
        return []
    return [
        read_report(p)
        for p in sorted(directory.glob("*.md"))
        if p.parent.name != ".quarantine"
    ]


def _cost(report: dict) -> dict:
    return report.get("cost") or {}


def compute(reports: list[dict]) -> Metrics:
    by_state: dict[str, int] = {}
    usd_by_state: dict[str, float] = {}
    for r in reports:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        spent = float(_cost(r).get("usd") or 0.0)
        if spent:
            usd_by_state[r["state"]] = usd_by_state.get(r["state"], 0.0) + spent

    promoted = by_state.get("promoted", 0)
    discarded = by_state.get("discarded", 0)
    decided = promoted + discarded
    fp_rate = (discarded / decided) if decided > 0 else None

    input_tokens = [_cost(r).get("input_tokens") for r in reports]
    input_tokens = [float(v) for v in input_tokens if v]
    durations = [_cost(r).get("duration_s") for r in reports]
    durations = [float(v) for v in durations if v]
    # Spend is the number this PoC exists to establish (ADR-0001), so it is
    # aggregated here rather than added up by hand from the report files.
    spends = [float(_cost(r).get("usd") or 0.0) for r in reports]
    paid = [v for v in spends if v]

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
        with_issue_link=sum(1 for r in reports if r.get("issue")),
        usd_by_state=usd_by_state,
    )


def can_close_phase(reports: list[dict]) -> tuple[bool, int]:
    """Refuses while any report still owes work: `new` (undecided),
    `incomplete` (the investigation failed) or `quarantined` (the text is
    outside git, unread). Counting only `new` let a phase close on a run
    where every single investigation had timed out — the pending count it
    returns is the blocker."""
    pending = sum(1 for r in reports if r["state"] in BLOCKING_STATES)
    return pending == 0, pending
