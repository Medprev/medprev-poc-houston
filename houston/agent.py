"""E4 — one `claude -p` subprocess per finding. Read-only tools only; Bash,
Write, and Edit are denied, so nothing the model produces reaches disk
except through the PII gate in houston.frontmatter.

Bounded by --max-budget-usd and a wall-clock timeout, not --max-turns —
see ADR-0006: the turn-count flag the original design assumed does not
exist in the installed CLI (2.1.251).
"""
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from houston.models import Finding

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "houston" / "allowedtools.txt"

DEFAULT_MAX_BUDGET_USD = "0.50"
DEFAULT_TIMEOUT_S = 300

PROMPT = """You are investigating one observability finding from Datadog. \
You have read-only tools to look up more context (logs, spans, related \
issues) if useful — you do not have to use them if the finding is already \
clear. Do not guess at evidence you have not actually queried.

Respond in English, in this exact structure:

## Root cause
One paragraph, plain language.

## Evidence
A bullet list, each bullet a claim followed by the exact query or tool call \
that supports it. Never paste raw log lines or user data — reference where \
to find it, not the content itself.

## Recommended action
One or two sentences.

## Issue body
A ready-to-paste GitHub issue body in 5W2H format (What/Why/Where/When/Who/How/How much), \
under 50 lines.

The finding, as JSON, follows on stdin.
"""


@dataclass
class InvestigationResult:
    body: str | None
    input_tokens: int
    output_tokens: int
    duration_s: float
    usd: float
    state: str  # "new" (investigated) | "incomplete" (failed/timed out)
    error: str | None = None


def _load_allowlist() -> str:
    names = [
        line.strip()
        for line in ALLOWLIST_PATH.read_text().splitlines()
        if line.strip()
    ]
    return ",".join(names)


def investigate(
    finding: Finding,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> InvestigationResult:
    env = {**os.environ}
    env.pop("CLAUDECODE", None)  # allow nesting claude -p inside a session

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--allowedTools", _load_allowlist(),
        "--disallowedTools", "Bash,Write,Edit",
        "--max-budget-usd", max_budget_usd,
        PROMPT,
    ]
    stdin_payload = json.dumps({
        "fingerprint": finding.fingerprint,
        "source": finding.source,
        "service": finding.service,
        "reason": finding.reason,
        "query": finding.query,
        "observed_count": finding.observed_count,
        "first_seen_ms": finding.first_seen_ms,
        "last_seen_ms": finding.last_seen_ms,
        "severity": finding.severity,
        "regressed": finding.regressed,
    })

    try:
        proc = subprocess.run(
            cmd, input=stdin_payload, capture_output=True, text=True,
            env=env, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0,
            duration_s=float(timeout_s), usd=0.0, state="incomplete",
            error=f"timed out after {timeout_s}s",
        )

    if proc.returncode != 0:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0, duration_s=0.0,
            usd=0.0, state="incomplete", error=proc.stderr[-2000:],
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0, duration_s=0.0,
            usd=0.0, state="incomplete",
            error=f"non-JSON stdout: {proc.stdout[:500]}",
        )

    usage = payload.get("usage", {})
    return InvestigationResult(
        body=payload.get("result"),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        duration_s=payload.get("duration_ms", 0) / 1000,
        usd=payload.get("total_cost_usd", 0.0),
        state="new",
    )
