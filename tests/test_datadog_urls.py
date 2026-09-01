"""Pure URL-builder tests. The exact shapes here were verified live in a
real browser session (2026-09-02) against app.datadoghq.com -- error
tracking issue page, event explorer with a scoped time range, and monitor
status page all confirmed to render the right content, not assumed from
docs alone."""
from houston.datadog_client import (
    Window,
    app_url,
    error_tracking_issue_url,
    event_explorer_url,
    monitor_url,
)


def test_app_url_prefixes_site():
    assert app_url("datadoghq.com", "/foo") == "https://app.datadoghq.com/foo"


def test_error_tracking_issue_url():
    url = error_tracking_issue_url("datadoghq.com", "114e7438-e897-11ef-83c4-da7ad0900002")
    assert url == "https://app.datadoghq.com/error-tracking/issue/114e7438-e897-11ef-83c4-da7ad0900002"


def test_monitor_url():
    assert monitor_url("datadoghq.com", "229652398") == "https://app.datadoghq.com/monitors/229652398"


def test_event_explorer_url_pins_the_window_not_live_now():
    window = Window(from_ms=1787940071675, to_ms=1788285671675)
    url = event_explorer_url("datadoghq.com", "source:kubernetes env:production", window)
    assert url.startswith("https://app.datadoghq.com/event/explorer?query=")
    assert "from_ts=1787940071675" in url
    assert "to_ts=1788285671675" in url
    assert "live=false" in url  # without this, the explorer defaults to "past 15 minutes"


def test_event_explorer_url_encodes_the_query():
    window = Window(from_ms=0, to_ms=1)
    url = event_explorer_url("datadoghq.com", "source:kubernetes env:production", window)
    assert "source%3Akubernetes" in url
    assert " " not in url  # spaces must be percent-encoded, not left raw
