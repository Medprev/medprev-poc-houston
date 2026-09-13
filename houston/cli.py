"""houston — CLI entrypoint. `python -m houston.cli <command>`.

Argparse, wiring, and printing only -- the use cases themselves live in
houston/pipeline.py (Move C, ADR-0032). The three `gh` subprocess calls
(`active_gh_account`, `create_issue`, the fix-PR issue comment) stay here
rather than moving into the pipeline: they're plumbing to an external
tool, the same reason the five `git` calls in fix_agent.py stayed put
during Move B."""
import argparse
import re
import subprocess
import sys

from houston.agent import DEFAULT_EFFORT as AGENT_DEFAULT_EFFORT
from houston.agent import DEFAULT_MAX_BUDGET_USD as AGENT_DEFAULT_BUDGET
from houston.agent import DEFAULT_MODEL as AGENT_DEFAULT_MODEL
from houston.agent import investigate as agent_investigate
from houston.collector import collect
from houston.fix_agent import DEFAULT_EFFORT as FIX_DEFAULT_EFFORT
from houston.fix_agent import DEFAULT_MODEL as FIX_DEFAULT_MODEL
from houston.fix_agent import fix as agent_fix
from houston.fix_agent import resolve_repo
from houston.metrics import BLOCKING_STATES, can_close_phase, compute, load_all_reports
from houston.model_runner import DEFAULT_RUNNER
from houston.pipeline import (
    PipelineError,
    build_promote_command,
    fix_report,
    investigate_findings,
    plan_run,
    promote_report,
    seed,
)

ISSUE_REPO = "Medprev/medprev-product-backlog"
ISSUE_LABEL = "AIOPS"
ISSUE_ACCOUNT = "carlacurymed"


def cmd_seed(args: argparse.Namespace) -> int:
    outcome = seed(collect, window_hours=args.window_hours)
    for fingerprint, hits in outcome.quarantined:
        print(f"  quarantined {fingerprint}: {hits}", file=sys.stderr)
    print(f"seeded {outcome.written} reports ({outcome.findings} findings, "
          f"{outcome.already_reported} already had a report, "
          f"{len(outcome.quarantined)} quarantined)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan = plan_run(collect, window_hours=args.window_hours, max_findings=args.max_findings)
    print(f"{plan.total} findings total, {plan.needing} needing investigation, "
          f"{len(plan.kept)} to investigate, {plan.dropped} dropped by cap")
    for f in plan.kept:
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
    Costs money/quota per ADR-0001 -- default cap is deliberately small."""
    def on_start(i, total, finding):
        print(f"  [{i}/{total}] {finding.fingerprint} ({finding.service}, "
              f"{finding.reason})...", end=" ", flush=True)

    run = investigate_findings(
        collect, agent_investigate, resolve_repo,
        window_hours=args.window_hours, max_findings=args.max_findings,
        max_budget_usd=args.max_budget_usd, timeout_s=args.timeout_s,
        model=args.model, effort=args.effort, runner=DEFAULT_RUNNER,
        on_start=on_start,
    )
    if not run.plan.kept:
        print("nothing needs investigation")
        return 0

    print(f"investigating {len(run.plan.kept)} of {run.plan.needing} findings needing it "
          f"({run.plan.dropped} dropped by cap) -- {args.model} @ effort {args.effort}, "
          f"max ${args.max_budget_usd} each, {args.timeout_s}s timeout each")
    for outcome in run.outcomes:
        if outcome.warnings:
            print(f"\n    WARNING: unresolved timestamp marker(s): {outcome.warnings}",
                  file=sys.stderr)
        write_result = outcome.write
        if write_result.written:
            print(f"${outcome.usd:.4f}, {outcome.state}")
        elif write_result.record_path:
            print(f"QUARANTINED ({write_result.pii_hits}), ${outcome.usd:.4f} "
                  f"recorded in {write_result.record_path.name}")
        else:
            print(f"QUARANTINED ({write_result.pii_hits}), ${outcome.usd:.4f} "
                  f"NOT recorded: the stub itself tripped the gate", file=sys.stderr)

    print(f"total spend this run: ${run.total_usd:.4f}")
    return 0


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
    try:
        command = build_promote_command(args.fingerprint)
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not args.create:
        escaped_body = command.issue_body.replace("'", "'\\''")
        command_lines = [
            f"gh issue create --repo {ISSUE_REPO} \\",
            f"  --title '{command.title}' \\",
            f"  --label {ISSUE_LABEL} \\",
            f"  --body '{escaped_body}'",
        ]
        print("\n".join(command_lines))
        print(f"\n# run the command above, or re-run with --create to file the "
              f"issue and record it in {command.path} automatically")
        return 0

    try:
        url = promote_report(
            args.fingerprint, account=active_gh_account(), required_account=ISSUE_ACCOUNT,
            create_issue_fn=create_issue,
        )
    except PipelineError as exc:
        print(f"refusing to promote: {exc}", file=sys.stderr)
        return 1

    print(f"issue: {url}")
    print(f"{command.path}: state: promoted")
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    """Creates a PR that fixes a promoted finding. Costs money — runs a
    claude -p subprocess with code tools against the target service's repo."""
    def notify(issue_url: str, message: str) -> None:
        subprocess.run(
            ["gh", "issue", "comment", issue_url, "--body", message],
            check=False, capture_output=True,
        )

    try:
        outcome = fix_report(
            args.fingerprint, issue=args.issue, fix_fn=agent_fix,
            resolve_repo_fn=resolve_repo, runner=DEFAULT_RUNNER,
            max_budget_usd=args.max_budget_usd, timeout_s=args.timeout_s,
            model=args.model, effort=args.effort, notify_fn=notify,
        )
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = outcome.result
    print(f"fixing {args.fingerprint}")
    print(f"  repo: {outcome.repo_info['repo']}  path: {outcome.repo_info['path']}")
    print(f"  issue: {outcome.issue_url}")
    print(f"  model: {args.model} @ effort {args.effort}")
    print(f"  budget: ${args.max_budget_usd}  timeout: {args.timeout_s}s")
    print(f"  state: {result.state}  cost: ${result.usd:.4f}")
    if result.pr_url:
        print(f"  PR: {result.pr_url}")
    elif result.error:
        print(f"  error: {result.error}", file=sys.stderr)

    return 0 if result.pr_url else 1


def main(argv: list[str] | None = None) -> int:
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
