"""houston — CLI entrypoint. `python -m houston.cli <command>`."""
import argparse
import re
import subprocess
import sys

from houston.agent import DEFAULT_EFFORT as AGENT_DEFAULT_EFFORT
from houston.agent import DEFAULT_MAX_BUDGET_USD as AGENT_DEFAULT_BUDGET
from houston.agent import DEFAULT_MODEL as AGENT_DEFAULT_MODEL
from houston.agent import investigate as agent_investigate
from houston.collector import collect
from houston.dedup import (
    already_reported,
    cap,
    filter_needing_investigation,
    filter_new,
    needs_investigation,
    report_path,
)
from houston.fix_agent import DEFAULT_EFFORT as FIX_DEFAULT_EFFORT
from houston.fix_agent import DEFAULT_MODEL as FIX_DEFAULT_MODEL
from houston.fix_agent import fix as agent_fix
from houston.fix_agent import resolve_repo
from houston.frontmatter import (
    QUARANTINED_STATE,
    Report,
    read_report,
    write_report,
)
from houston.metrics import BLOCKING_STATES, can_close_phase, compute, load_all_reports

# Both headings appear in the corpus: the prompt asks for the Portuguese one,
# the first reports on disk used the English one.
_ISSUE_BODY_HEADINGS = ("## Corpo da issue", "## Issue body")

ISSUE_REPO = "Medprev/medprev-product-backlog"
ISSUE_LABEL = "AIOPS"
ISSUE_ACCOUNT = "carlacurymed"

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


