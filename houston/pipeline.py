"""The houston use cases -- seed, run, investigate, promote, fix -- as
callables independent of argparse (Move C, ADR-0032).

`houston/cli.py` keeps three things this module deliberately does not own:
parsing argv, printing to stdout/stderr, and the three `gh` subprocess
calls (`active_gh_account`, `create_issue`, the fix-PR issue comment) --
those are out of scope for this refactor (tracked in #29), so `promote`
and `fix` below take them as injected callables instead of shelling out
themselves. Everything else a `cmd_*` function used to do -- deciding what
counts as a blocker, building a report, writing it through the gate --
lives here, where it can be called and tested without a `Namespace`.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from houston.dedup import (
    cap,
    filter_needing_investigation,
    filter_new,
    needs_investigation,
)
from houston.fix_agent import FixResult
from houston.frontmatter import (
    QUARANTINED_STATE,
    Cost,
    Report,
    WriteResult,
    record_fix_attempt,
    record_promotion,
    split_document,
    write_report,
)
from houston.model_runner import ModelRunner
from houston.models import Finding
from houston.report_store import DEFAULT_STORE, ReportStore

# What the document writers raise when a report on disk is not the shape
# they expect: no file, no `---` fences, a front-matter key holding a scalar
# where a mapping belongs, a cost value stored as a string. Every one of them
# lands *after* the step that already happened for real -- an issue filed on
# GitHub, an agent run billed -- so the use case reports it rather than dying
# on it and taking the URL or the cost figure with it.
WRITE_BACK_ERRORS = (AttributeError, OSError, TypeError, ValueError, yaml.YAMLError)


class BilledRun(Protocol):
    """What both agent runs report back. `agent.InvestigationResult` and
    `fix_agent.FixResult` carry the same seven numbers under the same names,
    so the mapping onto `Cost` is written once -- the investigation path used
    to copy them field by field after construction, which is the shape of
    drift that dropped `fix_pr`/`fix_state` in #35."""
    input_tokens: int
    output_tokens: int
    duration_s: float
    usd: float
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    model: str | None


def billed(run: BilledRun) -> Cost:
    return Cost(
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        duration_s=run.duration_s,
        usd=run.usd,
        cache_read_input_tokens=run.cache_read_input_tokens,
        cache_creation_input_tokens=run.cache_creation_input_tokens,
        model=run.model,
    )


class PipelineError(Exception):
    """An operator-facing refusal: no report at that fingerprint, wrong
    state, a `gh`/agent failure. `cli.py` turns it into an exit-code-1
    stderr message."""


class PromotionBlocked(PipelineError):
    """The ADR-0028 fail-closed guards refused, before anything was filed.
    Carries the blockers as a list because each one is its own
    operator-facing line -- one of them ends in a copy-pasteable `gh auth
    switch` command, and joining them puts shell syntax right after it."""

    def __init__(self, blockers: list[str]):
        super().__init__("; ".join(blockers))
        self.blockers = blockers


CollectFn = Callable[..., list[Finding]]
# Called with the service alone by investigate, and with the service plus the
# report text by fix; houston.fix_agent.resolve_repo takes both via a
# defaulted second parameter, so one annotation has to cover both shapes.
ResolveRepoFn = Callable[..., dict | None]


# ---------------------------------------------------------------------------
# Issue-body extraction and the promote title/blocker rules -- pure, moved
# from cli.py verbatim.
# ---------------------------------------------------------------------------

# Both headings appear in the corpus: the prompt asks for the Portuguese one,
# the first reports on disk used the English one.
_ISSUE_BODY_HEADINGS = ("## Corpo da issue", "## Issue body")

# Text the report renderer is supposed to have replaced: the collection
# window's own field names, and the timestamp markers of ADR-0022. One left
# raw means the body still carries a placeholder, and a shared backlog is
# not where that gets noticed.
_UNEXPANDED_MARKERS = ("window_from", "window_to", "{{ts:")


