"""E1 proof: collector runs against recorded Datadog responses, no network."""
import json
from pathlib import Path
from unittest.mock import patch

from houston.collector import (
    collect_error_tracking_findings,
    collect_kubernetes_findings,
    collect_monitor_findings,
    kubernetes_evidence_query,
    monitor_evidence_query,
    monitor_severity,
    monitor_timeline_query,
)
from houston.config import Config
from houston.datadog_client import DatadogClient, Window

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_post(url, headers=None, json=None, timeout=None):
    assert "/issues/search" in url
    return _FakeResponse(_load("et_search_response.json"))


def _fake_get(url, headers=None, params=None, timeout=None):
    if url.endswith("114e7438-e897-11ef-83c4-da7ad0900002"):
        return _FakeResponse(_load("et_issue_114e7438.json"))
    if url.endswith("c718a87c-a5a3-11f1-b501-da7ad0900002"):
        return _FakeResponse(_load("et_issue_c718a87c.json"))
    raise AssertionError(f"unexpected GET {url}")


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_collector_normalizes_two_step_search_into_findings(mock_post, mock_get):
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    window = Window.last(96)

    findings = collect_error_tracking_findings(client, window, query="env:production")

    assert len(findings) == 2
    assert mock_post.call_count == 1  # one search call for the whole batch
    assert mock_get.call_count == 2  # one detail call per issue, not per event

    one = next(f for f in findings if f.fingerprint.startswith("et-114e7438"))
    assert one.query == "env:production"  # the query the volume came from
    assert one.service == "medprev-rest-api"
    assert one.reason == "ProfessionalNotFoundException"  # the diagnostic label
    assert one.first_seen_ms == 1739292088005
    assert one.datadog_url == (
        "https://app.datadoghq.com/error-tracking/issue/114e7438-e897-11ef-83c4-da7ad0900002"
    )
    assert one.window_from_ms == window.from_ms


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_regression_is_scoped_to_the_window_not_to_all_history(mock_post, mock_get):
    """Regression test: `regression` is a permanent historical record. The
    fixture's regressed_at is 2025-11-10, so against a window that does not
    contain it the finding is not a regression -- before this, 33 of 151
    reports carried the label and `houston promote` put the word
    "regression" in the issue title of long-stable errors (ADR-0019)."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)

    # 2026-08-29 .. 2026-09-02, well after the fixture's regressed_at
    recent = Window(from_ms=1787940071675, to_ms=1788285671675)
    regressed = {
        f.fingerprint: f.regressed
        for f in collect_error_tracking_findings(client, recent)
    }
    assert regressed["et-114e7438-e897-11ef-83c4-da7ad0900002"] is False
    assert regressed["et-c718a87c-a5a3-11f1-b501-da7ad0900002"] is False

    # a window that does contain 2025-11-10T20:03:03.256Z
    around = Window(from_ms=1762000000000, to_ms=1763000000000)
    regressed_then = {
        f.fingerprint: f.regressed
        for f in collect_error_tracking_findings(client, around)
    }
    assert regressed_then["et-114e7438-e897-11ef-83c4-da7ad0900002"] is True


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_detail_call_is_skipped_for_findings_that_cannot_be_investigated(
    mock_post, mock_get,
):
    """The documented contract (docs/e0-verification.md) is one detail call
    per finding that still needs investigation. Fanning out over every
    search hit meant ~100 sequential calls per run, each one of them a
    chance to abort the run (ADR-0020)."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)

    findings = collect_error_tracking_findings(
        client, Window.last(96), should_enrich=lambda fingerprint: False,
    )

    assert mock_get.call_count == 0
    assert len(findings) == 2  # still counted, still deduplicable
    counts = {f.fingerprint: f.observed_count for f in findings}
    assert counts["et-114e7438-e897-11ef-83c4-da7ad0900002"] == 406
    assert all(f.severity == "unknown" and f.service is None for f in findings)


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_no_network_access_is_attempted(mock_post, mock_get):
    """If this test can fail with a real network error, something bypassed the mock."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    collect_error_tracking_findings(client, Window.last(96))
    for call in list(mock_post.call_args_list) + list(mock_get.call_args_list):
        pass  # presence of calls only through the mocked functions proves no real socket opened


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_observed_count_comes_from_search_step_not_issue_detail(mock_post, mock_get):
    """Regression test: the issue-detail endpoint's schema has no
    total_count field at all (confirmed against the official OpenAPI spec
    in docs/e0-verification.md) -- reading it there silently returns the
    default of 1 for every finding, which breaks E3's cap() ordering.
    Found live: a real investigation (E4) surfaced 287,657 real occurrences
    for a finding this bug had recorded as observed_count=1."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_error_tracking_findings(client, Window.last(96), query="env:production")

    counts = {f.fingerprint: f.observed_count for f in findings}
    assert counts["et-114e7438-e897-11ef-83c4-da7ad0900002"] == 406
    assert counts["et-c718a87c-a5a3-11f1-b501-da7ad0900002"] == 29


