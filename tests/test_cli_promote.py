"""houston promote: prints a ready command, never executes it."""
import argparse
from unittest.mock import patch

from houston.cli import cmd_promote
from houston.frontmatter import Report, write_report
from houston.models import Finding


def test_promote_prints_gh_command_and_never_runs_it(tmp_path, monkeypatch, capsys):
    import houston.dedup as dedup_mod
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

    finding = Finding(
        fingerprint="et-promote-test", source="error_tracking", query="q",
        service="medprev-rest-api", reason="new", first_seen_ms=1, last_seen_ms=2,
        observed_count=1, severity="high", regressed=False, raw={},
    )
    report = Report.from_finding(finding, state="new", body=(
        "## Root cause\nfoo\n\n## Issue body\n**What**: it broke.\n**Why**: users noticed."
    ))
    write_report(report)

    with patch("subprocess.run") as mock_run:
        cmd_promote(argparse.Namespace(fingerprint="et-promote-test"))
        mock_run.assert_not_called()  # never executes, only prints

    out = capsys.readouterr().out
    assert "gh issue create --repo Medprev/medprev-product-backlog" in out
    assert "**What**: it broke." in out
    assert "state: promoted" in out


def test_promote_reports_missing_fingerprint(tmp_path, monkeypatch, capsys):
    import houston.dedup as dedup_mod
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)

    exit_code = cmd_promote(argparse.Namespace(fingerprint="et-does-not-exist"))
    assert exit_code == 1
