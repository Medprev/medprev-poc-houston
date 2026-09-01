"""E3 — dedup, seed, cap. reports/{fingerprint}.md existing means already
handled; that is the entire dedup mechanism, no separate index needed."""
from pathlib import Path

from houston.models import Finding

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def report_path(fingerprint: str) -> Path:
    return REPORTS_DIR / f"{fingerprint}.md"


def already_reported(fingerprint: str) -> bool:
    return report_path(fingerprint).exists()


def filter_new(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if not already_reported(f.fingerprint)]


# States that mean "no real investigation happened yet" -- a report in one
# of these still needs its evidence/root-cause/timeline generated. `new`
# (already investigated, pending a human decision), `promoted`, and
# `discarded` are excluded on purpose: re-investigating those would
# overwrite a human decision or a completed investigation.
NEEDS_INVESTIGATION_STATES = {"seeded", "incomplete"}


def filter_needing_investigation(findings: list[Finding]) -> list[Finding]:
    """Unlike filter_new, a finding is NOT excluded just because
    reports/{fingerprint}.md exists -- `houston seed` deliberately writes a
    report with no real investigation (state: seeded), and dedup treating
    "has a file" as "done forever" meant seeded findings could never get
    real evidence/cause/timeline through `houston investigate`. This is
    what `houston run`/`houston investigate` should use; `houston seed`
    keeps using `filter_new` (existence-only), since seeding must never
    overwrite an already-decided or already-investigated report."""
    from houston.frontmatter import (
        read_report,  # deferred: frontmatter imports REPORTS_DIR from this module
    )

    result = []
    for finding in findings:
        path = report_path(finding.fingerprint)
        if not path.exists():
            result.append(finding)
            continue
        state = read_report(path).get("state")
        if state in NEEDS_INVESTIGATION_STATES:
            result.append(finding)
    return result


def cap(findings: list[Finding], max_findings: int = 15) -> tuple[list[Finding], int]:
    """Caps by descending observed volume. Returns (kept, dropped_count)."""
    ordered = sorted(findings, key=lambda f: f.observed_count, reverse=True)
    kept = ordered[:max_findings]
    dropped = len(ordered) - len(kept)
    return kept, max(dropped, 0)
