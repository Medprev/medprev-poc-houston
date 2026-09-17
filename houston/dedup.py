"""E3 — dedup, seed, cap. reports/{fingerprint}.md existing means already
handled; that is the entire dedup mechanism, no separate index needed."""
from collections import defaultdict

from houston.frontmatter import load_report
from houston.models import Finding
from houston.report_state import needs_investigation as state_needs_investigation
from houston.report_store import DEFAULT_STORE, ReportStore


def already_reported(fingerprint: str, store: ReportStore = DEFAULT_STORE) -> bool:
    return store.exists(fingerprint)


def filter_new(
    findings: list[Finding], store: ReportStore = DEFAULT_STORE,
) -> list[Finding]:
    return [f for f in findings if not already_reported(f.fingerprint, store)]


def needs_investigation(fingerprint: str, store: ReportStore = DEFAULT_STORE) -> bool:
    """Predicate form of filter_needing_investigation. The collector uses it
    to decide which findings are worth an extra per-finding detail call, so
    the expensive fan-out follows the same rule as the investigation itself."""
    path = store.path(fingerprint)
    if not path.exists():
        return True
    return state_needs_investigation(load_report(path).state)


def filter_needing_investigation(
    findings: list[Finding], store: ReportStore = DEFAULT_STORE,
) -> list[Finding]:
    """Unlike filter_new, a finding is NOT excluded just because
    reports/{fingerprint}.md exists -- `houston seed` deliberately writes a
    report with no real investigation (state: seeded), and dedup treating
    "has a file" as "done forever" meant seeded findings could never get
    real evidence/cause/timeline through `houston investigate`. This is
    what `houston run`/`houston investigate` should use; `houston seed`
    keeps using `filter_new` (existence-only), since seeding must never
    overwrite an already-decided or already-investigated report."""
    return [f for f in findings if needs_investigation(f.fingerprint, store)]


# Severity is computed by each source at real effort (ADR-0009 spent a whole
# live investigation establishing that the priority:pN *tag* is the only
# usable monitor signal); ranking has to actually read it.
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _severity_rank(finding: Finding) -> int:
    return _SEVERITY_RANK.get(finding.severity, len(_SEVERITY_RANK))


def cap(findings: list[Finding], max_findings: int = 15) -> tuple[list[Finding], int]:
    """Caps by severity tier first, then round-robin across sources, and
    only inside one (tier, source) group by descending observed volume.
    Returns (kept, dropped_count).

    `observed_count` counts three incommensurable things: errors in the
    window (error_tracking), warning events in the window (kubernetes), and
    alert notifications (monitor). Ordering the mixed list by that single
    number put error_tracking in the top 16 places on the real corpus and
    left every monitor finding — including P1/P2 — unreachable behind the
    deliberately small --max-findings (ADR-0018)."""
    grouped: dict[int, dict[str, list[Finding]]] = defaultdict(lambda: defaultdict(list))
    for finding in findings:
        grouped[_severity_rank(finding)][finding.source].append(finding)

    ordered: list[Finding] = []
    for tier in sorted(grouped):
        queues = []
        for source in sorted(grouped[tier]):
            queue = sorted(
                grouped[tier][source],
                key=lambda f: (-f.observed_count, f.fingerprint),
            )
            queues.append(queue)
        while any(queues):
            for queue in queues:
                if queue:
                    ordered.append(queue.pop(0))

    kept = ordered[:max_findings]
    return kept, max(len(ordered) - len(kept), 0)
