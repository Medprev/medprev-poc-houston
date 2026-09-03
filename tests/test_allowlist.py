"""E4 proof: the committed allowlist holds read-only tools only.

The assertions name real tool names from the snapshot on purpose. Checking
the committed file against the generator's own output, or against the
generator's own verb list, can only ever prove the generator agrees with
itself — that is what let six mutating tools sit in the shipped allowlist
(ADR-0016)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_allowlist import generate, is_read_only

ALLOWLIST_PATH = ROOT / "houston" / "allowedtools.txt"
PREFIX = "mcp__claude_ai_Datadog__"

# Every one of these mutates, spends, or executes, and none of them contains
# a write verb — they were all present in the committed allowlist.
MUTATING = [
    "clean-up-flag",            # deletes a feature flag
    "clone_datadog_form",       # creates a form
    "clone_llmobs_dataset",     # creates a dataset
    "ddsql_run_query",          # arbitrary DDSQL execution
    "run_synthetics_tests",     # triggers billable synthetic runs
    "verify-onboarding-flag",   # mutates onboarding state
    "execute_code",
    "create_datadog_monitor",
    "delete_datadog_dashboard",
    "update_datadog_skill",
    "unpublish_datadog_workflow",
    "unarchive-feature-flag",
    "unblock_datadog_security_aap_denylist",
]

# The investigation cannot do its job without these.
READ_ONLY = [
    "search_datadog_error_tracking_issues",
    "get_datadog_error_tracking_issue",
    "search_datadog_events",
    "search_datadog_logs",
    "search_datadog_spans",
    "get_datadog_trace",
    "get_datadog_metric",
    "describe_datadog_k8s_resource",
    "monitor_groups_search",
    "load_datadog_skill",
]


def _committed() -> set[str]:
    return set(ALLOWLIST_PATH.read_text().split())


def test_no_mutating_tool_is_in_the_committed_allowlist():
    committed = _committed()
    offenders = [n for n in MUTATING if PREFIX + n in committed]
    assert not offenders, f"mutating tool(s) in the allowlist: {offenders}"


def test_read_only_tools_the_investigation_needs_are_in_the_allowlist():
    committed = _committed()
    missing = [n for n in READ_ONLY if PREFIX + n not in committed]
    assert not missing, f"read-only tool(s) missing from the allowlist: {missing}"


def test_committed_allowlist_matches_regenerated_output():
    assert ALLOWLIST_PATH.read_text().splitlines() == generate(), (
        "houston/allowedtools.txt is stale — run "
        "`python scripts/generate_allowlist.py` and commit the result"
    )


def test_filter_fails_closed_on_an_unrecognized_verb():
    # A name that declares nothing read-only is denied even though it
    # carries no write verb -- the failure mode that shipped clean-up-flag.
    assert not is_read_only(PREFIX + "clean-up-flag")
    assert not is_read_only(PREFIX + "frobnicate_datadog_widget")
    assert not is_read_only(PREFIX + "_dd_gff")


def test_verb_matching_is_token_exact_not_substring():
    # "set" inside "dataset" and "run" inside "runtime" are not write verbs.
    assert is_read_only(PREFIX + "get_llmobs_dataset_records")
    assert is_read_only(PREFIX + "get_profiling_runtime_ids")
    assert is_read_only(PREFIX + "get_datadog_test_optimization_settings")
    # ...but as their own token they are.
    assert not is_read_only(PREFIX + "set_datadog_dashboard")
    assert not is_read_only(PREFIX + "run_datadog_query")
