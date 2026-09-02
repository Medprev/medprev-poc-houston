"""E4 proof: CLAUDECODE stripped for nesting, write tools always denied,
a timeout or failure never fabricates a result — it becomes incomplete,
and it never reports the cost of a failed run as zero."""
import json
import subprocess
from unittest.mock import patch

from houston.agent import investigate
from houston.models import Finding


def _finding() -> Finding:
    return Finding(
        fingerprint="et-test", source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="ProfessionalNotFoundException",
        first_seen_ms=1739292088005, last_seen_ms=1788285609984,
        observed_count=406, severity="medium", regressed=False,
        raw={"sample_workload": "medprev-rest-api-ag-58b5f96bd5-fwq5t"},
        window_from_ms=1787940071675, window_to_ms=1788285671675,
    )


def _fake_completed(stdout: str, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


@patch("houston.agent.subprocess.run")
def test_claudecode_env_var_is_stripped_to_allow_nesting(mock_run):
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {"input_tokens": 1, "output_tokens": 1},
         "duration_ms": 10, "total_cost_usd": 0.001}
    ))
    with patch.dict("os.environ", {"CLAUDECODE": "1"}):
        investigate(_finding())
    passed_env = mock_run.call_args.kwargs["env"]
    assert "CLAUDECODE" not in passed_env


@patch("houston.agent.subprocess.run")
def test_bash_write_edit_are_always_disallowed(mock_run):
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 10, "total_cost_usd": 0.0}
    ))
    investigate(_finding())
    cmd = mock_run.call_args.args[0]
    idx = cmd.index("--disallowedTools")
    assert cmd[idx + 1] == "Bash,Write,Edit"


@patch("houston.agent.subprocess.run")
def test_payload_carries_the_window_the_count_belongs_to(mock_run):
    """Regression test: the payload sent a window-scoped observed_count next
    to a years-old first_seen_ms and no window at all, so reports narrated
    "2272 ocorrências desde 2025-03-18" -- a sentence mixing two scopes --
    and that number landed in a ready-to-paste GitHub issue (ADR-0014)."""
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0}
    ))
    investigate(_finding())

    payload = json.loads(mock_run.call_args.kwargs["input"])
    assert payload["window_from_ms"] == 1787940071675
    assert payload["window_to_ms"] == 1788285671675
    assert payload["observed_count"] == 406
    # ADR-0008's stated mitigation: the pod identity the fingerprint drops
    # still reaches the agent.
    assert payload["raw"]["sample_workload"].startswith("medprev-rest-api-ag-")


@patch("houston.agent.subprocess.run")
def test_timeout_produces_incomplete_not_a_fabricated_result(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=5)
    result = investigate(_finding(), timeout_s=5)
    assert result.state == "incomplete"
    assert result.body is None
    assert "timed out" in result.error
    assert result.duration_s == 5.0


@patch("houston.agent.subprocess.run")
def test_nonzero_exit_produces_incomplete(mock_run):
    mock_run.return_value = _fake_completed("", returncode=1, stderr="some CLI error")
    result = investigate(_finding())
    assert result.state == "incomplete"
    assert result.body is None
    assert "some CLI error" in result.error


@patch("houston.agent.subprocess.run")
def test_exhausted_budget_records_what_it_actually_spent(mock_run):
    """Verified live (2026-09-02): `claude -p --max-budget-usd` exits 1 with
    an EMPTY stderr and the whole envelope on stdout. Hardcoding usd=0.0 on
    the non-zero-exit path recorded $0.00 for a run that had really spent
    $0.138283, wrote an error message with nothing after the colon, and
    left the finding first in line to be retried (ADR-0013)."""
    mock_run.return_value = _fake_completed(
        json.dumps({
            "is_error": True,
            "subtype": "error_max_budget_usd",
            "errors": ["Reached maximum budget"],
            "duration_ms": 41200,
            "total_cost_usd": 0.138283,
            "usage": {"input_tokens": 0, "output_tokens": 1204,
                      "cache_read_input_tokens": 10596,
                      "cache_creation_input_tokens": 13285},
        }),
        returncode=1,
        stderr="",
    )
    result = investigate(_finding())

    assert result.state == "incomplete"
    assert result.body is None
    assert result.usd == 0.138283
    assert result.duration_s == 41.2
    assert result.input_tokens == 23881
    assert "error_max_budget_usd" in result.error
    assert "Reached maximum budget" in result.error


@patch("houston.agent.subprocess.run")
def test_input_tokens_include_cache_reads_and_cache_writes(mock_run):
    """Verified live: a real run reported usage.input_tokens=0 next to
    cache_read=10596 and cache_creation=13285. Counting only
    usage.input_tokens understated the E6 metric by three orders of
    magnitude -- every report on disk records 2-14 input tokens for a
    ~$0.32 investigation (ADR-0013)."""
    mock_run.return_value = _fake_completed(json.dumps({
        "result": "## Causa raiz\nfoo",
        "usage": {"input_tokens": 0, "output_tokens": 1204,
                  "cache_read_input_tokens": 10596,
                  "cache_creation_input_tokens": 13285},
        "duration_ms": 30100, "total_cost_usd": 0.32,
    }))
    result = investigate(_finding())

    assert result.state == "new"
    assert result.input_tokens == 23881
    assert result.cache_read_input_tokens == 10596
    assert result.cache_creation_input_tokens == 13285


@patch("houston.agent.subprocess.run")
def test_exit_zero_with_is_error_is_still_incomplete(mock_run):
    mock_run.return_value = _fake_completed(json.dumps({
        "is_error": True, "subtype": "error_during_execution", "result": "",
        "usage": {}, "duration_ms": 900, "total_cost_usd": 0.004,
    }))
    result = investigate(_finding())
    assert result.state == "incomplete"
    assert result.usd == 0.004


@patch("houston.agent.subprocess.run")
def test_successful_result_extracts_cost_and_tokens(mock_run):
    mock_run.return_value = _fake_completed(json.dumps({
        "result": "## Root cause\nfoo",
        "usage": {"input_tokens": 1200, "output_tokens": 340},
        "duration_ms": 8200, "total_cost_usd": 0.011,
    }))
    result = investigate(_finding())
    assert result.state == "new"
    assert result.input_tokens == 1200
    assert result.output_tokens == 340
    assert result.duration_s == 8.2
    assert result.usd == 0.011
