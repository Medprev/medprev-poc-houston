"""Pure fingerprint functions — same input, same key. No I/O, no LLM.

Schema (from the plan, E1):
  et-{issue_id}                       Error Tracking issue — Datadog's own stable id
  mon-{monitor_id}[-{group}]          Monitor alert event, group only when present
  k8s-{cluster}-{reason}-{workload}   Kubernetes Warning event, pod/replicaset suffix stripped
"""
import re

_POD_SUFFIX = re.compile(r"-[0-9a-f]{8,10}-[a-z0-9]{5}$|-[0-9]+$")


def error_tracking_fingerprint(issue_id: str) -> str:
    return f"et-{issue_id}"


def monitor_fingerprint(monitor_id: int | str, group: str | None = None) -> str:
    if group:
        return f"mon-{monitor_id}-{group}"
    return f"mon-{monitor_id}"


def k8s_fingerprint(cluster: str, reason: str, workload: str) -> str:
    """`workload` should already be the pod name; the replicaset/pod hash
    suffix is stripped so that a Deployment's rolling pods collapse to one
    fingerprint instead of one per pod."""
    base_workload = _POD_SUFFIX.sub("", workload)
    return f"k8s-{cluster}-{reason}-{base_workload}"
