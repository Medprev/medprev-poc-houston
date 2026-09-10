"""E1 — deterministic collector. Zero LLM, zero disk writes.

Three queries over a fixed window; each source normalizes into a Finding via
a pure fingerprint function (houston.fingerprint). Each finding carries the
narrowest query that reproduces it, so the evidence can be re-run later.
"""
import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime

from houston.datadog_client import (
    DatadogClient,
    Window,
    error_tracking_issue_url,
    event_explorer_url,
    monitor_url,
)
from houston.fingerprint import (
    error_tracking_fingerprint,
    k8s_fingerprint,
    monitor_fingerprint,
)
from houston.models import EvidenceLink, Finding

_REASON_RE = re.compile(r"\*\*(\w+)\*\*")
_MONITOR_ID_RE = re.compile(r"/monitors/(\d+)")
_TITLE_PREFIX_RE = re.compile(r"^(?:\[P\d\]\s*)?\[(Triggered|Recovered|Alert|Warn)\]\s*")
# A recovery is a monitor going back to normal. They arrive under the
# triggered-status query anyway -- this project's own captured fixture has a
# `[Recovered]` title carrying `status: "warning"` -- so the status filter
# in the query is not enough to keep them out.
_RECOVERY_TITLE_RE = re.compile(r"^(?:\[P\d\]\s*)?\[Recovered\]", re.IGNORECASE)

UNKNOWN_REASON = "UnknownReason"


def _parse_tags(tags: list[str]) -> dict[str, str]:
    parsed = {}
    for tag in tags:
        if ":" in tag:
            key, _, value = tag.partition(":")
            parsed[key] = value
    return parsed


