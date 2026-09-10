"""Service -> repository resolution, shared by `houston/fix_agent.py`
(where the code fix is written) and `houston/agent.py` (which needs the
target repo name in the investigation payload so the issue body can name
it). Split out of fix_agent.py to avoid an agent <-> fix_agent import
cycle.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVICE_REPOS_PATH = ROOT / "houston" / "service_repos.yaml"


def load_service_repos() -> dict:
    return yaml.safe_load(SERVICE_REPOS_PATH.read_text()) or {}


def resolve_repo(service: str | None, report_body: str = "") -> dict | None:
    """Two-phase resolution: front-matter service first, then body scan."""
    mapping = load_service_repos()
    if service and service in mapping and mapping[service] is not None:
        return mapping[service]
    for name, entry in mapping.items():
        if entry is not None and re.search(rf'\b{re.escape(name)}\b', report_body):
            return entry
    return None
