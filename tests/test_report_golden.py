"""Byte-for-byte proof of the rendered report contract (ADR-0029).

Nothing in the existing suite asserts the exact bytes `write_report` puts on
disk -- front-matter key order, the injected `**Link do Datadog:**` line and
its blank-line framing, the trailing newline. Those bytes are the product:
153 tracked `reports/*.md` files are parsed back by `Report.from_markdown`
and patched in place by the promote and fix front-matter rewrites. A silent
change to `Report.to_markdown()`'s framing would not fail a single test
today -- these two do.

Frozen inputs use round dollar amounts (0.32, not a float that doesn't
round-trip) so the golden text is exactly reproducible.
"""
from pathlib import Path

from houston.frontmatter import Cost, Report, write_report
from houston.models import Finding

GOLDEN_DIR = Path(__file__).parent / "golden"


def _finding(fingerprint: str, *, regressed: bool) -> Finding:
    return Finding(
        fingerprint=fingerprint, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="ProfessionalNotFoundException",
        first_seen_ms=1700000000000, last_seen_ms=1700000001000,
        observed_count=42, severity="high", regressed=regressed, raw={},
        datadog_url=f"https://app.datadoghq.com/error-tracking/issue/{fingerprint}",
        window_from_ms=1700000000000, window_to_ms=1700086400000,
    )


def test_investigated_report_renders_byte_for_byte(store):
    finding = _finding("et-golden-test", regressed=True)
    report = Report.from_finding(
        finding, state="new", body="Causa raiz: timeout no client axios apos 5s.",
    )
    report.cost = Cost(
        input_tokens=12000, output_tokens=800, duration_s=42.5, usd=0.32,
        cache_read_input_tokens=9000, cache_creation_input_tokens=1200,
        model="claude-sonnet-5",
    )

    result = write_report(report)

    assert result.written
    assert result.path.read_text() == (GOLDEN_DIR / "report_new.md").read_text()


def test_quarantined_report_leaves_a_redacted_record_and_a_full_quarantine_file(store):
    finding = _finding("et-golden-quarantine", regressed=False)
    report = Report.from_finding(
        finding, state="new",
        body="Contato: carla.cury@medprevonline.com relatou o erro.",
    )
    report.cost = Cost(
        input_tokens=5000, output_tokens=300, duration_s=10.0, usd=0.10,
        model="claude-sonnet-5",
    )

    result = write_report(report)

    assert not result.written
    assert result.pii_hits == ["email"]
    assert result.record_path.read_text() == (
        GOLDEN_DIR / "report_quarantine_record.md"
    ).read_text()
    assert result.path.read_text() == (
        GOLDEN_DIR / "report_quarantine_full.md"
    ).read_text()
