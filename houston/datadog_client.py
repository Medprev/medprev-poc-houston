"""Thin REST v2 client for the three read-only queries the collector needs.

Two schema facts confirmed in E0 (docs/e0-verification.md) that this client
encodes so nothing downstream has to re-learn them:
  - error-tracking search is two calls, not one: `search` returns only
    {id, total_count} per result; the full attributes (first_seen,
    regression, ...) come from a second GET per issue.
  - `from`/`to` are epoch milliseconds, not relative strings like "now-96h"
    (that shorthand only exists on the MCP tool layer, not on raw REST v2).
"""
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

from houston.config import Config

_TIMEOUT_S = 30

# A single `houston run` issues around a hundred sequential calls (one
# search per source plus one detail GET per Error Tracking finding needing
# investigation). Measured live: one 503 on a detail GET aborted the whole
# run with an unhandled traceback, and the identical call then returned 200
# four times in a row — transient upstream noise, not a real failure
# (ADR-0020).
_MAX_ATTEMPTS = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _retry_after_s(resp: object, attempt: int) -> float:
    headers = getattr(resp, "headers", None) or {}
    try:
        return min(float(headers.get("Retry-After", 0)), 30.0) or 0.5 * 2**attempt
    except (TypeError, ValueError):
        return 0.5 * 2**attempt


def _with_retries(call):
    """Retries transient upstream failures; a 4xx that is not 429 raises on
    the first attempt, since retrying a bad request or a revoked key just
    burns wall-clock."""
    for attempt in range(_MAX_ATTEMPTS):
        last_attempt = attempt == _MAX_ATTEMPTS - 1
        try:
            resp = call()
        except (requests.ConnectionError, requests.Timeout):
            if last_attempt:
                raise
            time.sleep(0.5 * 2**attempt)
            continue
        if getattr(resp, "status_code", None) in _RETRY_STATUS and not last_attempt:
            time.sleep(_retry_after_s(resp, attempt))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable: retry loop exhausted without raising")


@dataclass(frozen=True)
class Window:
    from_ms: int
    to_ms: int

    @classmethod
    def last(cls, hours: int) -> "Window":
        to_ms = int(time.time() * 1000)
        from_ms = to_ms - hours * 3600 * 1000
        return cls(from_ms=from_ms, to_ms=to_ms)


def app_url(site: str, path: str) -> str:
    """The Datadog web app always lives at https://app.<site> -- verified
    live against this account's real site (datadoghq.com) for all three
    deep-link shapes this project uses (error-tracking issue, event
    explorer, monitor status), not assumed from docs alone."""
    return f"https://app.{site}{path}"


def error_tracking_issue_url(site: str, issue_id: str) -> str:
    return app_url(site, f"/error-tracking/issue/{issue_id}")


def monitor_url(site: str, monitor_id: str) -> str:
    return app_url(site, f"/monitors/{monitor_id}")


def event_explorer_url(site: str, query: str, window: Window) -> str:
    """Without explicit from_ts/to_ts the Event Explorer defaults to the
    past 15 minutes -- useless for a 96h collection window. live=false
    pins it to the given range instead of following "now"."""
    encoded_query = urllib.parse.quote(query)
    return app_url(
        site,
        f"/event/explorer?query={encoded_query}"
        f"&from_ts={window.from_ms}&to_ts={window.to_ms}&live=false",
    )


class DatadogClient:
    def __init__(self, config: Config):
        self._config = config
        self._headers = {
            "DD-API-KEY": config.dd_api_key,
            "DD-APPLICATION-KEY": config.dd_app_key,
            "Content-Type": "application/json",
        }

    @property
    def site(self) -> str:
        return self._config.dd_site

    def _post(self, path: str, body: dict) -> dict:
        resp = _with_retries(lambda: requests.post(
            f"{self._config.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=_TIMEOUT_S,
        ))
        return resp.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = _with_retries(lambda: requests.get(
            f"{self._config.base_url}{path}",
            headers=self._headers,
            params=params or {},
            timeout=_TIMEOUT_S,
        ))
        return resp.json()

    def validate(self) -> bool:
        resp = _with_retries(lambda: requests.get(
            f"{self._config.base_url}/api/v1/validate",
            headers=self._headers,
            timeout=_TIMEOUT_S,
        ))
        return bool(resp.json().get("valid"))

    def search_error_tracking_issues(
        self, query: str, window: Window, track: str = "trace"
    ) -> dict[str, int]:
        """Step 1 of 2. Returns {issue_id: total_count}. total_count only
        exists on this search-result shape (`error_tracking_search_result`)
        — the issue-detail endpoint's IssueAttributes schema has no such
        field at all, so reading it there silently returns a default (see
        the collector's own regression test for the bug this caused)."""
        body = {
            "data": {
                "type": "search_request",
                "attributes": {
                    "query": query,
                    "track": track,
                    "from": window.from_ms,
                    "to": window.to_ms,
                },
            }
        }
        data = self._post("/api/v2/error-tracking/issues/search", body)
        counts: dict[str, int] = {}
        for item in data.get("data", []):
            # An explicit `"total_count": null` makes .get(..., 1) return
            # None, which then kills cap()'s sort with a TypeError instead
            # of costing one finding its ranking.
            raw_count = (item.get("attributes") or {}).get("total_count")
            counts[item["id"]] = 1 if raw_count is None else int(raw_count)
        return counts

    def get_error_tracking_issue(self, issue_id: str) -> dict[str, Any]:
        """Step 2 of 2. Full attributes, including first_seen and regression."""
        data = self._get(f"/api/v2/error-tracking/issues/{issue_id}")
        return data["data"]

    def search_events(
        self, query: str, window: Window, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """POST /api/v2/events/search — one call per page, cursor-paginated.
        Unlike the Error Tracking search endpoint, `from`/`to` here accept
        relative date-math strings (e.g. "now-96h"), not just epoch ms —
        confirmed against the OpenAPI spec; the two v2 search endpoints are
        not consistent with each other."""
        events: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(events) < limit:
            page: dict[str, Any] = {"limit": min(1000, limit - len(events))}
            if cursor:
                page["cursor"] = cursor
            body = {
                "filter": {
                    "query": query,
                    "from": f"{window.from_ms}",
                    "to": f"{window.to_ms}",
                },
                "page": page,
                "sort": "timestamp",
            }
            data = self._post("/api/v2/events/search", body)
            events.extend(item["attributes"] for item in data.get("data", []))
            cursor = data.get("meta", {}).get("page", {}).get("after")
            if not cursor or not data.get("data"):
                break
        return events
