"""Invariants of the committed `reports/*.md` corpus (ADR-0029).

Deliberately narrow: the corpus has legacy drift (pre-ADR-0019 reports with
no `novelty`, pre-ADR-0023 reports with no `cost.model`, ...) that makes a
naive "every report matches today's full schema" assertion fail for
reasons that have nothing to do with a bug introduced today. The three
checks below hold for every report ever written, regardless of which ADR
was in force at the time -- that's what makes them safe to enforce.
"""
from pathlib import Path

from houston.frontmatter import read_report
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
        front_matter = read_report(path)
        assert path.stem == front_matter["fingerprint"], path


def test_every_report_carries_the_fields_dedup_and_metrics_read():
    required = {
        "fingerprint", "source", "reason", "service", "environment",
        "window", "observed", "severity", "state", "cost", "issue",
    }
    for path in _report_paths():
        front_matter = read_report(path)
        missing = required - front_matter.keys()
        assert not missing, f"{path.name} missing {missing}"
        assert front_matter["state"] in {
            "new", "promoted", "discarded", "seeded", "incomplete", "quarantined",
        }, path
