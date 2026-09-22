"""Shadow-mode triage (ADR-0035): what Jev may see, how its answer is read,
and the rule that a triage failure never costs an investigation. No
network -- the Jev response is the public example shape, in
tests/fixtures/jev_choice_response.json."""
import json
from pathlib import Path

import pytest
import requests

from houston.agent import InvestigationResult
from houston.cli import main
from houston.frontmatter import Report, Triage, load_report, record_triage, write_report
from houston.metrics import compute
from houston.models import Finding
from houston.pipeline import investigate_findings, plan_run, triage_reports
from houston.triage import (
    INVESTIGATE,
    LIKELY_NOISE,
    JevClassifier,
    TriageError,
    _request_body,
    _verdict_from,
    band,
    triage_or_none,
    triage_state,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "jev_choice_response.json").read_text()
)


def _finding(fp="et-triage", **overrides) -> Finding:
    defaults = {
        "fingerprint": fp, "source": "error_tracking", "query": "env:production",
        "service": "medprev-rest-api", "reason": "UnauthorizedException",
        "first_seen_ms": 1_000, "last_seen_ms": 1_000 + 7_200_000,
        "observed_count": 15248, "severity": "medium", "regressed": False,
        "raw": {"message": "login failed for someone@example.com"},
        "window_from_ms": 0, "window_to_ms": 96 * 3_600_000,
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _verdict(decision=LIKELY_NOISE, confidence=0.8) -> Triage:
    return Triage(decision=decision, confidence=confidence,
                  probabilities={decision: confidence}, model="jev-1.13.0",
                  input_tokens=400, usd=400 * 0.042 / 1_000_000)


class FakeClassifier:
    def __init__(self, verdict=None, raises=None):
        self.verdict = verdict or _verdict()
        self.raises = raises
        self.seen: list[Report] = []

    def classify(self, report):
        self.seen.append(report)
        if self.raises is not None:
            raise self.raises
        return self.verdict


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts: list[dict] = []

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        return self.response


def _collect_fn(findings):
    def collect(*, window_hours, should_enrich=None):
        return findings
    return collect


# ---------------------------------------------------------------------------
# What leaves the process
# ---------------------------------------------------------------------------

def test_state_is_the_whitelist_and_never_raw_or_body():
    report = Report.from_finding(_finding(), body="corpo com someone@example.com")
    report.state = "promoted"
    report.issue = "https://github.com/Medprev/medprev-product-backlog/issues/1"

    state = triage_state(report)

    assert set(state) == {
        "source", "reason", "service", "severity", "novelty",
        "observed_count_in_window", "window_hours", "active_hours",
    }
    rendered = json.dumps(state)
    # `raw` and the body carry free text; `state`/`issue` are the human
    # decision the verdict is measured against.
    assert "example.com" not in rendered
    assert "promoted" not in rendered and "github.com" not in rendered
    assert state["window_hours"] == 96.0
    assert state["active_hours"] == 2.0


def test_request_body_asks_one_choice_question_over_the_two_labels():
    body = _request_body({"source": "monitor"}, "jev-latest")
    assert body["model"] == "jev-latest"
    question = body["questions"]["decision"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {INVESTIGATE, LIKELY_NOISE}


def test_pii_in_the_state_is_refused_before_any_request():
    session = FakeSession(FakeResponse(FIXTURE))
    classifier = JevClassifier(api_key="k", session=session)
    report = Report.from_finding(_finding(reason="Falha para someone@example.com"))

    with pytest.raises(TriageError, match="PII"):
        classifier.classify(report)
    assert session.posts == []


# ---------------------------------------------------------------------------
# Reading the answer
# ---------------------------------------------------------------------------

def test_verdict_reads_the_public_response_shape_and_prices_input_only():
    verdict = _verdict_from(FIXTURE)
    assert verdict.decision == LIKELY_NOISE
    assert verdict.confidence == 0.79
    assert verdict.probabilities == {"investigate": 0.14, "likely_noise": 0.86}
    assert verdict.model == "jev-1.13.0"
    assert verdict.input_tokens == 412
    assert verdict.usd == pytest.approx(412 * 0.042 / 1_000_000)


@pytest.mark.parametrize("payload", [
    {},
    {"answers": {"decision": {"choice": "likely_noise"}}},
    {"answers": {"decision": {**FIXTURE["answers"]["decision"], "choice": "escalate"}}},
    {"answers": {"decision": {**FIXTURE["answers"]["decision"], "confidence": "high"}}},
])
def test_an_unrecognized_response_is_a_triage_error_not_a_guess(payload):
    with pytest.raises(TriageError):
        _verdict_from(payload)


def test_classifier_posts_with_bearer_auth_and_returns_the_verdict():
    session = FakeSession(FakeResponse(FIXTURE))
    verdict = JevClassifier(api_key="secret", session=session).classify(
        Report.from_finding(_finding())
    )
    assert verdict.decision == LIKELY_NOISE
    (post,) = session.posts
    assert post["url"] == "https://api.typesafe.ai/v1/systemone"
    assert post["headers"]["Authorization"] == "Bearer secret"
    assert post["json"]["state"]["reason"] == "UnauthorizedException"


def test_an_http_error_becomes_a_triage_error():
    session = FakeSession(FakeResponse({}, status_code=401))
    with pytest.raises(TriageError, match="request failed"):
        JevClassifier(api_key="bad", session=session).classify(
            Report.from_finding(_finding())
        )


def test_triage_or_none_fails_open_on_triage_errors_only():
    report = Report.from_finding(_finding())
    assert triage_or_none(None, report) == (None, None)
    assert triage_or_none(FakeClassifier(raises=TriageError("down")), report) == (None, "down")
    with pytest.raises(ZeroDivisionError):
        triage_or_none(FakeClassifier(raises=ZeroDivisionError()), report)


@pytest.mark.parametrize("confidence,expected", [
    (0.72, "act"), (0.95, "act"), (0.71, "review"), (0.45, "review"), (0.44, "human"),
])
def test_bands_follow_the_published_thresholds(confidence, expected):
    assert band(confidence) == expected


def test_from_env_refuses_without_a_key():
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        JevClassifier.from_env()


# ---------------------------------------------------------------------------
# Front-matter
# ---------------------------------------------------------------------------

def test_a_report_without_a_verdict_renders_no_triage_key():
    assert "triage:" not in Report.from_finding(_finding()).to_markdown()


def test_a_verdict_round_trips_through_the_report(store):
    report = Report.from_finding(_finding(), body="x")
    report.triage = _verdict()
    result = write_report(report)
    assert load_report(result.path).triage == _verdict()


def test_record_triage_patches_the_verdict_and_leaves_the_body(store):
    result = write_report(Report.from_finding(_finding(), state="promoted", body="## Corpo\nfoo"))
    before = result.path.read_text()

    record_triage(result.path, _verdict())

    after = load_report(result.path)
    assert after.triage == _verdict()
    assert after.state == "promoted"
    assert before.split("---", 2)[2] == result.path.read_text().split("---", 2)[2]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _investigate_fn(f, **kwargs):
    return InvestigationResult(
        body="## Causa\nfoo", input_tokens=100, output_tokens=200,
        duration_s=5.0, usd=0.35, state="new", model="claude-sonnet-5",
    )


def _investigate(findings, classifier):
    return investigate_findings(
        _collect_fn(findings), _investigate_fn, resolve_repo_fn=lambda *a: None,
        window_hours=96, max_findings=5, max_budget_usd="0.50", timeout_s=300,
        model="sonnet", effort="medium", runner=object(), classifier=classifier,
    )


def test_shadow_mode_records_the_verdict_and_still_investigates(store):
    run = _investigate([_finding()], FakeClassifier(_verdict(LIKELY_NOISE, 0.95)))

    (outcome,) = run.outcomes
    # Even a high-confidence "noise" skips nothing in shadow mode.
    assert outcome.state == "new"
    assert load_report(outcome.write.path).triage.decision == LIKELY_NOISE


def test_a_triage_outage_costs_no_investigation(store):
    run = _investigate([_finding()], FakeClassifier(raises=TriageError("503")))

    (outcome,) = run.outcomes
    assert outcome.state == "new"
    assert load_report(outcome.write.path).triage is None
    assert run.plan.triage_warnings == {"et-triage": "503"}


def test_triage_runs_after_the_cap_so_it_cannot_change_what_is_kept(store):
    findings = [_finding(f"et-{i}") for i in range(3)]
    classifier = FakeClassifier()

    plan = plan_run(_collect_fn(findings), window_hours=96, max_findings=2,
                    classifier=classifier)

    assert len(plan.kept) == 2 and plan.dropped == 1
    assert [r.fingerprint for r in classifier.seen] == [f.fingerprint for f in plan.kept]
    assert plan.triage_usd == pytest.approx(2 * _verdict().usd)


def test_no_classifier_means_no_triage_at_all(store):
    run = _investigate([_finding()], None)
    assert run.plan.triage == {}
    assert "triage:" not in run.outcomes[0].write.path.read_text()


def test_backfill_triages_decided_and_seeded_reports_once(store):
    for fp, state in [("et-a", "promoted"), ("et-b", "discarded"),
                      ("et-c", "seeded"), ("et-d", "new")]:
        write_report(Report.from_finding(_finding(fp), state=state, body="x"))
    classifier = FakeClassifier()

    first = triage_reports(classifier)
    second = triage_reports(classifier)

    assert sorted(o.fingerprint for o in first) == ["et-a", "et-b", "et-c"]
    assert second == []  # already carries a verdict; --retriage replaces it
    assert load_report(store / "et-a.md").triage == _verdict()
    assert load_report(store / "et-d.md").triage is None


def test_backfill_records_nothing_when_triage_fails(store):
    write_report(Report.from_finding(_finding("et-a"), state="promoted", body="x"))

    (outcome,) = triage_reports(FakeClassifier(raises=TriageError("down")))

    assert outcome.triage is None and outcome.warning == "down"
    assert load_report(store / "et-a.md").triage is None


# ---------------------------------------------------------------------------
# Metrics and CLI
# ---------------------------------------------------------------------------

def test_metrics_measure_agreement_and_flag_noise_on_promoted():
    def report(state, decision):
        r = Report.from_finding(_finding(), state=state)
        r.triage = _verdict(decision)
        return r

    m = compute([
        report("promoted", INVESTIGATE), report("promoted", LIKELY_NOISE),
        report("discarded", LIKELY_NOISE), report("seeded", LIKELY_NOISE),
    ])

    assert m.triaged == 4
    assert m.triage_usd_total == pytest.approx(4 * _verdict().usd)
    assert m.triage_agreement == {
        (INVESTIGATE, "promoted"): 1, (LIKELY_NOISE, "promoted"): 1,
        (LIKELY_NOISE, "discarded"): 1,
    }
    assert m.noise_on_promoted == 1


def test_triage_commands_refuse_without_a_key(store, capsys):
    assert main(["triage"]) == 1
    assert main(["run", "--triage", "shadow"]) == 1
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err


def test_the_api_key_never_appears_in_a_repr():
    assert "secret-key" not in repr(JevClassifier(api_key="secret-key"))
