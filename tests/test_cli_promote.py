"""houston promote: prints a ready command, never executes it, and hands
`gh` the issue body — not the whole report, and not a fenced code block."""
import argparse
from unittest.mock import patch

from houston.cli import cmd_promote, extract_issue_body
from houston.frontmatter import Report, write_report
from houston.models import Finding

_PT_BODY = """## Causa raiz
O serviço medprev-rest-api falha ao resolver o profissional.

## Corpo da issue
**O quê**: a rota quebra.
**Por quê**: usuários afetados.
"""

_FENCED_BODY = """## Causa raiz
foo

## Corpo da issue
```markdown
**O quê**: a rota quebra.
**Por quê**: usuários afetados.
```
"""


def _write(tmp_path, monkeypatch, fingerprint, body, reason="BranchLaboratoryNotFound",
           regressed=False):
    import houston.dedup as dedup_mod
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

    finding = Finding(
        fingerprint=fingerprint, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason=reason, first_seen_ms=1, last_seen_ms=2,
        observed_count=1, severity="high", regressed=regressed, raw={},
    )
    write_report(Report.from_finding(finding, state="new", body=body))


def test_promote_prints_gh_command_and_never_runs_it(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch, "et-promote-test", _PT_BODY)

    with patch("subprocess.run") as mock_run:
        cmd_promote(argparse.Namespace(fingerprint="et-promote-test"))
        mock_run.assert_not_called()  # never executes, only prints

    out = capsys.readouterr().out
    assert "gh issue create --repo Medprev/medprev-product-backlog" in out
    assert "**O quê**: a rota quebra." in out
    assert "state: promoted" in out


def test_promote_sends_only_the_issue_body_under_the_portuguese_heading(
    tmp_path, monkeypatch, capsys,
):
    """Regression test: the code split on "## Issue body" while the prompt
    emits "## Corpo da issue", so `--body` carried the entire report --
    root cause, timeline, evidence and all (ADR-0019)."""
    _write(tmp_path, monkeypatch, "et-pt", _PT_BODY)
    cmd_promote(argparse.Namespace(fingerprint="et-pt"))

    out = capsys.readouterr().out
    assert "## Causa raiz" not in out
    assert "O serviço medprev-rest-api falha" not in out


def test_promote_unwraps_a_fenced_issue_body(tmp_path, monkeypatch, capsys):
    """The model tends to fence the section; `gh issue create` would then
    file an issue whose whole 5W2H content renders as one code block."""
    _write(tmp_path, monkeypatch, "et-fenced", _FENCED_BODY)
    cmd_promote(argparse.Namespace(fingerprint="et-fenced"))

    body_arg = capsys.readouterr().out.split("--body '", 1)[1]
    assert "```" not in body_arg
    assert "**O quê**: a rota quebra." in body_arg


def test_promote_title_names_the_error_not_its_novelty(tmp_path, monkeypatch, capsys):
    """Regression test: the title read "[error_tracking] regression in
    medprev-rest-api" for every regressed finding, because `reason` held
    the novelty instead of the error type (ADR-0019)."""
    _write(tmp_path, monkeypatch, "et-title", _PT_BODY,
           reason="BranchLaboratoryNotFoundException", regressed=True)
    cmd_promote(argparse.Namespace(fingerprint="et-title"))

    out = capsys.readouterr().out
    assert "BranchLaboratoryNotFoundException" in out
    assert "[error_tracking] regression: BranchLaboratoryNotFoundException" in out


def test_extract_issue_body_still_reads_the_legacy_english_heading():
    body = "## Root cause\nfoo\n\n## Issue body\n**What**: it broke."
    assert extract_issue_body(body) == "**What**: it broke."


def test_extract_issue_body_falls_back_to_the_whole_report():
    assert extract_issue_body("## Causa raiz\nfoo") == "## Causa raiz\nfoo"


def test_promote_reports_missing_fingerprint(tmp_path, monkeypatch, capsys):
    import houston.dedup as dedup_mod
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)

    exit_code = cmd_promote(argparse.Namespace(fingerprint="et-does-not-exist"))
    assert exit_code == 1
