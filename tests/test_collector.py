"""E1 proof: collector runs against recorded Datadog responses, no network."""
import json
from pathlib import Path
from unittest.mock import patch

from houston.collector import (
    collect_error_tracking_findings,
    collect_kubernetes_findings,
    collect_monitor_findings,
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
    assert mock_get.call_count == 2  # one detail call per new issue, not per event

    regressed = {f.fingerprint: f.regressed for f in findings}
    assert regressed["et-114e7438-e897-11ef-83c4-da7ad0900002"] is True
    assert regressed["et-c718a87c-a5a3-11f1-b501-da7ad0900002"] is False

    one = next(f for f in findings if f.fingerprint.startswith("et-114e7438"))
    assert one.query == "env:production"  # evidence is reconferible: the query travels with the finding
    assert one.service == "medprev-rest-api"
    assert one.first_seen_ms == 1739292088005
    assert one.datadog_url == (
        "https://app.datadoghq.com/error-tracking/issue/114e7438-e897-11ef-83c4-da7ad0900002"
    )
    assert one.window_from_ms == window.from_ms


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

    # 3 raw events, 2 share monitor id 229652398 -> 2 findings, not 3
    assert len(findings) == 2

    sqs_finding = next(f for f in findings if f.fingerprint == "mon-229652398")
    assert sqs_finding.observed_count == 2
    assert sqs_finding.reason == "ADM - Execuções SQS com erro"  # from monitor.name, not the bracketed title
    assert sqs_finding.service == "tribo-core"
    assert sqs_finding.severity == "high"  # priority:p2 tag
    assert sqs_finding.datadog_url == "https://app.datadoghq.com/monitors/229652398"

    clearsale_finding = next(f for f in findings if f.fingerprint == "mon-311284089")
    assert clearsale_finding.severity == "medium"  # no priority tag -> falls back to status:warning
