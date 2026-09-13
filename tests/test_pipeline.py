"""Direct proof of the use cases in houston/pipeline.py (Move C, ADR-0032)
-- seed, plan_run, investigate_findings, promote, fix -- driven with fakes
instead of a Namespace and 5 @patch decorators. This file replaces
tests/test_cli_investigate.py, whose four tests asserted only that mocks
were called; the claims those tests made (state mapping, cost fields
recorded, model/effort forwarded, spend printed) are re-expressed below as
assertions on the InvestigationRun the pipeline actually returns, plus in
tests/test_e2e_pipeline.py's end-to-end runs through main(argv).

`cmd_fix` and `cmd_promote --create` had no tests at all before this PR
(README/ADR-0028 document `--create`'s guards, but nothing exercised
`promote_report`/`fix_report` directly) -- this file adds the first."""
from houston.agent import InvestigationResult
from houston.fix_agent import FixResult
from houston.frontmatter import Report, read_report, write_report
from houston.models import Finding
from houston.pipeline import (
    PipelineError,
    build_promote_command,
    fix_report,
    investigate_findings,
    plan_run,
    promote_report,
    promotion_blockers,
    seed,
)


def _finding(fp="et-cli-test", **overrides) -> Finding:
    defaults = {
        "fingerprint": fp, "source": "error_tracking", "query": "env:production",
        "service": "medprev-rest-api", "reason": "new", "first_seen_ms": 1, "last_seen_ms": 2,
        "observed_count": 5, "severity": "medium", "regressed": False, "raw": {},
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _collect_fn(findings):
    def collect(*, window_hours, should_enrich=None):
        return findings
    return collect


# ---------------------------------------------------------------------------
# seed / plan_run
# ---------------------------------------------------------------------------

def test_seed_writes_state_seeded_for_every_new_finding(store):
    outcome = seed(_collect_fn([_finding()]), window_hours=96)
    assert outcome.written == 1
    assert outcome.findings == 1
    assert outcome.already_reported == 0
    assert outcome.quarantined == []


def test_seed_skips_a_finding_that_already_has_a_report(store):
    finding = _finding()
    write_report(Report.from_finding(finding, state="seeded", body="x"))

    outcome = seed(_collect_fn([finding]), window_hours=96)

    assert outcome.written == 0
    assert outcome.already_reported == 1


def test_plan_run_caps_and_reports_dropped_count(store):
    findings = [_finding(f"et-{i}") for i in range(3)]
    plan = plan_run(_collect_fn(findings), window_hours=96, max_findings=2)
    assert plan.total == 3
    assert plan.needing == 3
    assert len(plan.kept) == 2
    assert plan.dropped == 1


# ---------------------------------------------------------------------------
# investigate_findings -- replaces test_cli_investigate.py
# ---------------------------------------------------------------------------

def test_successful_investigation_writes_state_new(store):
    finding = _finding()

    def investigate_fn(f, **kwargs):
        return InvestigationResult(
            body="## Root cause\nfoo", input_tokens=100, output_tokens=200,
            duration_s=5.0, usd=0.05, state="new", model="claude-sonnet-5",
        )

    run = investigate_findings(
        _collect_fn([finding]), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="sonnet", effort="medium", runner=object(),
    )

    assert len(run.outcomes) == 1
    outcome = run.outcomes[0]
    assert outcome.state == "new"
    assert outcome.usd == 0.05
    assert run.total_usd == 0.05
    # `usd` without the model that produced it is what made ADR-0023 a
    # forensic exercise, so the report has to carry both.
    parsed = read_report(outcome.write.path)
    assert parsed["state"] == "new"
    assert parsed["cost"]["usd"] == 0.05
    assert parsed["cost"]["model"] == "claude-sonnet-5"


def test_timed_out_investigation_writes_incomplete_not_fabricated(store):
    finding = _finding()

    def investigate_fn(f, **kwargs):
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0, duration_s=300.0,
            usd=0.0, state="incomplete", error="timed out after 300s",
        )

    run = investigate_findings(
        _collect_fn([finding]), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="sonnet", effort="medium", runner=object(),
    )

    outcome = run.outcomes[0]
    assert outcome.state == "incomplete"
    text = outcome.write.path.read_text()
    assert "timed out" in text


