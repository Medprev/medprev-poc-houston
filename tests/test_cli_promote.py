"""houston promote: prints a ready command by default, files the issue
only under --create, and hands `gh` the issue body — not the whole report,
and not a fenced code block."""
import argparse
from dataclasses import replace
from subprocess import CompletedProcess
from unittest.mock import patch

from houston.cli import cmd_promote, extract_issue_body, read_report
from houston.frontmatter import Report, write_report
from houston.models import Finding

_ISSUE_URL = "https://github.com/Medprev/medprev-product-backlog/issues/5483"

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


def _write(store, fingerprint, body, reason="BranchLaboratoryNotFound",
           regressed=False, state="new", issue=None):
    finding = Finding(
        fingerprint=fingerprint, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason=reason, first_seen_ms=1, last_seen_ms=2,
        observed_count=1, severity="high", regressed=regressed, raw={},
    )
    report = Report.from_finding(finding, state=state, body=body)
    write_report(replace(report, issue=issue))
    return store / f"{fingerprint}.md"


def _args(fingerprint, create=False):
    return argparse.Namespace(fingerprint=fingerprint, create=create)


def _fake_gh(account="carlacurymed", create_returncode=0):
    """Stands in for both `gh` calls promote makes, dispatching on argv."""
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ["gh", "auth", "status"]:
            if account is None:
                return CompletedProcess(argv, 1, "", "not logged in")
            return CompletedProcess(
                argv, 0, f"github.com\n  Logged in to github.com account {account}\n", "",
            )
        if argv[:3] == ["gh", "issue", "create"]:
            if create_returncode != 0:
                return CompletedProcess(argv, create_returncode, "", "gh: Not Found (HTTP 404)")
            return CompletedProcess(argv, 0, f"{_ISSUE_URL}\n", "")
        raise AssertionError(f"unexpected subprocess call: {argv}")

    return run, calls


def test_promote_without_create_prints_the_command_and_runs_nothing(
    store, capsys,
):
    """Filing is opt-in: the bare command touches neither GitHub nor the
    report, so a mistyped fingerprint costs nothing (ADR-0028)."""
    path = _write(store, "et-promote-test", _PT_BODY)

    with patch("houston.cli.subprocess.run") as mock_run:
        cmd_promote(_args("et-promote-test"))
        mock_run.assert_not_called()

    out = capsys.readouterr().out
    assert "gh issue create --repo Medprev/medprev-product-backlog" in out
    assert "--label AIOPS" in out
    assert "**O quê**: a rota quebra." in out
    assert "--create" in out
    assert read_report(path)["state"] == "new"


def test_promote_sends_only_the_issue_body_under_the_portuguese_heading(
    store, capsys,
):
    """Regression test: the code split on "## Issue body" while the prompt
    emits "## Corpo da issue", so `--body` carried the entire report --
    root cause, timeline, evidence and all (ADR-0019)."""
    _write(store, "et-pt", _PT_BODY)
    cmd_promote(_args("et-pt"))

    out = capsys.readouterr().out
    assert "## Causa raiz" not in out
    assert "O serviço medprev-rest-api falha" not in out


def test_promote_unwraps_a_fenced_issue_body(store, capsys):
    """The model tends to fence the section; `gh issue create` would then
    file an issue whose whole 5W2H content renders as one code block."""
    _write(store, "et-fenced", _FENCED_BODY)
    cmd_promote(_args("et-fenced"))

    body_arg = capsys.readouterr().out.split("--body '", 1)[1]
    assert "```" not in body_arg
    assert "**O quê**: a rota quebra." in body_arg


def test_promote_title_names_the_error_not_its_novelty(store, capsys):
    """Regression test: the title read "[error_tracking] regression in
    medprev-rest-api" for every regressed finding, because `reason` held
    the novelty instead of the error type (ADR-0019)."""
    _write(store, "et-title", _PT_BODY,
           reason="BranchLaboratoryNotFoundException", regressed=True)
    cmd_promote(_args("et-title"))

    out = capsys.readouterr().out
    assert "BranchLaboratoryNotFoundException" in out
    assert "[error_tracking] regression: BranchLaboratoryNotFoundException" in out


def test_extract_issue_body_still_reads_the_legacy_english_heading():
    body = "## Root cause\nfoo\n\n## Issue body\n**What**: it broke."
    assert extract_issue_body(body) == "**What**: it broke."


def test_extract_issue_body_falls_back_to_the_whole_report():
    assert extract_issue_body("## Causa raiz\nfoo") == "## Causa raiz\nfoo"


