"""E1 — deterministic collector. Zero LLM, zero disk writes.

Three queries over a fixed window; each source normalizes into a Finding via
a pure fingerprint function (houston.fingerprint). The query that produced
each finding travels with it, so it can be re-run later as evidence.
"""
from houston.datadog_client import DatadogClient, Window
from houston.fingerprint import error_tracking_fingerprint
from houston.models import Finding

DEFAULT_WINDOW_HOURS = 96


def collect_error_tracking_findings(
    client: DatadogClient,
    window: Window,
    query: str = "env:production",
    track: str = "trace",
) -> list[Finding]:
    counts_by_id = client.search_error_tracking_issues(query, window, track=track)
    findings: list[Finding] = []
    for issue_id, total_count in counts_by_id.items():
        issue = client.get_error_tracking_issue(issue_id)
        attrs = issue["attributes"]
        findings.append(
            Finding(
                fingerprint=error_tracking_fingerprint(issue_id),
                source="error_tracking",
                query=query,
                service=attrs.get("service"),
                reason=attrs.get("error_type", "unknown"),
                first_seen_ms=attrs.get("first_seen"),
                last_seen_ms=attrs.get("last_seen"),
                observed_count=total_count,  # from the search step; the
                # detail step's schema has no total_count field at all
                severity="high" if attrs.get("is_crash") else "medium",
                regressed=attrs.get("regression") is not None,
                raw=attrs,
            )
        )
    return findings


def collect(window_hours: int = DEFAULT_WINDOW_HOURS) -> list[Finding]:
    """Entry point for `houston run`. Kubernetes and Monitor sources land in
    a follow-up commit — see medprev-poc-houston#2 (E1) and #3 (E2, the
    cardinality gate that must pass before Kubernetes is in scope)."""
    from houston.config import Config

    config = Config.from_env()
    client = DatadogClient(config)
    window = Window.last(window_hours)
    return collect_error_tracking_findings(client, window)
