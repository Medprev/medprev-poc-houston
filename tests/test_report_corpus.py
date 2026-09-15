"""Invariants of the committed `reports/*.md` corpus (ADR-0029).

Deliberately narrow: the corpus has legacy drift (pre-ADR-0019 reports with
no `novelty`, pre-ADR-0023 reports with no `cost.model`, ...) that makes a
naive "every report matches today's full schema" assertion fail for
reasons that have nothing to do with a bug introduced today. The checks
below hold for every report ever written, regardless of which ADR was in
force at the time -- that's what makes them safe to enforce.

The key checks read the raw document through `split_document`, never
through `Report.from_markdown`: the claim is that the key is *on disk*, and
the parser fills an absent key with the field's default, which would make
the assertion vacuous.
"""
from pathlib import Path

from houston.frontmatter import Report, split_document
from houston.pii_gate import scan

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _report_paths() -> list[Path]:
    return sorted(p for p in REPORTS_DIR.glob("*.md") if p.parent == REPORTS_DIR)


def test_no_committed_report_contains_pii():
    paths = _report_paths()
    assert paths, "expected a non-empty reports/ corpus"
    offenders = {p.name: hits for p in paths if (hits := scan(p.read_text()))}
    assert offenders == {}


def test_every_report_filename_matches_its_own_fingerprint():
    """This is the entire dedup mechanism (dedup.py's `report_path` /
    `already_reported`): a fingerprint's report living at the "wrong" path
    would make dedup blind to it."""
    for path in _report_paths():
        front_matter, _ = split_document(path.read_text())
        assert path.stem == front_matter["fingerprint"], path


def test_every_report_carries_the_fields_dedup_and_metrics_read():
    required = {
        "fingerprint", "source", "reason", "service", "environment",
        "window", "observed", "severity", "state", "cost", "issue",
    }
    for path in _report_paths():
        front_matter, _ = split_document(path.read_text())
        missing = required - front_matter.keys()
        assert not missing, f"{path.name} missing {missing}"
        assert front_matter["state"] in {
            "new", "promoted", "discarded", "seeded", "incomplete", "quarantined",
        }, path


def test_every_committed_report_parses_into_a_report():
    """`load_report` is now the only way dedup, metrics and the site read a
    report, so a document the parser chokes on is a broken `houston metrics`,
    not a cosmetic problem. Covers the drift the checks above tolerate."""
    for path in _report_paths():
        report = Report.from_markdown(path.read_text())
        assert report.fingerprint == path.stem, path
        assert report.state, path


def test_parsed_bodies_carry_no_second_injected_link_line():
    """`to_markdown` injects `**Link do Datadog:**`; `from_markdown` takes it
    back out. Without the inverse, every load-then-write cycle stacked
    another copy -- which is what the backfill script had to strip by hand."""
    for path in _report_paths():
        report = Report.from_markdown(path.read_text())
        assert "**Link do Datadog:**" not in report.body, path