def _timestamp_ms(value: object) -> int | None:
    """Event timestamps come back as ISO-8601 strings on /events/search and
    as epoch milliseconds on Error Tracking; both shapes land here."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


DEFAULT_WINDOW_HOURS = 96


def _regressed_in_window(attrs: dict, window: Window) -> bool:
    """`regression` is a permanent historical record, not a window signal:
    this repo's own fixture carries `regressed_at: 2025-11-10` and was still
    labelled a regression ten months later, which put the word "regression"
    in the title of a GitHub issue for a long-stable error (ADR-0019)."""
    regression = attrs.get("regression") or {}
    regressed_at = _timestamp_ms(regression.get("regressed_at"))
    if regressed_at is None:
        return False
    return window.from_ms <= regressed_at <= window.to_ms


def collect_error_tracking_findings(
    client: DatadogClient,
    window: Window,
    query: str = "env:production",
    track: str = "trace",
    should_enrich: Callable[[str], bool] | None = None,
) -> list[Finding]:
    """Two calls per finding is the documented contract, but only for the
    findings that can still be investigated: `should_enrich` (the dedup
    predicate, in practice) decides which ids earn the second GET. Without
    it every run paid ~100 detail calls to enrich findings it was about to
    discard — see docs/e0-verification.md and ADR-0020.

    A finding that is not enriched carries what the search step returned
    (fingerprint, volume, deep link) and nothing invented for the rest."""
    counts_by_id = client.search_error_tracking_issues(query, window, track=track)
    findings: list[Finding] = []
    for issue_id, total_count in counts_by_id.items():
        fingerprint = error_tracking_fingerprint(issue_id)
        url = error_tracking_issue_url(client.site, issue_id)
        if should_enrich is not None and not should_enrich(fingerprint):
            findings.append(
                Finding(
                    fingerprint=fingerprint,
                    source="error_tracking",
                    query=query,
                    service=None,
                    reason="not enriched",
                    first_seen_ms=None,
                    last_seen_ms=None,
                    observed_count=total_count,
                    severity="unknown",
                    regressed=False,
                    raw={},
                    datadog_url=url,
                    window_from_ms=window.from_ms,
                    window_to_ms=window.to_ms,
                    evidence_links=(
                        EvidenceLink("Issue no Error Tracking", url, query),
                    ),
                )
            )
            continue
        issue = client.get_error_tracking_issue(issue_id)
        attrs = issue["attributes"]
        findings.append(
            Finding(
                fingerprint=fingerprint,
                source="error_tracking",
                # The per-issue locator is datadog_url (the issue page);
                # this is the query whose result the count comes from.
                query=query,
                service=attrs.get("service"),
                reason=attrs.get("error_type", "unknown"),
                first_seen_ms=attrs.get("first_seen"),
                last_seen_ms=attrs.get("last_seen"),
                observed_count=total_count,  # from the search step; the
                # detail step's schema has no total_count field at all
                severity="high" if attrs.get("is_crash") else "medium",
                regressed=_regressed_in_window(attrs, window),
                raw=attrs,
                datadog_url=url,
                window_from_ms=window.from_ms,
                window_to_ms=window.to_ms,
                evidence_links=(
                    EvidenceLink("Issue no Error Tracking", url, query),
                ),
            )
        )
    return findings


def kubernetes_evidence_query(query: str, namespace: str, reason: str) -> str:
    """Scoped to this finding's own namespace *and* reason. The reason has
    no facet on this endpoint (it is parsed out of the message), but the
    free-text term filters: verified live (2026-09-02) on a 96h window,
    `... kube_namespace:medprev-rest-api Unhealthy` returned 192 events
    against 409 for the namespace alone, and every event in the scoped
    result carried `**Unhealthy**`. Without it, six findings with different
    reasons in one namespace all pointed at the same link (ADR-0014)."""
    scoped = f"{query} kube_namespace:{namespace}"
    if reason and reason != UNKNOWN_REASON:
        scoped = f"{scoped} {reason}"
    return scoped


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
    is kept in `raw` and travels to the agent in the investigation payload,
    but does not fragment the fingerprint."""
    events = client.search_events(query, window, limit=20000)

    counts: Counter[str] = Counter()
    sample_by_fp: dict[str, dict] = {}
    seen_ms: dict[str, list[int]] = {}
    for event in events:
        tags = _parse_tags(event.get("tags", []))
        cluster = tags.get("kube_cluster_name", "unknown-cluster")
        namespace = tags.get("kube_namespace", "unknown-namespace")
        workload = tags.get("pod_name") or tags.get("kube_name", "unknown-workload")
        match = _REASON_RE.search(event.get("message", ""))
        reason = match.group(1) if match else UNKNOWN_REASON
        fp = k8s_fingerprint(cluster, reason, namespace)
        counts[fp] += 1
        timestamp_ms = _timestamp_ms(event.get("timestamp"))
        if timestamp_ms is not None:
            seen_ms.setdefault(fp, []).append(timestamp_ms)
        sample_by_fp.setdefault(fp, {
            "cluster": cluster, "namespace": namespace, "reason": reason,
            "sample_workload": workload, "timestamp": event.get("timestamp"),
        })

    findings = []
    for fp, count in counts.items():
        sample = sample_by_fp[fp]
        scoped_query = kubernetes_evidence_query(
            query, sample["namespace"], sample["reason"]
        )
        stamps = seen_ms.get(fp) or []
        k8s_url = event_explorer_url(client.site, scoped_query, window)
        findings.append(Finding(
            fingerprint=fp,
            source="kubernetes",
            query=scoped_query,
            service=sample["namespace"],
            reason=sample["reason"],
            # The window's own first/last sighting: this source has no
            # lifetime history, and leaving these null made the mandated
            # `## Linha do tempo` section unfillable (ADR-0014).
            first_seen_ms=min(stamps) if stamps else None,
            last_seen_ms=max(stamps) if stamps else None,
            observed_count=count,
            severity="medium",
            regressed=False,
            raw=sample,
            datadog_url=k8s_url,
            window_from_ms=window.from_ms,
            window_to_ms=window.to_ms,
            evidence_links=(
                EvidenceLink(
                    "Events Explorer (namespace + Reason, janela fixada)",
                    k8s_url, scoped_query,
                ),
            ),
        ))
    return findings


def monitor_severity(priority_tag: str | None, status: str | None) -> str:
    """The structured `priority` field is useless here -- every real event
    sampled reports `priority: "normal"` regardless of actual urgency. The
    real severity signal is the `priority:pN` tag (P1-P5) when present;
    `status` (error|warning) is the fallback (ADR-0009)."""
    if priority_tag in ("p1", "p2"):
        return "high"
    if priority_tag == "p3":
        return "medium"
    if priority_tag in ("p4", "p5"):
        return "low"
    return "high" if status == "error" else "medium"


def monitor_evidence_query(query: str, monitor_id: str) -> str:
    """Scoped to the one monitor. Verified live (2026-09-02):
    `@monitor.id:229652398` returns that monitor's events only (72 in 30d),
    while the bare tag form `monitor_id:229652398` returns zero — the
    nested attribute path is the one that works."""
    return f"{query} @monitor.id:{monitor_id}"


