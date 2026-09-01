"""One-off (but reusable) migration: refreshes datadog_url/window_from_ms/
window_to_ms on every existing report, preserving its state, body, cost,
and issue untouched. Needed once because 149 reports were written before
these fields existed; kept in case a future field addition needs the same
treatment.

Usage: python scripts/backfill_datadog_url.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from houston.collector import collect
from houston.dedup import REPORTS_DIR
from houston.frontmatter import Cost, Report, read_report, write_report


def main() -> None:
    findings_by_fp = {f.fingerprint: f for f in collect(window_hours=96)}
    updated, skipped_no_finding = 0, 0

    for path in sorted(REPORTS_DIR.glob("*.md")):
        fingerprint = path.stem
        finding = findings_by_fp.get(fingerprint)
        if finding is None:
            skipped_no_finding += 1
            continue  # finding aged out of the current 96h window -- can't refresh its URL/window

        existing = read_report(path)
        text = path.read_text()
        _, _, body = text.split("---", 2)

        report = Report.from_finding(finding, state=existing["state"], body=body.strip())
        report.cost = Cost(**existing["cost"])
        report.issue = existing.get("issue")
        result = write_report(report)
        assert result.written, f"unexpected quarantine on backfill: {fingerprint}"
        updated += 1

    print(f"updated {updated} reports, {skipped_no_finding} skipped "
          f"(fingerprint no longer in the current 96h window)")


if __name__ == "__main__":
    main()
