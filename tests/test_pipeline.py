"""Direct proof of the use cases in houston/pipeline.py (Move C, ADR-0032)
-- seed, plan_run, investigate_findings, promote, fix -- driven with fakes
instead of a Namespace and 5 @patch decorators. This file replaces
tests/test_cli_investigate.py, whose four tests asserted only that mocks
were called; the claims those tests made (state mapping, cost fields
recorded, model/effort forwarded, spend printed) are re-expressed below as
assertions on the InvestigationRun the pipeline actually returns, plus in
tests/test_e2e_pipeline.py's end-to-end runs through main(argv).

`cmd_fix` had no tests at all before this PR -- the largest untested
function in the package -- and nothing called `promote_report` or
`fix_report` directly; `cmd_promote --create` was already covered through
the CLI by seven tests in tests/test_cli_promote.py, which stay."""
import pytest

from houston.agent import InvestigationResult
from houston.fix_agent import FixResult
from houston.frontmatter import Report, load_report, write_report
from houston.models import Finding
from houston.pipeline import (
    PipelineError,
    PromotionBlocked,
    build_promote_command,
    fix_report,
    investigate_findings,
    plan_run,
    promote_report,
    promotion_blockers,
    seed,
)
from houston.report_store import ReportStore


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
    # ADR-0010: seeded has to be distinguishable from investigated, or the
    # finding never re-enters the queue and its $0 cost pollutes metrics.
    assert load_report(store / "et-cli-test.md").state == "seeded"


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
    parsed = load_report(outcome.write.path)
    assert parsed.state == "new"
    assert parsed.cost.usd == 0.05
    assert parsed.cost.model == "claude-sonnet-5"


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

    runner = object()
    investigate_findings(
        _collect_fn([finding]), investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="opus", effort="xhigh", runner=runner,
    )

    assert received["model"] == "opus"
    assert received["effort"] == "xhigh"
    # The port of ADR-0031 is only real if the injected runner is the one
    # that arrives: agent.investigate defaults to DEFAULT_RUNNER, so a
    # dropped forward would send the real subprocess runner silently.
    assert received["runner"] is runner


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


def _report(**overrides) -> Report:
    """A parsed report, the shape `build_promote_command` hands the guards.
    Built through the parser rather than the constructor so the guards are
    exercised against the same value a real report file produces."""
    front = "\n".join(f"{k}: {v}" for k, v in {"state": "new", **overrides}.items())
    return Report.from_markdown(f"---\n{front}\n---\n\nbody\n")


def test_promotion_blockers_flags_wrong_account():
    blockers = promotion_blockers(
        _report(), "", "carlacazv", required_account="carlacurymed",
    )
    assert any("carlacurymed" in b for b in blockers)


def test_promotion_blockers_flags_quarantined_state():
    blockers = promotion_blockers(
        _report(state="quarantined"), "", "carlacurymed",
        required_account="carlacurymed",
    )
    assert any("quarantined" in b for b in blockers)


def test_promotion_blockers_flags_a_report_that_already_carries_an_issue():
    blockers = promotion_blockers(
        _report(issue="https://github.com/Medprev/medprev-product-backlog/issues/1"),
        "", "carlacurymed", required_account="carlacurymed",
    )
    assert any("already carries issue" in b for b in blockers)


def test_promotion_blockers_flags_unexpanded_markers():
    blockers = promotion_blockers(
        _report(), "quebra entre window_from e window_to", "carlacurymed",
        required_account="carlacurymed",
    )
    assert any("unexpanded" in b for b in blockers)


def test_promotion_blockers_none_when_everything_is_clean():
    blockers = promotion_blockers(
        _report(), "clean body", "carlacurymed", required_account="carlacurymed",
    )
    assert blockers == []


def test_promote_report_files_the_issue_and_records_it(store):
    finding = _finding("et-promote")
    body = "## Causa raiz\nfoo\n\n## Corpo da issue\n**O quê**: quebrou."
    write_report(Report.from_finding(finding, state="new", body=body))

    url = promote_report(
        build_promote_command("et-promote"),
        account="carlacurymed", required_account="carlacurymed",
        create_issue_fn=lambda title, body: "https://github.com/org/repo/issues/9",
    )

    assert url == "https://github.com/org/repo/issues/9"
    parsed = load_report(store / "et-promote.md")
    assert parsed.issue == url
    assert parsed.state == "promoted"