def test_nothing_new_skips_the_agent_entirely(store):
    calls = []

    def investigate_fn(f, **kwargs):
        calls.append(f)
        raise AssertionError("should never be called")

    run = investigate_findings(
        _collect_fn([]), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="sonnet", effort="medium", runner=object(),
    )

    assert run.outcomes == []
    assert calls == []


def test_model_and_effort_reach_the_agent(store):
    """The operator's own Claude Code model selection must not be able to
    reprice a run, so the caller hands the agent an explicit model and
    effort on every call (ADR-0023)."""
    finding = _finding()
    received = {}

    def investigate_fn(f, **kwargs):
        received.update(kwargs)
        return InvestigationResult(
            body="## Root cause\nfoo", input_tokens=1, output_tokens=1,
            duration_s=1.0, usd=0.01, state="new", model="claude-opus-5",
        )

    investigate_findings(
        _collect_fn([finding]), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="opus", effort="xhigh", runner=object(),
    )

    assert received["model"] == "opus"
    assert received["effort"] == "xhigh"


def test_on_start_callback_fires_once_per_finding_before_the_agent_call(store):
    findings = [_finding("et-a"), _finding("et-b")]
    started = []

    def investigate_fn(f, **kwargs):
        return InvestigationResult(
            body="ok", input_tokens=1, output_tokens=1, duration_s=1.0,
            usd=0.01, state="new", model="claude-sonnet-5",
        )

    investigate_findings(
        _collect_fn(findings), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="sonnet", effort="medium", runner=object(),
        on_start=lambda i, total, f: started.append((i, total, f.fingerprint)),
    )

    assert started == [(1, 2, "et-a"), (2, 2, "et-b")]


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

def test_build_promote_command_raises_for_a_missing_report(store):
    try:
        build_promote_command("et-does-not-exist")
    except PipelineError as exc:
        assert "no report" in str(exc)
    else:
        raise AssertionError("expected PipelineError")


def test_promotion_blockers_flags_wrong_account():
    blockers = promotion_blockers({}, "", "carlacazv", required_account="carlacurymed")
    assert any("carlacurymed" in b for b in blockers)


def test_promotion_blockers_flags_quarantined_state():
    blockers = promotion_blockers(
        {"state": "quarantined"}, "", "carlacurymed", required_account="carlacurymed",
    )
    assert any("quarantined" in b for b in blockers)


def test_promotion_blockers_flags_unexpanded_markers():
    blockers = promotion_blockers(
        {}, "quebra entre window_from e window_to", "carlacurymed",
        required_account="carlacurymed",
    )
    assert any("unexpanded" in b for b in blockers)


def test_promotion_blockers_none_when_everything_is_clean():
    blockers = promotion_blockers(
        {}, "clean body", "carlacurymed", required_account="carlacurymed",
    )
    assert blockers == []


def test_promote_report_files_the_issue_and_records_it(store):
    finding = _finding("et-promote")
    body = "## Causa raiz\nfoo\n\n## Corpo da issue\n**O quê**: quebrou."
    write_report(Report.from_finding(finding, state="new", body=body))

    url = promote_report(
        "et-promote", account="carlacurymed", required_account="carlacurymed",
        create_issue_fn=lambda title, body: "https://github.com/org/repo/issues/9",
    )

    assert url == "https://github.com/org/repo/issues/9"
    parsed = read_report(store / "et-promote.md")
    assert parsed["issue"] == url
    assert parsed["state"] == "promoted"


