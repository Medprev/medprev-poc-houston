"""The one finding shape every source normalizes into."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceLink:
    """A Datadog link (or, when no deterministic link shape exists, the
    exact query) that proves a claim in the investigation. Built by the
    collector, never by the investigating model -- same rule ADR-0011
    already applies to `Finding.datadog_url`."""
    label: str
    url: str
    query: str | None = None


@dataclass(frozen=True)
class Finding:
    fingerprint: str
    source: str  # "error_tracking" | "monitor" | "kubernetes"
    # The narrowest query that reproduces this finding — kubernetes scopes
    # by namespace + reason, monitor by @monitor.id. For error_tracking the
    # per-finding locator is `datadog_url` (the issue page), and this is the
    # window-scoped query the volume came from.
    query: str
    service: str | None
    reason: str  # the diagnostic label: error_type / monitor name / k8s Reason
    first_seen_ms: int | None
    last_seen_ms: int | None
    observed_count: int  # occurrences inside [window_from_ms, window_to_ms], not cumulative
    severity: str
    regressed: bool  # regressed *inside this window*, not at any point in history
    raw: dict[str, Any]
    datadog_url: str | None = None  # deep link to the real evidence -- for log/event validation
    window_from_ms: int = 0
    window_to_ms: int = 0
    evidence_links: tuple[EvidenceLink, ...] = field(default_factory=tuple)
