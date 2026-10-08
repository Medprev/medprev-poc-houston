"""E8 (goal-driven) — static GitHub Pages summary.

Redaction rule (ADR-0005): this page renders ONLY structured front-matter
fields (fingerprint, service, source, reason, severity, state, dates,
promoted issue link). It never reads a report's body — evidence, root
cause, and error messages stay inside the repository. Front-matter fields
are closed-vocabulary/structured data that already passed the PII gate as
part of the whole rendered file; the body is free text and is exactly the
part of a report most likely to carry something the regex gate missed
(the documented proper-name gap in ADR-0003).
"""
import html
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from houston.frontmatter import Report
from houston.metrics import compute, load_all_reports
from houston.report_state import DISPLAY_ORDER

# Named "site/", not "docs/" — this repo's docs/ already holds ADRs and the
# E0 verification writeup; the generated Pages output needs its own folder.
OUTPUT_DIR = ROOT / "site"

_STATE_ORDER = [s.value for s in DISPLAY_ORDER]


def _fmt_ms(ms: int | None) -> str:
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _row(r: Report) -> str:
    fp = html.escape(r.fingerprint)
    short_fp = fp[:18] + "…" if len(fp) > 19 else fp
    service = html.escape(r.service or "—")
    issue_html = (
        f'<a href="{html.escape(r.issue)}">{html.escape(r.issue)}</a>' if r.issue else "—"
    )
    return (
        "<tr>"
        f'<td class="mono">{short_fp}</td>'
        f"<td>{service}</td>"
        f"<td>{html.escape(r.source)}</td>"
        f"<td>{html.escape(r.reason)}</td>"
        f'<td>{html.escape(r.novelty or "—")}</td>'
        f'<td><span class="sev sev-{html.escape(r.severity)}">{html.escape(r.severity)}</span></td>'
        f'<td><span class="state state-{html.escape(r.state)}">{html.escape(r.state)}</span></td>'
        f"<td>{_fmt_ms(r.first_seen_ms)}</td>"
        f"<td>{issue_html}</td>"
        "</tr>"
    )


def render(reports: list[Report]) -> str:
    m = compute(reports)
    fp_rate = f"{m.false_positive_rate:.1%}" if m.false_positive_rate is not None else "n/a"
    state_counts = "".join(
        f'<div class="stat"><span class="stat-n">{m.by_state.get(s, 0)}</span>'
        f'<span class="stat-l">{s}</span></div>'
        for s in _STATE_ORDER if s in m.by_state
    )
    rows = "\n".join(_row(r) for r in sorted(
        reports, key=lambda r: r.first_seen_ms or 0, reverse=True
    ))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Houston PoC — incident summary</title>
<style>
:root{{color-scheme:light dark;--ink:#101a22;--muted:#6a8394;--rule:#d8e1e7;--bg:#faf9f5;--surface:#fff;
--crit:#a8402a;--warn:#8a6410;--ok:#2c6b52;--accent:#1b5e8c}}
@media (prefers-color-scheme:dark){{:root{{--ink:#e6edf2;--muted:#8ea3af;--rule:#2a3a44;--bg:#0e1519;--surface:#151e24}}}}
*{{box-sizing:border-box}}
body{{margin:0;padding:32px 20px 80px;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.wrap{{max-width:960px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 6px}}
.sub{{color:var(--muted);margin:0 0 28px;font-size:14px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:28px}}
.stat{{background:var(--surface);border:1px solid var(--rule);border-radius:6px;
padding:12px 16px;min-width:90px}}
.stat-n{{display:block;font-size:22px;font-weight:700}}
.stat-l{{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;
border-bottom:1.5px solid var(--rule);padding:0 10px 8px 0}}
td{{padding:9px 10px 9px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.mono{{font-family:ui-monospace,monospace;font-size:12px;color:var(--muted)}}
.sev,.state{{font-size:11px;padding:2px 6px;border-radius:3px;border:1px solid currentColor}}
.sev-high,.sev-critical{{color:var(--crit)}} .sev-medium{{color:var(--warn)}} .sev-low{{color:var(--ok)}}
.state-new{{color:var(--accent)}} .state-promoted{{color:var(--ok)}} .state-discarded{{color:var(--muted)}}
.state-seeded{{color:var(--muted)}} .state-incomplete{{color:var(--crit)}}
.state-quarantined{{color:var(--warn)}}
footer{{margin-top:24px;color:var(--muted);font-size:12px}}
</style></head>
<body><div class="wrap">
<h1>Houston PoC — incident summary</h1>
<p class="sub">Read-only summary of {m.total} tracked findings. False-positive rate: {fp_rate}.
Structured fields only — no evidence, root cause, or error text is shown here (see the private repo for full reports).</p>
<div class="stats">{state_counts}</div>
<table>
<thead><tr><th>Fingerprint</th><th>Service</th><th>Source</th><th>Reason</th><th>Novelty</th><th>Severity</th><th>State</th><th>First seen</th><th>Issue</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<footer>Generated {generated_at} from reports/*.md front-matter. carlacurymed/medprev-poc-houston (private repo, public summary).</footer>
</div></body></html>
"""


def main() -> None:
    reports = load_all_reports()
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(render(reports))
    (OUTPUT_DIR / ".nojekyll").write_text("")
    print(f"wrote {OUTPUT_DIR / 'index.html'} ({len(reports)} reports)")


if __name__ == "__main__":
    main()