def test_promote_report_raises_without_filing_when_blocked(store):
    finding = _finding("et-blocked")
    write_report(Report.from_finding(
        finding, state="new", body="## Corpo da issue\nclean",
    ))
    calls = []

    def create_issue_fn(title, body):
        calls.append((title, body))
        return "https://github.com/org/repo/issues/1"

    try:
        promote_report(
            "et-blocked", account="carlacazv", required_account="carlacurymed",
            create_issue_fn=create_issue_fn,
        )
    except PipelineError:
        pass
    else:
        raise AssertionError("expected PipelineError")

    assert calls == []


# ---------------------------------------------------------------------------
# fix
# ---------------------------------------------------------------------------

def test_fix_report_refuses_a_report_that_is_not_promoted(store):
    finding = _finding("et-not-promoted")
    write_report(Report.from_finding(finding, state="new", body="x"))

    try:
        fix_report(
            "et-not-promoted", issue=None, fix_fn=lambda **kw: None,
            resolve_repo_fn=lambda *a: None, runner=object(),
            max_budget_usd="3.00", timeout_s=600, model="sonnet", effort="high",
        )
    except PipelineError as exc:
        assert "not 'promoted'" in str(exc)
    else:
        raise AssertionError("expected PipelineError")


def test_fix_report_refuses_without_an_issue_url(store):
    finding = _finding("et-no-issue")
    write_report(Report.from_finding(finding, state="promoted", body="x"))

    try:
        fix_report(
            "et-no-issue", issue=None, fix_fn=lambda **kw: None,
            resolve_repo_fn=lambda *a: None, runner=object(),
            max_budget_usd="3.00", timeout_s=600, model="sonnet", effort="high",
        )
    except PipelineError as exc:
        assert "issue URL" in str(exc)
    else:
        raise AssertionError("expected PipelineError")


def test_fix_report_refuses_a_service_with_no_repo_mapping(store):
    finding = _finding("et-no-repo", service="totally-unmapped-service")
    write_report(Report.from_finding(finding, state="promoted", body="x"))

    try:
        fix_report(
            "et-no-repo", issue="https://github.com/org/repo/issues/1",
            fix_fn=lambda **kw: None, resolve_repo_fn=lambda *a: None, runner=object(),
            max_budget_usd="3.00", timeout_s=600, model="sonnet", effort="high",
        )
    except PipelineError as exc:
        assert "does not map to a fixable repo" in str(exc)
    else:
        raise AssertionError("expected PipelineError")


def test_fix_report_records_the_pr_and_notifies_the_issue(store):
    finding = _finding("et-fix-ok", service="medprev-rest-api")
    write_report(Report.from_finding(
        finding, state="promoted",
        body="---\nfingerprint: et-fix-ok\n---\n## Causa raiz\nfoo",
    ))
    notifications = []

    def fix_fn(**kwargs):
        return FixResult(
            pr_url="https://github.com/org/repo/pull/1", body="fixed",
            input_tokens=1, output_tokens=1, duration_s=1.0, usd=1.5,
            state="pr_open", branch="houston/fix/et-fix-ok",
        )

    outcome = fix_report(
        "et-fix-ok", issue="https://github.com/org/repo/issues/1", fix_fn=fix_fn,
        resolve_repo_fn=lambda service, body="": {"repo": "org/repo", "path": "/tmp/fake"},
        runner=object(), max_budget_usd="3.00", timeout_s=600, model="sonnet",
        effort="high", notify_fn=lambda url, msg: notifications.append((url, msg)),
    )

    assert outcome.result.pr_url == "https://github.com/org/repo/pull/1"
    assert notifications == [
        ("https://github.com/org/repo/issues/1",
         "PR aberto pelo Houston fix agent: https://github.com/org/repo/pull/1"),
    ]
    parsed = read_report(store / "et-fix-ok.md")
    assert parsed["fix_pr"] == "https://github.com/org/repo/pull/1"
    assert parsed["fix_state"] == "pr_open"
