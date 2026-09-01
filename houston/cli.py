"""houston — CLI entrypoint. `python -m houston.cli <command>`."""
import argparse
import sys

from houston.agent import investigate as agent_investigate
from houston.collector import collect
from houston.dedup import cap, filter_needing_investigation, filter_new, report_path
from houston.frontmatter import Report, read_report, write_report
from houston.metrics import can_close_phase, compute, load_all_reports


def cmd_seed(args: argparse.Namespace) -> int:
    """Records pre-existing debt as state: seeded, investigating nothing.
    This is the one-time bootstrap so the backlog that existed before this
    tool did doesn't get treated as new signal on day one."""
    findings = collect(window_hours=args.window_hours)
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
    findings = collect(window_hours=args.window_hours)
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
    print(f"already had an open issue: {m.already_had_issue}")
    print(f"input tokens  p50={m.input_tokens_p50:.0f}  p95={m.input_tokens_p95:.0f}")
    print(f"duration (s)  p50={m.duration_s_p50:.1f}  p95={m.duration_s_p95:.1f}")

    can_close, pending = can_close_phase(reports)
    if not can_close:
        print(f"\nphase CANNOT close: {pending} report(s) still state: new")
        return 1
    print("\nphase can close: no report left in state: new")
    return 0



def cmd_investigate(args: argparse.Namespace) -> int:
    """Runs the E4 agent for real, one claude -p subprocess per finding.
    Costs money/quota per ADR-0001 -- default cap is deliberately small.
    Never fabricates a result: a timeout or failure writes state:
    incomplete, not a guessed report.

    Targets findings needing investigation (no report yet, or an existing
    report still state: seeded/incomplete) -- not just brand-new signal.
    A seeded report is overwritten with the real investigation; ADR-0010."""
    findings = collect(window_hours=args.window_hours)
    new_findings = filter_needing_investigation(findings)
    kept, dropped = cap(new_findings, max_findings=args.max_findings)
    if not kept:
        print("nothing needs investigation")
        return 0

    print(f"investigating {len(kept)} of {len(new_findings)} findings needing it "
          f"({dropped} dropped by cap) -- max ${args.max_budget_usd} each, "
          f"{args.timeout_s}s timeout each")
    total_usd = 0.0
    for i, finding in enumerate(kept, 1):
        print(f"  [{i}/{len(kept)}] {finding.fingerprint} ({finding.service}, "
              f"{finding.reason})...", end=" ", flush=True)
        result = agent_investigate(
            finding, max_budget_usd=args.max_budget_usd, timeout_s=args.timeout_s,
        )
        total_usd += result.usd
        if result.state == "incomplete":
            report = Report.from_finding(finding, state="incomplete", body=(
                f"Investigação não foi concluída: {result.error}"
            ))
        else:
            report = Report.from_finding(finding, state="new", body=result.body)
        report.cost.input_tokens = result.input_tokens
        report.cost.output_tokens = result.output_tokens
        report.cost.duration_s = result.duration_s
        report.cost.usd = result.usd
        write_result = write_report(report)
        if write_result.written:
            print(f"${result.usd:.2f}, {result.state}")
        else:
            print(f"QUARANTINED ({write_result.pii_hits})")

    print(f"total spend this run: ${total_usd:.2f}")
    return 0



def cmd_promote(args: argparse.Namespace) -> int:
    """Prints a ready gh issue create command for a report. Never runs it --
    promoting is a human gesture and the instrument that measures the
    false-positive rate (see the plan's own E6 design)."""
    path = report_path(args.fingerprint)
    if not path.exists():
        print(f"no report at {path}", file=sys.stderr)
        return 1
    report = read_report(path)
    text = path.read_text()
    _, _, body = text.split("---", 2)

    # pull the "## Issue body" section out of the investigation body, if present
    issue_body = body
    if "## Issue body" in body:
        issue_body = body.split("## Issue body", 1)[1].strip()

    title = f"[{report['source']}] {report['reason']} in {report.get('service') or 'unknown service'}"
    escaped_body = issue_body.replace("'", "'\\''")
    command_lines = [
        "gh issue create --repo Medprev/medprev-product-backlog \\",
        f"  --title '{title}' \\",
        f"  --body '{escaped_body}'",
    ]
    print("\n".join(command_lines))
    print(f"\n# after running the command above, paste the issue URL into "
          f"{path}'s front-matter (issue: field) and set state: promoted")
    return 0


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
    inv_p.add_argument("--max-budget-usd", default="0.50")
    inv_p.add_argument("--timeout-s", type=int, default=300)
    inv_p.set_defaults(func=cmd_investigate)

    promote_p = sub.add_parser("promote", help="print (never run) a ready gh issue create for a report")
    promote_p.add_argument("fingerprint")
    promote_p.set_defaults(func=cmd_promote)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