def _unfence(text: str) -> str:
    """Strips a wrapping ``` fence. The model tends to fence the issue-body
    section, and `gh issue create --body` would then file an issue whose
    whole 5W2H content renders as one literal code block."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    closing = next(
        (i for i in range(len(lines) - 1, 0, -1) if lines[i].strip().startswith("```")),
        None,
    )
    if closing is None:
        return text
    return "\n".join(lines[1:closing]).strip()


def extract_issue_body(body: str) -> str:
    """Pulls the ready-to-paste issue body out of a report body. Falls back
    to the whole report when neither heading is present, so a malformed
    report still prints something a human can edit."""
    section = body
    for heading in _ISSUE_BODY_HEADINGS:
        if heading in body:
            section = body.split(heading, 1)[1]
            break
    return _unfence(section.strip())


def issue_title(report: Report) -> str:
    """Names the error, in the shape the backlog reads.

    `reason` is the diagnostic label (error_type / monitor name / k8s
    Reason); novelty is a separate field, so the title names the error
    instead of naming how new it is."""
    novelty = "regression: " if report.novelty == "regression" else ""
    return (
        f"[{report.source}] {novelty}{report.reason} "
        f"in {report.service or 'unknown service'}"
    )


def promotion_blockers(
    report: Report, issue_body: str, account: str | None, *, required_account: str,
) -> list[str]:
    """Everything that must be true before an issue reaches the shared
    backlog. Each one fails closed: filing is outward-facing, and undoing
    it means a human closing an issue other people already saw."""
    blockers = []
    if account != required_account:
        blockers.append(
            f"active gh account is {account or 'unreadable'}, not {required_account} "
            f"-- run: gh auth switch --user {required_account}"
        )
    if report.issue:
        blockers.append(f"report already carries issue: {report.issue}")
    if report.state == QUARANTINED_STATE:
        blockers.append(
            "report is quarantined -- its body is the redaction record, "
            "not an investigation (ADR-0015)"
        )
    raw = [marker for marker in _UNEXPANDED_MARKERS if marker in issue_body]
    if raw:
        blockers.append(f"issue body carries unexpanded markers: {', '.join(raw)}")
    return blockers


# ---------------------------------------------------------------------------
# seed / run / investigate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeedOutcome:
    findings: int
    already_reported: int
    written: int
    quarantined: list[tuple[str, list[str]]] = field(default_factory=list)


def seed(
    collect_fn: CollectFn, *, window_hours: int, store: ReportStore = DEFAULT_STORE,
    on_quarantine: Callable[[str, list[str]], None] = lambda *_: None,
) -> SeedOutcome:
    """Records pre-existing debt as state: seeded, investigating nothing.
    This is the one-time bootstrap so the backlog that existed before this
    tool did doesn't get treated as new signal on day one.

    `on_quarantine` fires per quarantined finding instead of only at the
    end: an interrupted seed has still named every fingerprint the gate
    caught, and the alternative is diffing reports/.quarantine/ against
    reports/ by hand."""
    findings = collect_fn(
        window_hours=window_hours,
        should_enrich=lambda fingerprint: not store.exists(fingerprint),
    )
    new_findings = filter_new(findings, store)
    written = 0
    quarantined: list[tuple[str, list[str]]] = []
    for finding in new_findings:
        report = Report.from_finding(finding, state="seeded", body=(
            "Semeado na primeira rodada — dívida pré-existente, ainda não investigada. "
            "Este achado já tinha atividade antes do Houston começar a rastreá-lo."
        ))
        result = write_report(report, store)
        if result.written:
            written += 1
        else:
            quarantined.append((finding.fingerprint, result.pii_hits))
            on_quarantine(finding.fingerprint, result.pii_hits)
    return SeedOutcome(
        findings=len(findings), already_reported=len(findings) - len(new_findings),
        written=written, quarantined=quarantined,
    )


@dataclass(frozen=True)
class RunPlan:
    total: int
    needing: int
    kept: list[Finding]
    dropped: int


def plan_run(
    collect_fn: CollectFn, *, window_hours: int, max_findings: int,
    store: ReportStore = DEFAULT_STORE,
) -> RunPlan:
    """Collects, dedups, and caps -- what `houston investigate` would act
    on, without spending anything (E4 costs money; this does not)."""
    findings = collect_fn(
        window_hours=window_hours,
        should_enrich=lambda fp: needs_investigation(fp, store),
    )
    new_findings = filter_needing_investigation(findings, store)
    kept, dropped = cap(new_findings, max_findings=max_findings)
    return RunPlan(total=len(findings), needing=len(new_findings), kept=kept, dropped=dropped)


@dataclass(frozen=True)
class InvestigationOutcome:
    finding: Finding
    write: WriteResult
    usd: float
    state: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InvestigationRun:
    plan: RunPlan
    outcomes: list[InvestigationOutcome]

    @property
    def total_usd(self) -> float:
        return sum(o.usd for o in self.outcomes)


def investigate_findings(
    collect_fn: CollectFn,
    investigate_fn: Callable[..., object],
    resolve_repo_fn: ResolveRepoFn,
    *,
    window_hours: int,
    max_findings: int,
    max_budget_usd: str,
    timeout_s: int,
    model: str,
    effort: str,
    runner: ModelRunner,
    store: ReportStore = DEFAULT_STORE,
    on_plan: Callable[[RunPlan], None] = lambda *_: None,
    on_start: Callable[[int, int, Finding], None] = lambda *_: None,
    on_result: Callable[[InvestigationOutcome], None] = lambda *_: None,
) -> InvestigationRun:
    """Runs the real agent (`claude -p`) on capped new findings and writes
    real reports. Costs money/quota per ADR-0001 -- default cap is
    deliberately small. Never fabricates a result: a timeout or failure
    writes state: incomplete, not a guessed report.

    Targets findings needing investigation (no report yet, or an existing
    report still state: seeded/incomplete) -- not just brand-new signal.
    A seeded report is overwritten with the real investigation (ADR-0010).

    Three callbacks let a caller narrate the run without this module
    knowing about stdout, and their order is the point: `on_plan` fires
    after planning and before the first paid call -- the tier and budget
    announcement ADR-0023 exists for has to reach the operator while a
    Ctrl-C still saves money -- then `on_start` before each agent call and
    `on_result` after each report is written, so every cost line stays
    attached to the finding that produced it. A caller with no callbacks
    still gets every outcome back at the end."""
    plan = plan_run(collect_fn, window_hours=window_hours, max_findings=max_findings, store=store)
    on_plan(plan)
    outcomes: list[InvestigationOutcome] = []
    for i, finding in enumerate(plan.kept, 1):
        on_start(i, len(plan.kept), finding)
        target_repo = (resolve_repo_fn(finding.service) or {}).get("repo")
        result = investigate_fn(
            finding, max_budget_usd=max_budget_usd, timeout_s=timeout_s,
            target_repo=target_repo, model=model, effort=effort, runner=runner,
        )
        if result.state == "incomplete":
            report = Report.from_finding(finding, state="incomplete", body=(
                f"Investigação não foi concluída: {result.error}"
            ))
        else:
            report = Report.from_finding(finding, state="new", body=result.body)
        report.cost = billed(result)
        write_result = write_report(report, store)
        outcome = InvestigationOutcome(
            finding=finding, write=write_result,
            usd=result.usd, state=result.state, warnings=result.warnings,
        )
        outcomes.append(outcome)
        on_result(outcome)
    return InvestigationRun(plan=plan, outcomes=outcomes)


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromoteCommand:
    path: Path
    title: str
    issue_body: str
    report: Report


def build_promote_command(
    fingerprint: str, *, store: ReportStore = DEFAULT_STORE,
) -> PromoteCommand:
    """The dry-run shape of `houston promote`: what would be filed, never
    run. Raises PipelineError if there is no report at that fingerprint."""
    path = store.path(fingerprint)
    if not path.exists():
        raise PipelineError(f"no report at {path}")
    text = path.read_text()
    report = Report.from_markdown(text)
    # The issue body is filed verbatim into a shared backlog, so it comes
    # from the *document* view, not from `report.body`. 143 of the 153
    # committed reports carry no `## Corpo da issue` heading and hit
    # `extract_issue_body`'s whole-body fallback -- exactly where the
    # injected `**Link do Datadog:**` line lives, and that link is the
    # reader's way to the real evidence (ADR-0011).
    _, document_body = split_document(text)
    return PromoteCommand(
        path=path, title=issue_title(report),
        issue_body=extract_issue_body(document_body), report=report,
    )


def promote_report(
    command: PromoteCommand,
    *,
    account: str | None,
    required_account: str,
    create_issue_fn: Callable[[str, str], str | None],
    on_warning: Callable[[str], None] = lambda _: None,
) -> str:
    """Files the issue and records `issue:` + `state: promoted`. Raises
    PromotionBlocked when a guard refuses before anything is filed
    (ADR-0028), PipelineError when `gh` itself fails after the attempt --
    promoting stays a human gesture, and every refusal fails closed rather
    than filing something a human would have to notice and undo.

    Takes the command the caller already built rather than a fingerprint:
    the guards then judge the same bytes that get filed, and a non-default
    store is named once instead of at two call sites that could disagree."""
    blockers = promotion_blockers(
        command.report, command.issue_body, account, required_account=required_account,
    )
    if blockers:
        raise PromotionBlocked(blockers)

    url = create_issue_fn(command.title, command.issue_body)
    if url is None:
        raise PipelineError("gh issue create failed -- report left untouched")

    try:
        record_promotion(command.path, url)
    except WRITE_BACK_ERRORS as exc:
        on_warning(
            f"issue filed at {url}, but recording it on {command.path.name} failed: "
            f"{exc} -- write `issue: {url}` and `state: promoted` by hand, or the "
            f"next run will file it again"
        )
    return url


# ---------------------------------------------------------------------------
# fix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FixOutcome:
    repo_info: dict
    issue_url: str
    result: FixResult


def fix_report(
    fingerprint: str,
    *,
    issue: str | None,
    fix_fn: Callable[..., object],
    resolve_repo_fn: ResolveRepoFn,
    runner: ModelRunner,
    max_budget_usd: str,
    timeout_s: int,
    model: str,
    effort: str,
    notify_fn: Callable[[str, str], None] = lambda *_: None,
    on_start: Callable[[dict, str], None] = lambda *_: None,
    on_warning: Callable[[str], None] = lambda _: None,
    store: ReportStore = DEFAULT_STORE,
) -> FixOutcome:
    """Creates a PR that fixes a promoted finding. Costs money -- runs a
    claude -p subprocess with code tools against the target service's
    repo. Raises PipelineError for every precondition a human already
    checked once at promote time but that may have changed since (state,
    issue URL, a repo mapping).

    `on_start` fires with the resolved repo and issue URL before the agent
    call, and that is the only moment the mapping is still cancellable:
    resolve_repo falls back to scanning the report body, so a report
    naming a second service can resolve to the wrong repo, and this agent
    writes code, pushes a branch and opens a PR."""
    path = store.path(fingerprint)
    if not path.exists():
        raise PipelineError(f"no report at {path}")

    text = path.read_text()
    report = Report.from_markdown(text)
    if report.state != "promoted":
        raise PipelineError(f"report state is '{report.state}', not 'promoted'")

    issue_url = issue or report.issue
    if not issue_url:
        raise PipelineError(
            "no issue URL: pass --issue <url> or set the issue: field in the report"
        )

    service = report.service
    repo_info = resolve_repo_fn(service, text)
    if repo_info is None:
        raise PipelineError(f"service '{service}' does not map to a fixable repo")

    on_start(repo_info, issue_url)

    result = fix_fn(
        fingerprint=fingerprint, report_markdown=text, issue_url=issue_url,
        repo_info=repo_info, max_budget_usd=max_budget_usd, timeout_s=timeout_s,
        model=model, effort=effort, runner=runner,
    )

    # Recorded before notifying, and recorded on every outcome: `gh` not
    # being on PATH must not be what loses the URL of a PR the agent already
    # pushed, and an attempt that ends without a PR still billed. A write
    # failure here (a malformed document, a permissions error) must not cost
    # the operator the PR URL or cost figure a paid run already produced --
    # this is the one caller allowed to see it happen and still hand back
    # what the run achieved, printed rather than raised.
    try:
        record_fix_attempt(
            path, pr_url=result.pr_url, state=result.state, cost=billed(result),
        )
    except WRITE_BACK_ERRORS as exc:
        on_warning(
            f"fix attempt for {fingerprint} spent ${result.usd:.4f} and "
            f"{'opened ' + result.pr_url if result.pr_url else 'did not open a PR'}, "
            f"but recording it on the report failed: {exc}"
        )
    if result.pr_url:
        notify_fn(issue_url, f"PR aberto pelo Houston fix agent: {result.pr_url}")

    return FixOutcome(repo_info=repo_info, issue_url=issue_url, result=result)
