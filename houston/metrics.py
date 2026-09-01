"""E6 — houston metrics. Every number here comes from front-matter; nothing
is typed by hand, same pattern as medprev-qa-agent."""
from dataclasses import dataclass
from pathlib import Path

from houston.dedup import REPORTS_DIR
from houston.frontmatter import read_report


@dataclass
class Metrics:
    total: int
    by_state: dict[str, int]
    false_positive_rate: float | None  # None when no promoted+discarded yet
    promoted_count: int
    discarded_count: int
    pending_new: int
    input_tokens_p50: float
    input_tokens_p95: float
    duration_s_p50: float
    duration_s_p95: float
    already_had_issue: int


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


def compute(reports: list[dict]) -> Metrics:
    by_state: dict[str, int] = {}
    for r in reports:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1

    promoted = by_state.get("promoted", 0)
    discarded = by_state.get("discarded", 0)
    decided = promoted + discarded
    fp_rate = (discarded / decided) if decided > 0 else None

    input_tokens = [r["cost"]["input_tokens"] for r in reports if r["cost"]["input_tokens"]]
    durations = [r["cost"]["duration_s"] for r in reports if r["cost"]["duration_s"]]

    return Metrics(
        total=len(reports),
        by_state=by_state,
        false_positive_rate=fp_rate,
        promoted_count=promoted,
        discarded_count=discarded,
        pending_new=by_state.get("new", 0),
        input_tokens_p50=_percentile(input_tokens, 0.50),
        input_tokens_p95=_percentile(input_tokens, 0.95),
        duration_s_p50=_percentile(durations, 0.50),
        duration_s_p95=_percentile(durations, 0.95),
        already_had_issue=sum(1 for r in reports if r.get("issue")),
    )


def can_close_phase(reports: list[dict]) -> tuple[bool, int]:
    """houston metrics refuses to close the phase while any report is
    state: new — the pending count it returns is the blocker."""
    pending = sum(1 for r in reports if r["state"] == "new")
    return pending == 0, pending
