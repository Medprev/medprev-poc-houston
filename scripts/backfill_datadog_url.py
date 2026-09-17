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
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from houston.collector import collect
from houston.config import Config
from houston.datadog_client import Window, event_explorer_url
from houston.frontmatter import Report, load_report, write_report
from houston.models import Finding
from houston.report_state import check_fix_state, check_state
from houston.report_store import DEFAULT_STORE

_LEGACY_NOVELTY = {"new", "regression"}


def _deep_link(finding: Finding, report: Report, site: str) -> str | None:
    """The Kubernetes link is window-scoped, so it is rebuilt against the
    window the report's own numbers were measured in — not the window this
    migration happens to run in."""
    if finding.source == "kubernetes" and report.window_from_ms and report.window_to_ms:
        window = Window(from_ms=report.window_from_ms, to_ms=report.window_to_ms)
        return event_explorer_url(site, finding.query, window)
    return finding.datadog_url


def _repaired_labels(existing: Report, finding: Finding) -> tuple[str, str]:
    """Legacy reports stored "new"/"regression" in `reason`, overwriting the
    diagnostic label the collector had produced. Where the finding is still
    live, its real label is restored and the novelty moves to its own field."""
    legacy_reason = existing.reason
    novelty = existing.novelty
    if not novelty:
        novelty = legacy_reason if legacy_reason in _LEGACY_NOVELTY else (
            "regression" if finding.regressed else "new"
        )
    reason = legacy_reason
    if reason in _LEGACY_NOVELTY or not reason:
        reason = finding.reason
    return reason, novelty


def refreshed(existing: Report, finding: Finding, site: str) -> Report:
    """One report, three derived fields refreshed.

    Everything measured -- state, body, cost, issue, observed counts,
    severity, the window, and the fix_pr/fix_state a `houston fix` run
    recorded -- is carried by `replace` rather than re-listed, which is what
    stops a field added to `Report` later from being silently dropped here
    (#35).

    The old code indexed the front-matter dict directly, so a malformed
    report raised KeyError and stopped the migration. `from_markdown` is
    tolerant, so that loudness has to be asked for: this rewrites 153 files
    in one pass, and writing an empty state back over all of them is not a
    failure mode worth discovering afterwards."""
    if not existing.state or not existing.fingerprint:
        raise ValueError(
            "refusing to rewrite a report with no state/fingerprint: "
            f"{existing.fingerprint or '<unnamed>'}"
        )
    reason, novelty = _repaired_labels(existing, finding)
    return replace(
        existing,
        reason=reason,
        novelty=novelty,
        datadog_url=_deep_link(finding, existing, site),
    )


def preflight(paths: list[Path]) -> None:
    """Every report is checked before the first one is written.

    `write_report` refuses a state outside the vocabulary (ADR-0035), and
    this loop rewrites 153 files with no transaction around it -- so without
    a pass up front, one bad document leaves the corpus half-migrated and
    the traceback names the exception, not the file."""
    offenders = []
    for path in paths:
        report = load_report(path)
        try:
            check_state(report.state)
            if report.fix_state is not None:
                check_fix_state(report.fix_state)
        except ValueError as exc:
            offenders.append(f"{path.name}: {exc}")
    if offenders:
        raise SystemExit(
            "refusing to migrate -- fix these first:\n  " + "\n  ".join(offenders)
        )


def main() -> None:
    preflight(list(DEFAULT_STORE.iter_paths()))
    findings_by_fp = {f.fingerprint: f for f in collect(window_hours=96)}
    site = Config.from_env().dd_site
    updated, skipped_no_finding = 0, 0

    for path in DEFAULT_STORE.iter_paths():
        finding = findings_by_fp.get(path.stem)
        if finding is None:
            skipped_no_finding += 1
            continue  # finding aged out of the current 96h window -- can't refresh its link

        result = write_report(refreshed(load_report(path), finding, site))
        assert result.written, f"unexpected quarantine on backfill: {path.stem}"
        updated += 1

    print(f"updated {updated} reports, {skipped_no_finding} skipped "
          f"(fingerprint no longer in the current 96h window)")


if __name__ == "__main__":
    main()
