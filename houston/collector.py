"""E1 — deterministic collector. Zero LLM, zero disk writes.

Three queries over a fixed window; each source normalizes into a Finding via
a pure fingerprint function (houston.fingerprint). The query that produced
each finding travels with it, so it can be re-run later as evidence.
"""
import re
from collections import Counter

from houston.datadog_client import DatadogClient, Window
from houston.fingerprint import error_tracking_fingerprint, k8s_fingerprint
from houston.models import Finding

_REASON_RE = re.compile(r"\*\*(\w+)\*\*")


def _parse_tags(tags: list[str]) -> dict[str, str]:
    parsed = {}
    for tag in tags:
        if ":" in tag:
            key, _, value = tag.partition(":")
            parsed[key] = value
    return parsed


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


def collect_kubernetes_findings(
    client: DatadogClient,
    window: Window,
    query: str = "source:kubernetes env:production status:warn",
) -> list[Finding]:
    """`status:warn` is the real severity facet Datadog uses for Kubernetes
    events -- confirmed live (2026-09-02): `alert_type` (the facet other
    Datadog products use) returns no data for this source at all. Each
    Kubernetes Reason (BackOff, Unhealthy, FailedScheduling, ...) is parsed
    from the event message's `**Reason**:` marker -- there is no structured
    reason field on this endpoint, unlike Error Tracking's error_type.

    Fingerprints at NAMESPACE granularity, not per-workload -- ADR-0008.
    Measured live over 7 real days: 340.4 distinct fingerprints/day at
    workload granularity (over the plan's 30/day gate), 7.1/day at
    namespace granularity (passes). The per-workload identity (which pod)
    is kept in `raw` for the agent to read during investigation, but does
    not fragment the fingerprint."""
    events = client.search_events(query, window, limit=20000)

    counts: Counter[str] = Counter()
    sample_by_fp: dict[str, dict] = {}
    for event in events:
        tags = _parse_tags(event.get("tags", []))
        cluster = tags.get("kube_cluster_name", "unknown-cluster")
        namespace = tags.get("kube_namespace", "unknown-namespace")
        workload = tags.get("pod_name") or tags.get("kube_name", "unknown-workload")
        match = _REASON_RE.search(event.get("message", ""))
        reason = match.group(1) if match else "UnknownReason"
        fp = k8s_fingerprint(cluster, reason, namespace)
        counts[fp] += 1
        sample_by_fp.setdefault(fp, {
            "cluster": cluster, "namespace": namespace, "reason": reason,
            "sample_workload": workload, "timestamp": event.get("timestamp"),
        })

    findings = []
    for fp, count in counts.items():
        sample = sample_by_fp[fp]
        findings.append(Finding(
            fingerprint=fp,
            source="kubernetes",
            query=query,
            service=sample["namespace"],
            reason=sample["reason"],
            first_seen_ms=None,
            last_seen_ms=None,
            observed_count=count,
            severity="medium",
            regressed=False,
            raw=sample,
        ))
    return findings


def measure_kubernetes_cardinality(
    client: DatadogClient,
    days: int = 7,
    query: str = "source:kubernetes env:production status:warn",
) -> dict[str, float]:
    """E2's gate: distinct fingerprints per day, over `days` days of history.
    Decision rule fixed before seeing the number (per the plan): above 30
    new k8s fingerprints/day, granularity coarsens to namespace; if still
    over, the source drops from Slice 1."""
    window = Window.last(days * 24)
    findings = collect_kubernetes_findings(client, window, query=query)
    distinct = len(findings)
    return {
        "distinct_fingerprints": distinct,
        "days": days,
        "fingerprints_per_day": distinct / days,
    }


def collect(window_hours: int = DEFAULT_WINDOW_HOURS) -> list[Finding]:
    """Entry point for `houston run`. Error Tracking and Kubernetes (E2's
    gate passed at namespace granularity, ADR-0008) are live. Monitor
    events (`source:alert`) are not implemented yet — see
    medprev-poc-houston#2."""
    from houston.config import Config

    config = Config.from_env()
    client = DatadogClient(config)
    window = Window.last(window_hours)
    return (
        collect_error_tracking_findings(client, window)
        + collect_kubernetes_findings(client, window)
    )