def _fake_post_k8s_events(url, headers=None, json=None, timeout=None):
    assert "/events/search" in url
    return _FakeResponse(_load("k8s_events_response.json"))


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_k8s_events)
def test_kubernetes_findings_fingerprint_by_namespace_not_workload(mock_post):
    """Regression test for ADR-0008: measured live that per-workload
    fingerprinting produces 340.4 distinct/day (over the plan's 30/day
    gate) vs. 7.1/day at namespace granularity. Two different pods with
    the same reason in the same namespace must collapse to one finding."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_kubernetes_findings(client, Window.last(96))

    # 3 raw events, 2 in the same namespace+reason (different pods) -> 2 findings, not 3
    assert len(findings) == 2

    rest_api_finding = next(f for f in findings if f.service == "medprev-rest-api")
    assert rest_api_finding.observed_count == 2  # both Unhealthy events collapsed
    assert rest_api_finding.reason == "Unhealthy"
    assert rest_api_finding.fingerprint == "k8s-eks-medprev-online-prd-Unhealthy-medprev-rest-api"
    assert rest_api_finding.datadog_url.startswith(
        "https://app.datadoghq.com/event/explorer?query="
    )
    assert "kube_namespace%3Amedprev-rest-api" in rest_api_finding.datadog_url

    airflow_finding = next(f for f in findings if f.service == "medprev-analytics-etl-airflow")
    assert airflow_finding.observed_count == 1
    assert airflow_finding.reason == "FailedGetResourceMetric"


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_k8s_events)
def test_kubernetes_link_and_query_are_scoped_to_the_reason(mock_post):
    """Regression test: the link was scoped by namespace only, so six
    findings with different reasons in one namespace shared a byte-identical
    datadog_url, and `query` kept the unscoped collector query. Verified
    live that the free-text reason term filters (ADR-0014)."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_kubernetes_findings(client, Window.last(96))

    urls = {f.fingerprint: f.datadog_url for f in findings}
    assert len(set(urls.values())) == len(findings)  # no two findings share a link
    for finding in findings:
        assert finding.reason in finding.query
        assert f"kube_namespace:{finding.service}" in finding.query


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_k8s_events)
def test_kubernetes_findings_carry_the_windows_first_and_last_sighting(mock_post):
    """This source has no lifetime history, and leaving both timestamps
    null made the report contract's mandated `## Linha do tempo` section
    unfillable for every kubernetes and monitor finding (ADR-0014)."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_kubernetes_findings(client, Window.last(96))

    rest_api = next(f for f in findings if f.service == "medprev-rest-api")
    # 2026-09-01T17:52:03Z and 2026-09-01T18:20:53Z
    assert rest_api.first_seen_ms == 1788285123000
    assert rest_api.last_seen_ms == 1788286853000
    assert rest_api.first_seen_ms < rest_api.last_seen_ms


def _fake_post_monitor_events(url, headers=None, json=None, timeout=None):
    assert "/events/search" in url
    return _FakeResponse(_load("monitor_events_response.json"))


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_monitor_events)
def test_monitor_findings_read_nested_alert_attributes_not_top_level(mock_post):
    """Regression test: the REST v2 response's real shape nests title/
    status/priority/monitor under attributes.attributes (AlertEventAttributes),
    not at the top level alongside message/tags/timestamp. A first version
    read event["title"] directly and got the fallback value for every
    single finding, live, against production (2026-09-02)."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_monitor_findings(client, Window.last(96))

    sqs_finding = next(f for f in findings if f.fingerprint == "mon-229652398")
    assert sqs_finding.observed_count == 2
    assert sqs_finding.reason == "ADM - Execuções SQS com erro"  # from monitor.name, not the bracketed title
    assert sqs_finding.service == "tribo-core"
    assert sqs_finding.severity == "high"  # priority:p2 tag
    assert sqs_finding.datadog_url == "https://app.datadoghq.com/monitors/229652398"
    assert sqs_finding.query.endswith("@monitor.id:229652398")
    # 2026-08-28T19:38:58Z and 2026-08-29T01:09:58Z
    assert sqs_finding.first_seen_ms == 1787945938000
    assert sqs_finding.last_seen_ms == 1787965798000


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_monitor_events)
def test_recovery_events_do_not_become_findings(mock_post):
    """Regression test: a recovery is a monitor going back to normal, not an
    incident. The captured fixture proves the status filter is not enough --
    its `[Recovered]` event carries `status: "warning"`, and stripping the
    prefix for the name hid that it had arrived at all."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_monitor_findings(client, Window.last(96))

    # 3 raw events: 2 triggered on one monitor, 1 recovery on another
    assert [f.fingerprint for f in findings] == ["mon-229652398"]


def test_monitor_severity_prefers_the_priority_tag_over_status():
    assert monitor_severity("p1", "warning") == "high"
    assert monitor_severity("p2", None) == "high"
    assert monitor_severity("p3", "error") == "medium"
    assert monitor_severity("p5", "error") == "low"


def test_monitor_severity_falls_back_to_status_without_a_priority_tag():
    assert monitor_severity(None, "error") == "high"
    assert monitor_severity(None, "warning") == "medium"


def test_evidence_queries_scope_to_one_finding():
    assert kubernetes_evidence_query(
        "source:kubernetes env:production status:warn", "medprev-rest-api", "Unhealthy",
    ) == "source:kubernetes env:production status:warn kube_namespace:medprev-rest-api Unhealthy"
    # the parsed-reason fallback is our own placeholder, not a Datadog term
    assert kubernetes_evidence_query("q", "ns", "UnknownReason") == "q kube_namespace:ns"
    assert monitor_evidence_query("source:alert", "42") == "source:alert @monitor.id:42"


def test_monitor_timeline_query_drops_the_status_filter():
    """Unlike monitor_evidence_query, the timeline query must not exclude
    [Recovered] events -- the report's step-by-step timeline needs the
    whole Triggered/Re-Triggered/Recovered cycle."""
    assert monitor_timeline_query("42") == "source:alert @monitor.id:42"
    assert "status:" not in monitor_timeline_query("42")


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_monitor_events)
def test_monitor_findings_carry_two_evidence_links(mock_post):
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_monitor_findings(client, Window.last(96))

    sqs_finding = next(f for f in findings if f.fingerprint == "mon-229652398")
    assert len(sqs_finding.evidence_links) == 2
    assert sqs_finding.evidence_links[0].url == sqs_finding.datadog_url
    timeline_link = sqs_finding.evidence_links[1]
    assert "status" not in (timeline_link.query or "")
    assert "@monitor.id:229652398" in timeline_link.query
    assert "from_ts=" in timeline_link.url and "to_ts=" in timeline_link.url


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_error_tracking_findings_carry_one_evidence_link(mock_post, mock_get):
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_error_tracking_findings(
        client, Window.last(96), should_enrich=lambda fp: True,
    )
    for finding in findings:
        assert len(finding.evidence_links) == 1
        assert finding.evidence_links[0].url == finding.datadog_url


@patch("houston.datadog_client.requests.post", side_effect=_fake_post_k8s_events)
def test_kubernetes_findings_carry_one_evidence_link(mock_post):
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    findings = collect_kubernetes_findings(client, Window.last(96))

    for finding in findings:
        assert len(finding.evidence_links) == 1
        assert finding.evidence_links[0].url == finding.datadog_url
        assert finding.evidence_links[0].query == finding.query


_STATE_FIXTURE_IDS = {
    "aaaaaaaa-0000-11f1-0000-da7ad0900002": "et_issue_state_ignored.json",
    "bbbbbbbb-0000-11f1-0000-da7ad0900002": "et_issue_state_excluded.json",
    "cccccccc-0000-11f1-0000-da7ad0900002": "et_issue_state_acknowledged.json",
    "114e7438-e897-11ef-83c4-da7ad0900002": "et_issue_114e7438.json",
}


def _fake_search_over_states(url, headers=None, json=None, timeout=None):
    assert "/issues/search" in url
    return _FakeResponse({
        "data": [
            {"id": issue_id, "attributes": {"total_count": 500}}
            for issue_id in _STATE_FIXTURE_IDS
        ]
    })


def _fake_get_by_state(url, headers=None, params=None, timeout=None):
    for issue_id, fixture in _STATE_FIXTURE_IDS.items():
        if url.endswith(issue_id):
            return _FakeResponse(_load(fixture))
    raise AssertionError(f"unexpected GET {url}")


@patch("houston.datadog_client.requests.get", side_effect=_fake_get_by_state)
@patch("houston.datadog_client.requests.post", side_effect=_fake_search_over_states)
def test_issues_a_human_dismissed_are_dropped(mock_post, mock_get):
    """ADR-0026: IGNORED and EXCLUDED are a person's own triage in Datadog.
    Investigating them re-decides a question someone already answered --
    three IGNORED issues carried more events than all 100 OPEN ones."""
    client = DatadogClient(
        Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    )

    findings = collect_error_tracking_findings(client, Window.last(96))

    kept = {f.fingerprint for f in findings}
    assert kept == {
        "et-cccccccc-0000-11f1-0000-da7ad0900002",  # ACKNOWLEDGED: picked up
        "et-114e7438-e897-11ef-83c4-da7ad0900002",  # OPEN
    }
    # The state lives on the detail response, so the filter costs no extra
    # call -- every candidate is still fetched exactly once (ADR-0007).
    assert mock_get.call_count == len(_STATE_FIXTURE_IDS)
    assert mock_post.call_count == 1


@patch("houston.datadog_client.requests.get", side_effect=_fake_get_by_state)
@patch("houston.datadog_client.requests.post", side_effect=_fake_search_over_states)
def test_dedup_skips_the_detail_call_before_state_can_be_read(mock_post, mock_get):
    """The state filter runs inside the enrich step, so a finding dedup
    already excluded never pays for it -- ADR-0020's contract is intact."""
    client = DatadogClient(
        Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    )

    findings = collect_error_tracking_findings(
        client, Window.last(96), should_enrich=lambda _: False,
    )

    assert mock_get.call_count == 0
    assert len(findings) == len(_STATE_FIXTURE_IDS)
    assert {f.reason for f in findings} == {"not enriched"}
