"""One-off (but reusable) migration: refreshes the derived fields on every
existing report — the Datadog deep link, and the reason/novelty split —
while preserving everything that was *measured*: state, body, cost, issue,
observed count, first/last seen, severity, and the window those numbers
belong to.

The earlier version rebuilt the whole front-matter from a freshly collected
finding under a preserved body, so a report ended up claiming `count: 48120`
above an evidence section that said 287,657 occurrences, and re-running it
duplicated the injected `**Link do Datadog:**` line. A measured number and
the window it was measured in only mean something together (ADR-0014), so
neither is recomputed here.

Usage: python scripts/backfill_datadog_url.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from houston.collector import collect
from houston.config import Config
from houston.datadog_client import Window, event_explorer_url
from houston.frontmatter import Cost, Report, read_report, write_report
from houston.models import Finding
from houston.report_store import DEFAULT_STORE

_LEGACY_NOVELTY = {"new", "regression"}


def _strip_link_line(body: str) -> str:
    """`to_markdown` injects the link line itself; keeping the previous one
    in the body is what duplicated it on every re-run."""
    kept = [
        line for line in body.strip().splitlines()
        if not line.startswith("**Link do Datadog:**")
    ]
    return "\n".join(kept).strip()


def _recorded_window(existing: dict) -> Window | None:
    window = existing.get("window") or {}
    if window.get("from") and window.get("to"):
        return Window(from_ms=int(window["from"]), to_ms=int(window["to"]))
    return None


def _deep_link(finding: Finding, window: Window | None, site: str) -> str | None:
    """The Kubernetes link is window-scoped, so it is rebuilt against the
    window the report's own numbers were measured in — not the window this
    migration happens to run in."""
    if finding.source == "kubernetes" and window is not None:
        return event_explorer_url(site, finding.query, window)
    return finding.datadog_url


def _repaired_labels(existing: dict, finding: Finding) -> tuple[str, str]:
    """Legacy reports stored "new"/"regression" in `reason`, overwriting the
    diagnostic label the collector had produced. Where the finding is still
    live, its real label is restored and the novelty moves to its own field."""
    legacy_reason = existing.get("reason")
    novelty = existing.get("novelty")
    if novelty is None:
        novelty = legacy_reason if legacy_reason in _LEGACY_NOVELTY else (
            "regression" if finding.regressed else "new"
        )
    reason = legacy_reason
    if reason in _LEGACY_NOVELTY or not reason:
        reason = finding.reason
    return reason, novelty


def main() -> None:
    findings_by_fp = {f.fingerprint: f for f in collect(window_hours=96)}
    site = Config.from_env().dd_site
    updated, skipped_no_finding = 0, 0

    for path in DEFAULT_STORE.iter_paths():
        finding = findings_by_fp.get(path.stem)
        if finding is None:
            skipped_no_finding += 1
            continue  # finding aged out of the current 96h window -- can't refresh its link

        existing = read_report(path)
        _, _, body = path.read_text().split("---", 2)
        window = _recorded_window(existing)
        reason, novelty = _repaired_labels(existing, finding)
        observed = existing.get("observed") or {}

        report = Report(
            fingerprint=existing["fingerprint"],
            source=existing["source"],
            reason=reason,
            novelty=novelty,
            service=existing.get("service"),
            environment=existing.get("environment", "production"),
            window_from_ms=window.from_ms if window else 0,
            window_to_ms=window.to_ms if window else 0,
            observed_count=observed.get("count", 0),
            first_seen_ms=observed.get("first_seen"),
            last_seen_ms=observed.get("last_seen"),
            severity=existing["severity"],
            state=existing["state"],
            body=_strip_link_line(body),
            cost=Cost(**(existing.get("cost") or {})),
            issue=existing.get("issue"),
            datadog_url=_deep_link(finding, window, site),
        )
        result = write_report(report)
        assert result.written, f"unexpected quarantine on backfill: {path.stem}"
        updated += 1

    print(f"updated {updated} reports, {skipped_no_finding} skipped "
          f"(fingerprint no longer in the current 96h window)")


if __name__ == "__main__":
    main()
