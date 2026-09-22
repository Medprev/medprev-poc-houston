"""Pre-investigation triage behind a port (ADR-0035): one typed decision per
finding -- investigate, or likely noise -- from TypeSafe's Jev, a System
One model that returns calibrated probabilities instead of text.

Shadow mode only. A verdict is recorded on the report and measured by
`houston metrics` against the decision a human later makes; nothing here
drops, reorders, or skips a finding. ADR-0024's `UnauthorizedException` is
the case this exists for: a handled outcome modeled as an exception, which
cost a full `claude -p` investigation to classify as noise.

Three rules, each one a line in ADR-0035:

- **The state is a whitelist of front-matter fields.** `triage_state` reads
  a `Report`, never a `Finding`'s `raw` payload and never a body: the same
  line `scripts/generate_site.py` draws (ADR-0005), because this is a new
  third party receiving Datadog data. The whitelist is also what makes a
  verdict on an already-decided report honest -- `state`, `issue` and the
  body are exactly what it cannot see.
- **The PII gate runs before the network.** A state that trips
  `pii_gate.scan` is refused with no request made.
- **Fail open.** Every failure is a `TriageError`; the caller records no
  verdict and carries on. A triage outage never costs an investigation.

The request and response shapes are the public ones (`POST
/v1/systemone`, a `choice` question, `answers`/`usage` back) and live in
`_request_body` / `_verdict_from` and nowhere else, so confirming them
against a live key is a change to two functions and one fixture."""
import json
import os
from dataclasses import dataclass, field
from typing import Protocol

import requests

from houston.datadog_client import _with_retries
from houston.frontmatter import Report, Triage
from houston.pii_gate import scan

DEFAULT_MODEL = "jev-latest"
API_URL = "https://api.typesafe.ai/v1/systemone"
QUESTION = "decision"
INVESTIGATE = "investigate"
LIKELY_NOISE = "likely_noise"
_TIMEOUT_S = 10

# Published price: input only, output free. Kept here so `usd` is computed
# by code from the billed token count, the rule every other cost in a
# report already follows (ADR-0013).
USD_PER_MILLION_INPUT = 0.042

# TypeSafe's suggested bands: act above the auto floor, review in the
# middle, hand to a person below. Recorded, not acted on, in shadow mode.
AUTO_FLOOR = 0.72
HUMAN_BELOW = 0.45

_CRITERIA = {
    INVESTIGATE: (
        "A real fault worth a root-cause investigation: an unhandled error, "
        "a regression, a crash, or a failure users or operators feel."
    ),
    LIKELY_NOISE: (
        "An expected outcome surfaced as an error: a handled exception such "
        "as an auth refusal or validation failure, a routine Kubernetes "
        "lifecycle event, or a self-resolving alert flap."
    ),
}

_INSTRUCTIONS = (
    "This is one production signal from Datadog (Error Tracking, a monitor "
    "alert, or Kubernetes events), before anyone has investigated it. "
    "Decide whether it deserves a paid root-cause investigation."
)


class TriageError(Exception):
    """Any reason no verdict exists: refused by the PII gate, a transport
    failure, a response in a shape this module does not recognize."""


class Classifier(Protocol):
    def classify(self, report: Report) -> Triage:
        """Returns a verdict or raises TriageError. Never anything else --
        the pipeline's fail-open handling catches TriageError only."""
        ...


def band(confidence: float) -> str:
    if confidence >= AUTO_FLOOR:
        return "act"
    if confidence < HUMAN_BELOW:
        return "human"
    return "review"


def triage_state(report: Report) -> dict:
    """What Jev sees. Every value is a front-matter field the report
    already carries, so nothing leaves here that `reports/` does not
    already hold in git behind the PII gate."""
    window_h = (report.window_to_ms - report.window_from_ms) / 3_600_000
    active_h = (
        (report.last_seen_ms - report.first_seen_ms) / 3_600_000
        if report.first_seen_ms and report.last_seen_ms else None
    )
    return {
        "source": report.source,
        "reason": report.reason,
        "service": report.service,
        "severity": report.severity,
        "novelty": report.novelty,
        "observed_count_in_window": report.observed_count,
        "window_hours": round(window_h, 1) if window_h > 0 else None,
        "active_hours": round(active_h, 1) if active_h is not None else None,
    }


def _request_body(state: dict, model: str) -> dict:
    return {
        "model": model,
        "state": state,
        "questions": {
            QUESTION: {
                "type": "choice",
                "instructions": _INSTRUCTIONS,
                "criteria": _CRITERIA,
            },
        },
    }


def _verdict_from(payload: dict) -> Triage:
    try:
        answer = payload["answers"][QUESTION]
        decision = answer["choice"]
        probabilities = {k: float(v) for k, v in answer["probabilities"].items()}
        confidence = float(answer["confidence"])
        input_tokens = int((payload.get("usage") or {}).get("input_tokens") or 0)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise TriageError(f"unrecognized Jev response: {exc!r}") from exc
    if decision not in _CRITERIA:
        raise TriageError(f"Jev answered outside the criteria: {decision!r}")
    return Triage(
        decision=decision,
        confidence=confidence,
        probabilities=probabilities,
        model=payload.get("model"),
        input_tokens=input_tokens,
        usd=input_tokens * USD_PER_MILLION_INPUT / 1_000_000,
    )


@dataclass
class JevClassifier:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    url: str = API_URL
    session: requests.Session = field(default_factory=requests.Session, repr=False)

    @classmethod
    def from_env(cls) -> "JevClassifier":
        api_key = os.environ.get("TYPESAFE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "TYPESAFE_API_KEY missing -- add it to .env to run triage "
                "(ADR-0035); without it, leave --triage off."
            )
        return cls(api_key=api_key)

    def classify(self, report: Report) -> Triage:
        state = triage_state(report)
        hits = scan(json.dumps(state, ensure_ascii=False))
        if hits:
            raise TriageError(f"state refused by the PII gate: {hits}")
        body = _request_body(state, self.model)
        try:
            resp = _with_retries(lambda: self.session.post(
                self.url, json=body, timeout=_TIMEOUT_S,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ))
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise TriageError(f"Jev request failed: {exc}") from exc
        return _verdict_from(payload)


def triage_or_none(
    classifier: Classifier | None, report: Report,
) -> tuple[Triage | None, str | None]:
    """The fail-open call: a verdict, or None plus the reason as a warning.
    Catches TriageError only -- anything else is a bug in a classifier, not
    an outage, and should surface as one."""
    if classifier is None:
        return None, None
    try:
        return classifier.classify(report), None
    except TriageError as exc:
        return None, str(exc)
