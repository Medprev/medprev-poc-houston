"""The one finding shape every source normalizes into."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    fingerprint: str
    source: str  # "error_tracking" | "monitor" | "kubernetes"
    query: str  # the exact query that produced this finding — reconferible evidence
    service: str | None
    reason: str
    first_seen_ms: int | None
    last_seen_ms: int | None
    observed_count: int
    severity: str
    regressed: bool
    raw: dict[str, Any]
