"""Pure fingerprint functions — same input, same key. No I/O, no LLM.

Schema (from the plan, E1, as amended by ADR-0008):
  et-{issue_id}                        Error Tracking issue — Datadog's own stable id
  mon-{monitor_id}[-{group}]           Monitor alert event, group only when present
  k8s-{cluster}-{reason}-{namespace}   Kubernetes Warning event, namespace granularity
"""


def error_tracking_fingerprint(issue_id: str) -> str:
    return f"et-{issue_id}"


def monitor_fingerprint(monitor_id: int | str, group: str | None = None) -> str:
    if group:
        return f"mon-{monitor_id}-{group}"
    return f"mon-{monitor_id}"


def k8s_fingerprint(cluster: str, reason: str, namespace: str) -> str:
    """`namespace` is the identity, not the pod: ADR-0008 moved this source
    to namespace granularity, so a Deployment's rolling pods already
    collapse into one fingerprint without any suffix stripping.

    The pod/replicaset-hash strip this function used to apply is gone on
    purpose. Applied to a namespace, its `-[0-9]+$` branch collapsed
    `medprev-web-app-2` onto `medprev-web-app`, and dedup-by-file-existence
    then suppressed the second namespace permanently (ADR-0019)."""
    return f"k8s-{cluster}-{reason}-{namespace}"
