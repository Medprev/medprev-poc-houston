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
from dataclasses import dataclass
from typing import Any

import requests

from houston.config import Config

_TIMEOUT_S = 30


@dataclass(frozen=True)
class Window:
    from_ms: int
    to_ms: int

    @classmethod
    def last(cls, hours: int) -> "Window":
        to_ms = int(time.time() * 1000)
        from_ms = to_ms - hours * 3600 * 1000
        return cls(from_ms=from_ms, to_ms=to_ms)


class DatadogClient:
    def __init__(self, config: Config):
        self._config = config
        self._headers = {
            "DD-API-KEY": config.dd_api_key,
            "DD-APPLICATION-KEY": config.dd_app_key,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{self._config.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(
            f"{self._config.base_url}{path}",
            headers=self._headers,
            params=params or {},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json()

    def validate(self) -> bool:
        resp = requests.get(
            f"{self._config.base_url}/api/v1/validate",
            headers=self._headers,
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
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
        return {
            item["id"]: item.get("attributes", {}).get("total_count", 1)
            for item in data.get("data", [])
        }

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
