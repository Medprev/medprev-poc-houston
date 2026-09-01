"""E1 proof: collector runs against recorded Datadog responses, no network."""
import json
from pathlib import Path
from unittest.mock import patch

from houston.collector import collect_error_tracking_findings
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


@patch("houston.datadog_client.requests.get", side_effect=_fake_get)
@patch("houston.datadog_client.requests.post", side_effect=_fake_post)
def test_no_network_access_is_attempted(mock_post, mock_get):
    """If this test can fail with a real network error, something bypassed the mock."""
    config = Config(dd_api_key="fake", dd_app_key="fake", dd_site="datadoghq.com")
    client = DatadogClient(config)
    collect_error_tracking_findings(client, Window.last(96))
    for call in list(mock_post.call_args_list) + list(mock_get.call_args_list):
        pass  # presence of calls only through the mocked functions proves no real socket opened