def test_promote_report_raises_without_filing_when_blocked(store):
    finding = _finding("et-blocked")
    write_report(Report.from_finding(
        finding, state="new", body="## Corpo da issue\nclean",
    ))
    calls = []

    def create_issue_fn(title, body):
        calls.append((title, body))
        return "https://github.com/org/repo/issues/1"

    with pytest.raises(PromotionBlocked):
        promote_report(
            build_promote_command("et-blocked"),
            account="carlacazv", required_account="carlacurymed",
            create_issue_fn=create_issue_fn,
        )

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
    parsed = load_report(store / "et-fix-ok.md")
    assert parsed.fix_pr == "https://github.com/org/repo/pull/1"
    assert parsed.fix_state == "pr_open"
    assert parsed.fix_cost.usd == 1.5


def test_fix_report_records_what_the_attempt_billed(store):
    """The FixResult -> front-matter mapping, end to end: an attempt that
    opens no PR still spent money, and the report is where that number is
    read from (`houston metrics`)."""
    finding = _finding("et-fix-paid", service="medprev-rest-api")
    write_report(Report.from_finding(finding, state="promoted", body="## Causa raiz\nfoo"))

    def fix_fn(**kwargs):
        return FixResult(
            pr_url=None, body=None, input_tokens=90000, output_tokens=4200,
            duration_s=311.5, usd=1.84, state="incomplete",
            error="agent finished but no PR URL found in output",
            cache_read_input_tokens=80000, cache_creation_input_tokens=3000,
            model="claude-sonnet-5",
        )

    fix_report(
        "et-fix-paid", issue="https://github.com/org/repo/issues/1", fix_fn=fix_fn,
        resolve_repo_fn=lambda service, body="": {"repo": "org/repo", "path": "/tmp/fake"},
        runner=object(), max_budget_usd="3.00", timeout_s=600, model="sonnet",
        effort="high", notify_fn=lambda url, msg: None,
    )

    parsed = load_report(store / "et-fix-paid.md")
    assert parsed.fix_cost.usd == 1.84
    assert parsed.fix_cost.input_tokens == 90000
    assert parsed.fix_cost.model == "claude-sonnet-5"
    assert parsed.fix_state == "incomplete"
    assert parsed.cost.usd == 0.0  # the investigation's own cost, untouched


# ---------------------------------------------------------------------------
# the seams the three moves introduced: store, runner, and the callbacks that
# keep operator-facing output attached to the step that produced it
# ---------------------------------------------------------------------------

def test_an_explicit_store_is_where_the_report_lands(store, tmp_path):
    """ADR-0030's seam is advertised in every use-case signature; the
    conftest `store` fixture repoints DEFAULT_STORE in place, so a dropped
    `store` forward is invisible to every other test in this suite. A
    caller passing its own ReportStore -- a dry-run directory -- would
    otherwise write into the real reports/ instead."""
    other = ReportStore(tmp_path / "elsewhere")
    other.root.mkdir()

    outcome = seed(_collect_fn([_finding("et-elsewhere")]), window_hours=96, store=other)

    assert outcome.written == 1
    assert (other.root / "et-elsewhere.md").exists()
    assert not (store / "et-elsewhere.md").exists()


def test_investigation_writes_through_the_store_it_was_given(store, tmp_path):
    other = ReportStore(tmp_path / "elsewhere")
    other.root.mkdir()

    def investigate_fn(f, **kwargs):
        return InvestigationResult(
            body="## Causa raiz\nfoo", input_tokens=1, output_tokens=1,
            duration_s=1.0, usd=0.01, state="new",
        )

    investigate_findings(
        _collect_fn([_finding("et-store")]), investigate_fn,
        resolve_repo_fn=lambda *a: None, window_hours=96, max_findings=5,
        max_budget_usd="0.50", timeout_s=300, model="sonnet", effort="medium",
        runner=object(), store=other,
    )

    assert (other.root / "et-store.md").exists()
    assert not (store / "et-store.md").exists()