def test_extract_issue_body_keeps_h3_subsections_intact():
    """ADR-0022's issue body has ### subsections (Descrição, Causa raiz,
    Linha do tempo, ...) inside `## Corpo da issue` -- the split-to-EOF
    behaviour of extract_issue_body must carry all of them, not stop at
    the first ###."""
    body = (
        "## Causa raiz\nfoo\n\n"
        "## Corpo da issue\n"
        "### Descrição do incidente\nX quebrou.\n\n"
        "### Ação recomendada\nCorrigir Y no repo Z.\n"
    )
    extracted = extract_issue_body(body)
    assert "### Descrição do incidente" in extracted
    assert "### Ação recomendada" in extracted
    assert "Corrigir Y no repo Z." in extracted


def test_promote_reports_missing_fingerprint(store, capsys):
    exit_code = cmd_promote(_args("et-does-not-exist"))
    assert exit_code == 1


def test_promote_create_files_the_issue_and_records_it_in_the_report(
    store, capsys,
):
    """The whole point: the two manual steps after the command -- filing
    and writing the URL back -- happen in the same gesture as the decision."""
    path = _write(store, "et-create", _PT_BODY)
    run, calls = _fake_gh()

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-create", create=True))

    assert exit_code == 0
    create_call = next(c for c in calls if c[:3] == ["gh", "issue", "create"])
    assert "--repo" in create_call and "Medprev/medprev-product-backlog" in create_call
    assert "--label" in create_call and "AIOPS" in create_call
    title = create_call[create_call.index("--title") + 1]
    assert title == "[error_tracking] BranchLaboratoryNotFound in medprev-rest-api"
    body = create_call[create_call.index("--body") + 1]
    assert body.startswith("**O quê**: a rota quebra.")
    assert "## Causa raiz" not in body

    front = read_report(path)
    assert front["issue"] == _ISSUE_URL
    assert front["state"] == "promoted"
    assert _ISSUE_URL in capsys.readouterr().out


def test_promote_create_keeps_the_body_out_of_a_shell(store):
    """Arguments go through argv, so an apostrophe in the body is data,
    not quoting -- the '\\'' escaping belongs to the printed form only."""
    path = _write(store, "et-quote", _PT_BODY.replace("quebra", "n'ao"))
    run, calls = _fake_gh()

    with patch("houston.cli.subprocess.run", side_effect=run):
        cmd_promote(_args("et-quote", create=True))

    create_call = next(c for c in calls if c[:3] == ["gh", "issue", "create"])
    body = create_call[create_call.index("--body") + 1]
    assert "n'ao" in body
    assert "'\\''" not in body
    assert read_report(path)["state"] == "promoted"


def test_promote_create_refuses_the_personal_github_account(
    store, capsys,
):
    """A 404 on a private Medprev repo is almost always the active account
    flipped to the personal one -- check it before filing, not after."""
    path = _write(store, "et-account", _PT_BODY)
    run, calls = _fake_gh(account="carlacazv")

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-account", create=True))

    assert exit_code == 1
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert read_report(path)["state"] == "new"
    assert "carlacurymed" in capsys.readouterr().err


def test_promote_create_refuses_a_report_that_already_carries_an_issue(
    store, capsys,
):
    """Re-running promote would otherwise file the same finding twice in a
    backlog other teams read."""
    _write(store, "et-dup", _PT_BODY, state="promoted", issue=_ISSUE_URL)
    run, calls = _fake_gh()

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-dup", create=True))

    assert exit_code == 1
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert _ISSUE_URL in capsys.readouterr().err


def test_promote_create_refuses_an_unexpanded_placeholder(store, capsys):
    """Seen for real on 11/09/2026: the rendered body kept `window_from` /
    `window_to` literal, and only a human reading the printed command
    caught it."""
    body = _PT_BODY.replace("a rota quebra", "quebra entre `window_from` e `window_to`")
    path = _write(store, "et-marker", body)
    run, calls = _fake_gh()

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-marker", create=True))

    assert exit_code == 1
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert read_report(path)["state"] == "new"
    err = capsys.readouterr().err
    assert "window_from" in err and "window_to" in err


def test_promote_create_refuses_a_quarantined_report(store, capsys):
    """A quarantined report's body is the redaction record, not an
    investigation (ADR-0015) -- there is no issue body to file."""
    _write(store, "et-quar", "Relatório retido pelo gate de PII.",
           state="quarantined")
    run, calls = _fake_gh()

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-quar", create=True))

    assert exit_code == 1
    assert not any(c[:3] == ["gh", "issue", "create"] for c in calls)
    assert "quarantined" in capsys.readouterr().err


def test_promote_create_leaves_the_report_untouched_when_gh_fails(
    store, capsys,
):
    """No issue means no promotion: recording state: promoted without a URL
    would count a finding that nobody can act on toward the FP rate."""
    path = _write(store, "et-ghfail", _PT_BODY)
    run, _ = _fake_gh(create_returncode=1)

    with patch("houston.cli.subprocess.run", side_effect=run):
        exit_code = cmd_promote(_args("et-ghfail", create=True))

    assert exit_code == 1
    front = read_report(path)
    assert front["state"] == "new"
    assert front["issue"] is None
    assert "HTTP 404" in capsys.readouterr().err
