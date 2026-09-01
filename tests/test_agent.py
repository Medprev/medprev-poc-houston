"""E4 proof: CLAUDECODE stripped for nesting, write tools always denied,
a timeout or failure never fabricates a result — it becomes incomplete."""
import json
import subprocess
from unittest.mock import patch

from houston.agent import investigate
from houston.models import Finding


def _finding() -> Finding:
    return Finding(
        fingerprint="et-test", source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="new", first_seen_ms=1, last_seen_ms=2,
        observed_count=5, severity="medium", regressed=False, raw={},
    )


def _fake_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


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
def test_timeout_produces_incomplete_not_a_fabricated_result(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=5)
    result = investigate(_finding(), timeout_s=5)
    assert result.state == "incomplete"
    assert result.body is None
    assert "timed out" in result.error


@patch("houston.agent.subprocess.run")
def test_nonzero_exit_produces_incomplete(mock_run):
    mock_run.return_value = _fake_completed("", returncode=1)
    mock_run.return_value.stderr = "some CLI error"
    result = investigate(_finding())
    assert result.state == "incomplete"
    assert result.body is None


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
