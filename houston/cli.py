"""houston — CLI entrypoint. `python -m houston.cli <command>`."""
import argparse
import sys

from houston.collector import collect
from houston.dedup import cap, filter_new
from houston.frontmatter import Report, write_report
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
            "Seeded on first run — pre-existing debt, not investigated. "
            "This finding already had activity before Houston started tracking it."
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
    quota per ADR-0001 and is run deliberately, not on every `run`."""
    findings = collect(window_hours=args.window_hours)
    new_findings = filter_new(findings)
    kept, dropped = cap(new_findings, max_findings=args.max_findings)
    print(f"{len(findings)} findings total, {len(new_findings)} new, "
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

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