def monitor_timeline_query(monitor_id: str) -> str:
    """Unlike `monitor_evidence_query`, this one drops the collector's own
    `status:error OR status:warn` filter -- that filter is what makes the
    collector see triggers and miss `[Recovered]` events (status: "ok" or a
    warning-status recovery, see `_RECOVERY_TITLE_RE`), but the report's
    step-by-step timeline needs the full Triggered/Re-Triggered/Recovered
    cycle. Same `@monitor.id:` attribute path verified live for
    `monitor_evidence_query` above (ADR-0014)."""
    return f"source:alert @monitor.id:{monitor_id}"


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
    1. The structured `priority` field is useless here (see
       monitor_severity).
    2. Unlike Error Tracking and Kubernetes, `env` is NOT a reliable tag
       here: of 56 real triggered (status:error|warn) events in a 96h
       window, only 4 carried an `env` tag at all. Scoping this query by
       `env:production` (as the other two sources do) would silently drop
       52 of 56 real incidents -- so this source is deliberately NOT
       env-scoped.

    Recoveries (a monitor going back to normal) are noise, not signal --
    same operational call already made for the #houston Slack channel's own
    Zabbix routing (medprev-product-backlog#5635). `status:ok` is excluded
    by the default query, but that is not sufficient: a `[Recovered]` event
    can arrive carrying `status: "warning"`, so the title is checked too."""
    events = client.search_events(query, window, limit=5000)

    counts: Counter[str] = Counter()
    sample_by_fp: dict[str, dict] = {}
    seen_ms: dict[str, list[int]] = {}
    for event in events:
        tags = _parse_tags(event.get("tags", []))
        alert_attrs = event.get("attributes", {})
        monitor = alert_attrs.get("monitor") or {}

        title = alert_attrs.get("title", "")
        if alert_attrs.get("status") == "ok" or _RECOVERY_TITLE_RE.match(title):
            continue

        monitor_id = monitor.get("id")
        if monitor_id is None:
            match = _MONITOR_ID_RE.search(event.get("message", ""))
            if not match:
                continue  # no monitor id found anywhere -- can't fingerprint, skip
            monitor_id = match.group(1)
        monitor_id = str(monitor_id)

        name = monitor.get("name") or _TITLE_PREFIX_RE.sub("", title).strip()
        fp = monitor_fingerprint(monitor_id)
        counts[fp] += 1
        timestamp_ms = _timestamp_ms(event.get("timestamp"))
        if timestamp_ms is not None:
            seen_ms.setdefault(fp, []).append(timestamp_ms)
        sample_by_fp.setdefault(fp, {
            "monitor_id": monitor_id, "name": name,
            "team": tags.get("team"), "priority_tag": tags.get("priority"),
            "status": alert_attrs.get("status"),
            "timestamp": event.get("timestamp"),
        })

    findings = []
    for fp, count in counts.items():
        sample = sample_by_fp[fp]
        stamps = seen_ms.get(fp) or []
        monitor_id = sample["monitor_id"]
        monitor_status_url = monitor_url(client.site, monitor_id)
        timeline_url = event_explorer_url(
            client.site, monitor_timeline_query(monitor_id), window
        )
        findings.append(Finding(
            fingerprint=fp,
            source="monitor",
            query=monitor_evidence_query(query, monitor_id),
            service=sample["team"],
            reason=sample["name"] or f"monitor {monitor_id}",
            first_seen_ms=min(stamps) if stamps else None,
            last_seen_ms=max(stamps) if stamps else None,
            observed_count=count,
            severity=monitor_severity(sample["priority_tag"], sample["status"]),
            regressed=False,
            raw=sample,
            datadog_url=monitor_status_url,
            window_from_ms=window.from_ms,
            window_to_ms=window.to_ms,
            evidence_links=(
                EvidenceLink("Página do monitor", monitor_status_url),
                EvidenceLink(
                    "Eventos do monitor na janela "
                    "(Triggered/Re-Triggered/Recovered)",
                    timeline_url, monitor_timeline_query(monitor_id),
                ),
            ),
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


def collect(
    window_hours: int = DEFAULT_WINDOW_HOURS,
    should_enrich: Callable[[str], bool] | None = None,
) -> list[Finding]:
    """Entry point for `houston run`. All three planned sources are live:
    Error Tracking, Kubernetes (namespace granularity, ADR-0008), and
    Monitor alert events (ADR-0009).

    `should_enrich` limits the per-finding Error Tracking detail call to the
    fingerprints that can still be investigated. Callers that need every
    field on every finding (the backfill script) leave it None."""
    from houston.config import Config

    config = Config.from_env()
    client = DatadogClient(config)
    window = Window.last(window_hours)
    return (
        collect_error_tracking_findings(client, window, should_enrich=should_enrich)
        + collect_kubernetes_findings(client, window)
        + collect_monitor_findings(client, window)
    )