def test_unresolved_timestamp_warnings_survive_into_the_outcome(store):
    """ADR-0022: a report written with a raw {{ts:}} placeholder has to
    warn at the moment it is paid for. The outcome is the only carrier
    between the agent and that warning."""
    def investigate_fn(f, **kwargs):
        return InvestigationResult(
            body="## Causa raiz\nfoo", input_tokens=1, output_tokens=1,
            duration_s=1.0, usd=0.01, state="new",
            warnings=["{{ts:not-a-timestamp}}"],
        )

    run = investigate_findings(
        _collect_fn([_finding("et-warn")]), investigate_fn,
        resolve_repo_fn=lambda *a: None, window_hours=96, max_findings=5,
        max_budget_usd="0.50", timeout_s=300, model="sonnet", effort="medium",
        runner=object(),
    )

    assert run.outcomes[0].warnings == ["{{ts:not-a-timestamp}}"]


def test_on_plan_fires_before_the_first_paid_call(store):
    """The tier/budget announcement ADR-0023 exists for is only a guard if
    it reaches the operator while a Ctrl-C still saves money."""
    events = []

    def investigate_fn(f, **kwargs):
        events.append(("agent", f.fingerprint))
        return InvestigationResult(
            body="ok", input_tokens=1, output_tokens=1, duration_s=1.0,
            usd=0.01, state="new",
        )

    investigate_findings(
        _collect_fn([_finding("et-a"), _finding("et-b")]), investigate_fn,
        resolve_repo_fn=lambda *a: None, window_hours=96, max_findings=5,
        max_budget_usd="0.50", timeout_s=300, model="sonnet", effort="medium",
        runner=object(), on_plan=lambda plan: events.append(("plan", len(plan.kept))),
        on_result=lambda outcome: events.append(("result", outcome.finding.fingerprint)),
    )

    assert events == [
        ("plan", 2),
        ("agent", "et-a"), ("result", "et-a"),
        ("agent", "et-b"), ("result", "et-b"),
    ]


def test_seed_names_each_quarantined_finding_as_the_gate_catches_it(store):
    """Batching the quarantine list until the end means an interrupted
    seed names none of them, and the operator diffs reports/.quarantine/
    against reports/ by hand (ADR-0004 measured this branch at 22% of a
    real run)."""
    # The gate reads the full rendered file, front-matter included
    # (ADR-0015), which is how a diagnostic label carrying a document
    # quarantines a report whose body is the fixed seed text.
    finding = _finding("et-pii", reason="lookup falhou para 123.456.789-09")
    seen = []

    outcome = seed(
        _collect_fn([finding]), window_hours=96,
        on_quarantine=lambda fp, hits: seen.append((fp, hits)),
    )

    assert outcome.written == 0
    assert len(outcome.quarantined) == 1
    assert [fp for fp, _ in seen] == ["et-pii"]
    assert seen[0][1] == outcome.quarantined[0][1]


def test_promotion_blocked_carries_every_blocker_separately(store):
    """One blocker ends in a copy-pasteable `gh auth switch` command;
    joining them puts `; ` -- shell syntax -- immediately after it."""
    finding = _finding("et-two-blockers")
    write_report(Report.from_finding(
        finding, state="new", body="## Corpo da issue\nwindow_from ainda cru",
    ))

    with pytest.raises(PromotionBlocked) as excinfo:
        promote_report(
            build_promote_command("et-two-blockers"),
            account="carlacazv", required_account="carlacurymed",
            create_issue_fn=lambda title, body: "https://github.com/org/repo/issues/1",
        )

    assert len(excinfo.value.blockers) == 2
    assert any("carlacazv" in b for b in excinfo.value.blockers)
    assert any("window_from" in b for b in excinfo.value.blockers)


