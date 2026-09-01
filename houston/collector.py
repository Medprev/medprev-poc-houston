"""E1 — deterministic collector. Zero LLM, zero disk writes.

Three queries over a fixed window; each source normalizes into a Finding via
a pure fingerprint function (houston.fingerprint). The query that produced
each finding travels with it, so it can be re-run later as evidence.
"""
import re
from collections import Counter

from houston.datadog_client import DatadogClient, Window
from houston.fingerprint import (
    error_tracking_fingerprint,
    k8s_fingerprint,
    monitor_fingerprint,
)
from houston.models import Finding

_REASON_RE = re.compile(r"\*\*(\w+)\*\*")
_MONITOR_ID_RE = re.compile(r"/monitors/(\d+)")
_TITLE_PREFIX_RE = re.compile(r"^(?:\[P\d\]\s*)?\[(Triggered|Recovered|Alert|Warn)\]\s*")


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


def collect_monitor_findings(
    client: DatadogClient,
    window: Window,
    query: str = "source:alert (status:error OR status:warn)",
) -> list[Finding]:
    """Monitor alert events. The REST v2 response's real shape diverges
    from what its own OpenAPI spec's top-level V2EventAttributes schema
    suggests -- `title`, `status`, `priority`, `service`, and a structured
    `monitor: {id, name, ...}` object all live one level deeper, under
    `attributes.attributes` (the category-specific AlertEventAttributes),
    not at the top level alongside `message`/`tags`/`timestamp`. Confirmed
    live (2026-09-02) after a first version read `event["title"]` directly
    and silently got the fallback value for every single finding.

    Two more things found live, not documented anywhere the plan could
    have named them:
    1. The structured `priority` field is useless here -- every real event
       sampled reports `priority: "normal"` regardless of actual urgency.
       The real severity signal is the `priority:pN` *tag* (P1-P5), when
       present; `status` (error|warning) is the fallback.
    2. Unlike Error Tracking and Kubernetes, `env` is NOT a reliable tag
       here: of 56 real triggered (status:error|warn) events in a 96h
       window, only 4 carried an `env` tag at all. Scoping this query by
       `env:production` (as the other two sources do) would silently drop
       52 of 56 real incidents -- so this source is deliberately NOT
       env-scoped.

    `status:ok` events are recoveries (a monitor going back to normal), not
    incidents, and are excluded by the default query -- same operational
    call already made for the #houston Slack channel's own Zabbix routing
    (medprev-product-backlog#5635): recovery notifications are noise, not
    signal, for anything meant to page or investigate."""
    events = client.search_events(query, window, limit=5000)

    counts: Counter[str] = Counter()
    sample_by_fp: dict[str, dict] = {}
    for event in events:
        tags = _parse_tags(event.get("tags", []))
        alert_attrs = event.get("attributes", {})
        monitor = alert_attrs.get("monitor") or {}

        monitor_id = monitor.get("id")
        if monitor_id is None:
            match = _MONITOR_ID_RE.search(event.get("message", ""))
            if not match:
                continue  # no monitor id found anywhere -- can't fingerprint, skip
            monitor_id = match.group(1)
        monitor_id = str(monitor_id)

        name = monitor.get("name") or _TITLE_PREFIX_RE.sub(
            "", alert_attrs.get("title", "")
        ).strip()
        fp = monitor_fingerprint(monitor_id)
        counts[fp] += 1
        sample_by_fp.setdefault(fp, {
            "monitor_id": monitor_id, "name": name,
            "team": tags.get("team"), "priority_tag": tags.get("priority"),
            "status": alert_attrs.get("status"),
            "timestamp": event.get("timestamp"),
        })

    findings = []
    for fp, count in counts.items():
        sample = sample_by_fp[fp]
        priority_tag = sample["priority_tag"]
        if priority_tag in ("p1", "p2"):
            severity = "high"
        elif priority_tag == "p3":
            severity = "medium"
        elif priority_tag in ("p4", "p5"):
            severity = "low"
        else:  # no priority tag on this monitor -- fall back to status
            severity = "high" if sample["status"] == "error" else "medium"
        findings.append(Finding(
            fingerprint=fp,
            source="monitor",
            query=query,
            service=sample["team"],
            reason=sample["name"] or f"monitor {sample['monitor_id']}",
            first_seen_ms=None,
            last_seen_ms=None,
            observed_count=count,
            severity=severity,
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
    """Entry point for `houston run`. All three planned sources are live:
    Error Tracking, Kubernetes (namespace granularity, ADR-0008), and
    Monitor alert events (ADR-0009)."""
    from houston.config import Config

    config = Config.from_env()
    client = DatadogClient(config)
    window = Window.last(window_hours)
    return (
        collect_error_tracking_findings(client, window)
        + collect_kubernetes_findings(client, window)
        + collect_monitor_findings(client, window)
    )
