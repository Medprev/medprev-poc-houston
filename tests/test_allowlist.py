"""E4 proof: no write-verb tool ever reaches the committed allowlist."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_allowlist import WRITE_VERBS, generate

ALLOWLIST_PATH = ROOT / "houston" / "allowedtools.txt"


def test_no_write_verb_in_committed_allowlist():
    names = ALLOWLIST_PATH.read_text().splitlines()
    offenders = [n for n in names if WRITE_VERBS.search(n)]
    assert not offenders, f"write-verb tool(s) leaked into allowlist: {offenders}"


def test_committed_allowlist_matches_regenerated_output():
    committed = ALLOWLIST_PATH.read_text().splitlines()
    regenerated = generate()
    assert committed == regenerated, (
        "houston/allowedtools.txt is stale — run "
        "`python scripts/generate_allowlist.py` and commit the result"
    )


def test_generator_actually_filters_something():
    # sanity check the regex isn't accidentally inert
    assert WRITE_VERBS.search("create_datadog_monitor")
    assert WRITE_VERBS.search("delete_rum_metric")
    assert WRITE_VERBS.search("mute_datadog_security_findings")
    assert not WRITE_VERBS.search("search_datadog_error_tracking_issues")
    assert not WRITE_VERBS.search("get_datadog_error_tracking_issue")