def test_a_gh_failure_is_not_a_promotion_blocker(store):
    """`gh` failing happens after the guards passed and after the attempt;
    labelling it "refusing to promote" tells the operator nothing was
    filed, which is exactly what they cannot assume."""
    finding = _finding("et-gh-down")
    write_report(Report.from_finding(
        finding, state="new", body="## Corpo da issue\nclean",
    ))

    with pytest.raises(PipelineError) as excinfo:
        promote_report(
            build_promote_command("et-gh-down"),
            account="carlacurymed", required_account="carlacurymed",
            create_issue_fn=lambda title, body: None,
        )

    assert not isinstance(excinfo.value, PromotionBlocked)
    assert "gh issue create failed" in str(excinfo.value)


def _promoted_report(store, fingerprint):
    write_report(Report.from_finding(
        _finding(fingerprint, service="medprev-rest-api"), state="promoted",
        body="## Causa raiz\nfoo",
    ))


def test_fix_discloses_the_resolved_repo_before_the_agent_runs(store):
    """resolve_repo falls back to scanning the report body, so a report
    naming a second service can resolve to the wrong repo -- and this
    agent writes code, pushes a branch and opens a PR. The mapping is only
    cancellable before the call."""
    _promoted_report(store, "et-fix-order")
    events = []
    received = {}

    def fix_fn(**kwargs):
        events.append("agent")
        received.update(kwargs)
        return FixResult(
            pr_url="https://github.com/org/repo/pull/1", body="fixed",
            input_tokens=1, output_tokens=1, duration_s=1.0, usd=1.5,
            state="pr_open", branch="houston/fix/et-fix-order",
        )

    runner = object()
    fix_report(
        "et-fix-order", issue="https://github.com/org/repo/issues/1", fix_fn=fix_fn,
        resolve_repo_fn=lambda service, body="": {"repo": "org/repo", "path": "/tmp/fake"},
        runner=runner, max_budget_usd="3.00", timeout_s=600, model="sonnet",
        effort="high", on_start=lambda repo_info, url: events.append(repo_info["repo"]),
    )

    assert events == ["org/repo", "agent"]
    # Same seam as investigate: fix_agent.fix defaults to DEFAULT_RUNNER,
    # so a dropped forward reaches the real subprocess runner in silence.
    assert received["runner"] is runner


def test_the_pr_url_is_recorded_before_gh_is_told_about_it(store):
    """`gh` missing from PATH -- the realistic cron/CI case -- must not be
    what loses the URL of a PR the agent already pushed and billed for."""
    _promoted_report(store, "et-fix-notify-fails")

    def fix_fn(**kwargs):
        return FixResult(
            pr_url="https://github.com/org/repo/pull/7", body="fixed",
            input_tokens=1, output_tokens=1, duration_s=1.0, usd=2.9,
            state="pr_open", branch="houston/fix/et-fix-notify-fails",
        )

    def notify_fn(url, message):
        raise FileNotFoundError("gh")

    with pytest.raises(FileNotFoundError):
        fix_report(
            "et-fix-notify-fails", issue="https://github.com/org/repo/issues/1",
            fix_fn=fix_fn,
            resolve_repo_fn=lambda service, body="": {"repo": "org/repo", "path": "/tmp/fake"},
            runner=object(), max_budget_usd="3.00", timeout_s=600, model="sonnet",
            effort="high", notify_fn=notify_fn,
        )

    parsed = load_report(store / "et-fix-notify-fails.md")
    assert parsed.fix_pr == "https://github.com/org/repo/pull/7"
    assert parsed.fix_state == "pr_open"


def test_the_filed_issue_body_keeps_the_datadog_link(store):
    """143 of the 153 committed reports carry no `## Corpo da issue` heading,
    so `extract_issue_body` falls back to the whole body -- which is exactly
    where the injected `**Link do Datadog:**` line lives. Building the command
    from `report.body` (link-stripped) silently dropped the reader's only way
    to the evidence from every issue filed off those reports (ADR-0011)."""
    finding = _finding(
        "et-no-heading",
        datadog_url="https://app.datadoghq.com/error-tracking/issue/no-heading",
    )
    write_report(Report.from_finding(finding, body="Seeded, not investigated."))

    command = build_promote_command("et-no-heading")

    assert command.issue_body.startswith("**Link do Datadog:**")
    assert "Seeded, not investigated." in command.issue_body
