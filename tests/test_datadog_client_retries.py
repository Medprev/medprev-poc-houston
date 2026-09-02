"""A run issues around a hundred sequential Datadog calls. Measured live
(2026-09-02): one 503 on a detail GET aborted the whole run with an
unhandled traceback, and the identical call then returned 200 four times in
a row (ADR-0020)."""
from unittest.mock import patch

import pytest
import requests

from houston.config import Config
from houston.datadog_client import DatadogClient


def _client() -> DatadogClient:
    return DatadogClient(Config(dd_api_key="k", dd_app_key="k", dd_site="datadoghq.com"))


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self.headers = {}
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


@patch("houston.datadog_client.time.sleep")
@patch("houston.datadog_client.requests.get")
def test_transient_503_is_retried_and_the_run_survives(mock_get, mock_sleep):
    mock_get.side_effect = [
        _Response(503),
        _Response(200, {"data": {"attributes": {"service": "medprev-rest-api"}}}),
    ]

    issue = _client().get_error_tracking_issue("114e7438")

    assert issue["attributes"]["service"] == "medprev-rest-api"
    assert mock_get.call_count == 2
    assert mock_sleep.called  # backed off instead of hammering


@patch("houston.datadog_client.time.sleep")
@patch("houston.datadog_client.requests.post")
def test_connection_error_is_retried(mock_post, mock_sleep):
    mock_post.side_effect = [
        requests.ConnectionError("connection reset"),
        _Response(200, {"data": []}),
    ]

    assert _client().search_events("q", _window(), limit=1) == []
    assert mock_post.call_count == 2


@patch("houston.datadog_client.time.sleep")
@patch("houston.datadog_client.requests.get")
def test_retries_are_bounded_and_the_error_still_surfaces(mock_get, mock_sleep):
    mock_get.side_effect = [_Response(503), _Response(503), _Response(503)]

    with pytest.raises(requests.HTTPError):
        _client().get_error_tracking_issue("114e7438")

    assert mock_get.call_count == 3


@patch("houston.datadog_client.time.sleep")
@patch("houston.datadog_client.requests.get")
def test_a_client_error_is_not_retried(mock_get, mock_sleep):
    """A revoked key or a malformed query fails the same way three times;
    retrying it only burns wall-clock."""
    mock_get.side_effect = [_Response(403)]

    with pytest.raises(requests.HTTPError):
        _client().get_error_tracking_issue("114e7438")

    assert mock_get.call_count == 1
    assert not mock_sleep.called


def _window():
    from houston.datadog_client import Window
    return Window(from_ms=1, to_ms=2)