def cmd_seed(args: argparse.Namespace) -> int:
    """Records pre-existing debt as state: seeded, investigating nothing.
    This is the one-time bootstrap so the backlog that existed before this
    tool did doesn't get treated as new signal on day one."""
    # Seeding writes a report for anything that has none, so that is
    # exactly the set worth the per-finding detail call.
    findings = collect(
        window_hours=args.window_hours,
        should_enrich=lambda fingerprint: not already_reported(fingerprint),
    )
    new_findings = filter_new(findings)
    written, quarantined = 0, 0
    for finding in new_findings:
        report = Report.from_finding(finding, state="seeded", body=(
            "Semeado na primeira rodada — dívida pré-existente, ainda não investigada. "
            "Este achado já tinha atividade antes do Houston começar a rastreá-lo."
        ))
        result = write_report(report)
        if result.written:
            written += 1
        else:
            quarantined += 1
            print(f"  quarantined {finding.fingerprint}: {result.pii_hits}", file=sys.stderr)
    print(f"seeded {written} reports ({len(findings)} findings, "
          f"{len(findings) - len(new_findings)} already had a report, "
          f"{quarantined} quarantined)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Collects, dedups, and caps — prints what would be investigated.
    Does not invoke the agent yet (E4); that step costs Claude Code usage
    quota per ADR-0001 and is run deliberately, not on every `run`.

    "Needs investigation" includes findings with no report yet AND
    existing reports still in state: seeded/incomplete -- a seeded report
    has no real evidence/cause, and treating "has a file" as "done
    forever" meant it could never get one (ADR-0010)."""
    findings = collect(
        window_hours=args.window_hours, should_enrich=needs_investigation,
    )
    new_findings = filter_needing_investigation(findings)
    kept, dropped = cap(new_findings, max_findings=args.max_findings)
    print(f"{len(findings)} findings total, {len(new_findings)} needing investigation, "
          f"{len(kept)} to investigate, {dropped} dropped by cap")
    for f in kept:
        print(f"  {f.fingerprint}  {f.service}  {f.reason}  count={f.observed_count}")
    return 0



def cmd_metrics(args: argparse.Namespace) -> int:
    reports = load_all_reports()
    if not reports:
        print("no reports yet — run `houston seed` or `houston run` first")
        return 0
    m = compute(reports)
    print(f"total reports: {m.total}")
    for state, count in sorted(m.by_state.items()):
        print(f"  {state}: {count}")
    fp = f"{m.false_positive_rate:.1%}" if m.false_positive_rate is not None else "n/a (no promoted+discarded yet)"
    print(f"false-positive rate: {fp}")
    print(f"reports carrying an issue link: {m.with_issue_link}")
    print(f"spend total: ${m.usd_total:.4f}   mean ${m.usd_mean:.4f}/paid finding   "
          f"p50=${m.usd_p50:.4f}  p95=${m.usd_p95:.4f}")
    if m.usd_by_state:
        by_state = "  ".join(
            f"{state}=${spent:.4f}" for state, spent in sorted(m.usd_by_state.items())
        )
        print(f"spend by state: {by_state}")
    print(f"input tokens  p50={m.input_tokens_p50:.0f}  p95={m.input_tokens_p95:.0f}")
    print(f"duration (s)  p50={m.duration_s_p50:.1f}  p95={m.duration_s_p95:.1f}")

    can_close, pending = can_close_phase(reports)
    if not can_close:
        breakdown = ", ".join(
            f"{m.by_state[state]} {state}"
            for state in BLOCKING_STATES if m.by_state.get(state)
        )
        print(f"\nphase CANNOT close: {pending} report(s) still owe work ({breakdown})")
        return 1
    print(f"\nphase can close: no report left in {'/'.join(BLOCKING_STATES)}")
    return 0



def cmd_investigate(args: argparse.Namespace) -> int:
    """Runs the E4 agent for real, one claude -p subprocess per finding.
    Costs money/quota per ADR-0001 -- default cap is deliberately small.
    Never fabricates a result: a timeout or failure writes state:
    incomplete, not a guessed report.

    Targets findings needing investigation (no report yet, or an existing
    report still state: seeded/incomplete) -- not just brand-new signal.
    A seeded report is overwritten with the real investigation; ADR-0010."""
    findings = collect(
        window_hours=args.window_hours, should_enrich=needs_investigation,
    )
    new_findings = filter_needing_investigation(findings)
    kept, dropped = cap(new_findings, max_findings=args.max_findings)
    if not kept:
        print("nothing needs investigation")
        return 0

    print(f"investigating {len(kept)} of {len(new_findings)} findings needing it "
          f"({dropped} dropped by cap) -- {args.model} @ effort {args.effort}, "
          f"max ${args.max_budget_usd} each, {args.timeout_s}s timeout each")
    total_usd = 0.0
    for i, finding in enumerate(kept, 1):
        print(f"  [{i}/{len(kept)}] {finding.fingerprint} ({finding.service}, "
              f"{finding.reason})...", end=" ", flush=True)
        target_repo = (resolve_repo(finding.service) or {}).get("repo")
        result = agent_investigate(
            finding, max_budget_usd=args.max_budget_usd, timeout_s=args.timeout_s,
            target_repo=target_repo, model=args.model, effort=args.effort,
        )
        total_usd += result.usd
        if result.warnings:
            print(f"\n    WARNING: unresolved timestamp marker(s): {result.warnings}",
                  file=sys.stderr)
        if result.state == "incomplete":
            report = Report.from_finding(finding, state="incomplete", body=(
                f"Investigação não foi concluída: {result.error}"
            ))
        else:
            report = Report.from_finding(finding, state="new", body=result.body)
        report.cost.input_tokens = result.input_tokens
        report.cost.output_tokens = result.output_tokens
        report.cost.cache_read_input_tokens = result.cache_read_input_tokens
        report.cost.cache_creation_input_tokens = result.cache_creation_input_tokens
        report.cost.duration_s = result.duration_s
        report.cost.usd = result.usd
        report.cost.model = result.model
        write_result = write_report(report)
        if write_result.written:
            print(f"${result.usd:.4f}, {result.state}")
        elif write_result.record_path:
            print(f"QUARANTINED ({write_result.pii_hits}), ${result.usd:.4f} "
                  f"recorded in {write_result.record_path.name}")
        else:
            print(f"QUARANTINED ({write_result.pii_hits}), ${result.usd:.4f} "
                  f"NOT recorded: the stub itself tripped the gate", file=sys.stderr)

    print(f"total spend this run: ${total_usd:.4f}")
    return 0



def issue_title(report: dict) -> str:
    """Names the error, in the shape the backlog reads.

    `reason` is the diagnostic label (error_type / monitor name / k8s
    Reason); novelty is a separate field, so the title names the error
    instead of naming how new it is."""
    novelty = "regression: " if report.get("novelty") == "regression" else ""
    return (
        f"[{report['source']}] {novelty}{report['reason']} "
        f"in {report.get('service') or 'unknown service'}"
    )


def active_gh_account() -> str | None:
    """The account `gh` would act as, or None when it cannot be read.

    A 404 on a private Medprev repo is almost always this flipped to the
    personal account, and by then half the work has already happened."""
    result = subprocess.run(
        ["gh", "auth", "status", "--active"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    match = re.search(r"Logged in to \S+ account (\S+)", result.stdout + result.stderr)
    return match.group(1) if match else None


def promotion_blockers(report: dict, issue_body: str, account: str | None) -> list[str]:
    """Everything that must be true before an issue reaches the shared
    backlog. Each one fails closed: filing is outward-facing, and undoing
    it means a human closing an issue other people already saw."""
    blockers = []
    if account != ISSUE_ACCOUNT:
        blockers.append(
            f"active gh account is {account or 'unreadable'}, not {ISSUE_ACCOUNT} "
            f"-- run: gh auth switch --user {ISSUE_ACCOUNT}"
        )
    if report.get("issue"):
        blockers.append(f"report already carries issue: {report['issue']}")
    if report.get("state") == QUARANTINED_STATE:
        blockers.append(
            "report is quarantined -- its body is the redaction record, "
            "not an investigation (ADR-0015)"
        )
    raw = [marker for marker in _UNEXPANDED_MARKERS if marker in issue_body]
    if raw:
        blockers.append(f"issue body carries unexpanded markers: {', '.join(raw)}")
    return blockers


def create_issue(title: str, body: str) -> str | None:
    """Files the issue and returns its URL, or None on failure.

    Arguments go through argv, never a shell, so the body needs no quoting
    -- the printed form is the one a human pastes into a shell, and only
    that one is escaped."""
    result = subprocess.run(
        ["gh", "issue", "create", "--repo", ISSUE_REPO, "--title", title,
         "--label", ISSUE_LABEL, "--body", body],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return None
    urls = [line.strip() for line in result.stdout.splitlines()
            if line.strip().startswith("http")]
    return urls[-1] if urls else None


def cmd_promote(args: argparse.Namespace) -> int:
    """Prints a ready gh issue create command for a report, and with
    --create runs it and records the result.

    Promoting stays a human gesture: the decision "actionable or noise" is
    the instrument that measures the false-positive rate. What --create
    removes is the typing -- filing the issue and writing `issue:` +
    `state: promoted` back, the step that is easy to forget precisely
    because it is separate from the command (ADR-0028)."""
    path = report_path(args.fingerprint)
    if not path.exists():
        print(f"no report at {path}", file=sys.stderr)
        return 1
    report = read_report(path)
    text = path.read_text()
    _, _, body = text.split("---", 2)

    issue_body = extract_issue_body(body)
    title = issue_title(report)

    if not args.create:
        escaped_body = issue_body.replace("'", "'\\''")
        command_lines = [
            f"gh issue create --repo {ISSUE_REPO} \\",
            f"  --title '{title}' \\",
            f"  --label {ISSUE_LABEL} \\",
            f"  --body '{escaped_body}'",
        ]
        print("\n".join(command_lines))
        print(f"\n# run the command above, or re-run with --create to file the "
              f"issue and record it in {path} automatically")
        return 0

    blockers = promotion_blockers(report, issue_body, active_gh_account())
    if blockers:
        for blocker in blockers:
            print(f"refusing to promote: {blocker}", file=sys.stderr)
        return 1

    url = create_issue(title, issue_body)
    if url is None:
        print("gh issue create failed -- report left untouched", file=sys.stderr)
        return 1

    update_front_matter(path, issue=url, state="promoted")
    print(f"issue: {url}")
    print(f"{path}: state: promoted")
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    """Creates a PR that fixes a promoted finding. Costs money — runs a
    claude -p subprocess with code tools against the target service's repo."""
    path = report_path(args.fingerprint)
    if not path.exists():
        print(f"no report at {path}", file=sys.stderr)
        return 1

    report = read_report(path)
    if report.get("state") != "promoted":
        print(f"report state is '{report.get('state')}', not 'promoted'", file=sys.stderr)
        return 1

    issue_url = args.issue or report.get("issue")
    if not issue_url:
        print("no issue URL: pass --issue <url> or set the issue: field in the report",
              file=sys.stderr)
        return 1

    text = path.read_text()
    service = report.get("service")
    repo_info = resolve_repo(service, text)
    if repo_info is None:
        print(f"service '{service}' does not map to a fixable repo", file=sys.stderr)
        return 1

    print(f"fixing {args.fingerprint}")
    print(f"  repo: {repo_info['repo']}  path: {repo_info['path']}")
    print(f"  issue: {issue_url}")
    print(f"  model: {args.model} @ effort {args.effort}")
    print(f"  budget: ${args.max_budget_usd}  timeout: {args.timeout_s}s")

    result = agent_fix(
        fingerprint=args.fingerprint,
        report_markdown=text,
        issue_url=issue_url,
        repo_info=repo_info,
        max_budget_usd=args.max_budget_usd,
        timeout_s=args.timeout_s,
        model=args.model,
        effort=args.effort,
    )

    print(f"  state: {result.state}  cost: ${result.usd:.4f}")
    if result.pr_url:
        print(f"  PR: {result.pr_url}")
        subprocess.run(
            ["gh", "issue", "comment", issue_url, "--body",
             f"PR aberto pelo Houston fix agent: {result.pr_url}"],
            check=False, capture_output=True,
        )
        update_front_matter(path, fix_pr=result.pr_url, fix_state=result.state)
    elif result.error:
        print(f"  error: {result.error}", file=sys.stderr)
        update_front_matter(path, fix_pr=None, fix_state="incomplete")

    return 0 if result.pr_url else 1


def update_front_matter(path, **fields):
    """Writes structured fields back into an existing report.

    Values here are code-owned -- a URL `gh` printed, a state this CLI
    chose -- never model text, so this does not re-run the PII gate over
    a body that already passed it at write time."""
    import yaml as _yaml
    text = path.read_text()
    _, front_raw, body = text.split("---", 2)
    fm = _yaml.safe_load(front_raw)
    fm.update(fields)
    yaml_block = _yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{yaml_block}---{body}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="houston")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_p = sub.add_parser("seed", help="record pre-existing debt without investigating")
    seed_p.add_argument("--window-hours", type=int, default=96)
    seed_p.set_defaults(func=cmd_seed)

    run_p = sub.add_parser("run", help="collect, dedup, cap — print what would be investigated")
    run_p.add_argument("--window-hours", type=int, default=96)
    run_p.add_argument("--max-findings", type=int, default=15)
    run_p.set_defaults(func=cmd_run)

    metrics_p = sub.add_parser("metrics", help="compute FP rate, cost, and phase-close readiness")
    metrics_p.set_defaults(func=cmd_metrics)

    inv_p = sub.add_parser("investigate", help="run the real agent on capped new findings (costs money)")
    inv_p.add_argument("--window-hours", type=int, default=96)
    inv_p.add_argument("--max-findings", type=int, default=5, help="deliberately small default -- override once you trust the cost")
    inv_p.add_argument("--max-budget-usd", default=AGENT_DEFAULT_BUDGET,
                       help="sized for the investigation shape in ADR-0024, "
                            "not a round number -- see houston/agent.py")
    inv_p.add_argument("--timeout-s", type=int, default=300)
    inv_p.add_argument("--model", default=AGENT_DEFAULT_MODEL,
                       help="pinned, never inherited from the operator's Claude Code "
                            "settings -- raise --max-budget-usd if you move up a tier")
    inv_p.add_argument("--effort", default=AGENT_DEFAULT_EFFORT,
                       choices=["low", "medium", "high", "xhigh", "max"])
    inv_p.set_defaults(func=cmd_investigate)

    promote_p = sub.add_parser("promote", help="print a ready gh issue create for a report; --create files it")
    promote_p.add_argument("fingerprint")
    promote_p.add_argument("--create", action="store_true",
                           help="file the issue and record issue: + state: promoted "
                                "in the report -- without it, the command only prints")
    promote_p.set_defaults(func=cmd_promote)

    fix_p = sub.add_parser("fix", help="create a PR fixing a promoted finding (costs money)")
    fix_p.add_argument("fingerprint")
    fix_p.add_argument("--issue", help="GitHub issue URL (reads from front-matter if absent)")
    fix_p.add_argument("--max-budget-usd", default="3.00")
    fix_p.add_argument("--timeout-s", type=int, default=600)
    fix_p.add_argument("--model", default=FIX_DEFAULT_MODEL,
                       help="pinned, never inherited from the operator's Claude Code settings")
    fix_p.add_argument("--effort", default=FIX_DEFAULT_EFFORT,
                       choices=["low", "medium", "high", "xhigh", "max"])
    fix_p.set_defaults(func=cmd_fix)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
