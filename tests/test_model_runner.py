"""Direct proof of SubprocessRunner's contract (ADR-0031): the only place
`subprocess.run` is called to invoke `claude` in the package. Merge rule
for this PR: it must not reduce the number of assertions made against a
real argv/env/cwd/stdin shape -- test_agent.py and test_fix_agent.py moved
those assertions onto FakeRunner.calls, which proves the port is threaded
correctly, but only this file proves SubprocessRunner itself builds the
real subprocess.run() call the same way agent.py/fix_agent.py used to."""
import subprocess
from pathlib import Path
from unittest.mock import patch

from houston.model_runner import ModelRun, SubprocessRunner


def _fake_completed(stdout: str, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@patch("houston.model_runner.subprocess.run")
def test_argv_is_passed_through_unchanged(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude", "-p", "--model", "sonnet"]))
    assert mock_run.call_args.args[0] == ["claude", "-p", "--model", "sonnet"]


@patch("houston.model_runner.subprocess.run")
def test_stdin_is_passed_as_input(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"], stdin='{"fingerprint": "et-x"}'))
    assert mock_run.call_args.kwargs["input"] == '{"fingerprint": "et-x"}'


@patch("houston.model_runner.subprocess.run")
def test_no_stdin_passes_none_as_input(mock_run):
    """The fix agent's call shape has no stdin -- the prompt is argv[-1]."""
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert mock_run.call_args.kwargs["input"] is None


@patch("houston.model_runner.subprocess.run")
def test_env_is_passed_through(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"], env={"PATH": "/usr/bin"}))
    assert mock_run.call_args.kwargs["env"] == {"PATH": "/usr/bin"}


@patch("houston.model_runner.subprocess.run")
def test_no_env_passes_none_meaning_inherit(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert mock_run.call_args.kwargs["env"] is None


@patch("houston.model_runner.subprocess.run")
def test_cwd_is_passed_as_a_string(mock_run):
    """subprocess.run's cwd historically wants a str, not a Path -- the
    fix agent's original call site did str(worktree_dir)."""
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"], cwd=Path("/tmp/wt")))
    assert mock_run.call_args.kwargs["cwd"] == "/tmp/wt"


@patch("houston.model_runner.subprocess.run")
def test_no_cwd_passes_none_meaning_current_directory(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert mock_run.call_args.kwargs["cwd"] is None


@patch("houston.model_runner.subprocess.run")
def test_timeout_is_passed_through(mock_run):
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"], timeout_s=42))
    assert mock_run.call_args.kwargs["timeout"] == 42


@patch("houston.model_runner.subprocess.run")
def test_check_is_always_false(mock_run):
    """A non-zero exit must reach the caller as data (ModelOutcome), never
    as a raised CalledProcessError -- both agent.py and fix_agent.py decide
    state from the outcome, not from an exception."""
    mock_run.return_value = _fake_completed("ok")
    SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert mock_run.call_args.kwargs["check"] is False


@patch("houston.model_runner.subprocess.run")
def test_successful_run_returns_the_captured_outcome(mock_run):
    mock_run.return_value = _fake_completed("stdout text", returncode=0, stderr="")
    outcome = SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert outcome.returncode == 0
    assert outcome.stdout == "stdout text"
    assert outcome.stderr == ""
    assert outcome.timed_out is False


@patch("houston.model_runner.subprocess.run")
def test_nonzero_exit_is_returned_not_raised(mock_run):
    mock_run.return_value = _fake_completed("", returncode=1, stderr="boom")
    outcome = SubprocessRunner().run(ModelRun(argv=["claude"]))
    assert outcome.returncode == 1
    assert outcome.stderr == "boom"
    assert outcome.timed_out is False


@patch("houston.model_runner.subprocess.run")
def test_timeout_is_reported_as_an_outcome_not_a_raised_exception(mock_run):
    """The CLI prints its JSON envelope on stdout even on a timeout kill
    (ADR-0013) -- exc.stdout carries whatever was captured before the kill,
    and it must survive as ModelOutcome.stdout, not be lost to a raise."""
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["claude"], timeout=5, output='{"partial": true}',
    )
    outcome = SubprocessRunner().run(ModelRun(argv=["claude"], timeout_s=5))
    assert outcome.timed_out is True
    assert outcome.returncode is None
    assert outcome.stdout == '{"partial": true}'


@patch("houston.model_runner.subprocess.run")
def test_timeout_with_no_captured_stdout_returns_empty_string(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=5)
    outcome = SubprocessRunner().run(ModelRun(argv=["claude"], timeout_s=5))
    assert outcome.timed_out is True
    assert outcome.stdout == ""


@patch("houston.model_runner.subprocess.run")
def test_timeout_stdout_captured_as_bytes_is_decoded(mock_run):
    """`text=True` on subprocess.run should make captured output str, but
    a TimeoutExpired raised before the text-mode decode kicks in can still
    carry bytes -- decode defensively rather than let it propagate as a
    TypeError in _payload_or_none downstream."""
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["claude"], timeout=5, output=b'{"partial": true}',
    )
    outcome = SubprocessRunner().run(ModelRun(argv=["claude"], timeout_s=5))
    assert outcome.stdout == '{"partial": true}'
