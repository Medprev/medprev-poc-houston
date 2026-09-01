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


def cap(findings: list[Finding], max_findings: int = 15) -> tuple[list[Finding], int]:
    """Caps by descending observed volume. Returns (kept, dropped_count)."""
    ordered = sorted(findings, key=lambda f: f.observed_count, reverse=True)
    kept = ordered[:max_findings]
    dropped = len(ordered) - len(kept)
    return kept, max(dropped, 0)
