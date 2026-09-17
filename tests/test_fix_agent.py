"""E9 proof: fix agent strips CLAUDECODE, allows code tools, blocks Datadog
tools, resolves service to repo via front-matter or body scan, versions
branches on retry, and records cost on both success and failure."""
import json
from pathlib import Path
from unittest.mock import patch

from houston.fix_agent import (
    ALLOWED_TOOLS,
    _branch_name,
    _extract_pr_url,
    fix,
    load_service_repos,
    resolve_repo,
)
from houston.model_runner import ModelOutcome
from tests.fake_runner import FakeRunner
from tests.fake_runner import outcome as _outcome

GOOD_PAYLOAD = json.dumps({
    "result": "Fixed the bug. PR: https://github.com/Medprev/medprev-web-app/pull/42",
    "usage": {"input_tokens": 5000, "output_tokens": 2000,
              "cache_read_input_tokens": 20000,
              "cache_creation_input_tokens": 15000},
    "duration_ms": 45000, "total_cost_usd": 2.15,
})

REPO_INFO = {"repo": "Medprev/medprev-web-app", "path": "/tmp/fake-repo"}


def test_service_repos_yaml_loads():
    mapping = load_service_repos()
    assert "medprev-rest-api" in mapping
    assert mapping["medprev-rest-api"]["repo"] == "Medprev/medprev-rest-api"


def test_resolve_repo_direct_match():
    info = resolve_repo("medprev-rest-api")
    assert info is not None
    assert info["repo"] == "Medprev/medprev-rest-api"


def test_resolve_repo_null_for_infra():
    assert resolve_repo("kube-system") is None
    assert resolve_repo("argocd") is None


def test_resolve_repo_unknown_service_returns_none():
    assert resolve_repo("totally-unknown-service") is None


def test_resolve_repo_body_scan_finds_service():
    body = "O serviço `medprev-rest-api` (equipe tribo-core) apresenta falhas"
    info = resolve_repo("tribo-core", body)
    assert info is not None
    assert info["repo"] == "Medprev/medprev-rest-api"


def test_resolve_repo_body_scan_no_match():
    assert resolve_repo("tribo-core", "no service mentioned here") is None


def test_branch_name_first_attempt():
    assert _branch_name("et-abc123", 1) == "houston/fix/et-abc123"


def test_branch_name_subsequent_attempts():
    assert _branch_name("et-abc123", 2) == "houston/fix/et-abc123-v2"
    assert _branch_name("et-abc123", 3) == "houston/fix/et-abc123-v3"


def test_extract_pr_url():
    text = "I created PR: https://github.com/Medprev/medprev-web-app/pull/42 for the fix."
    assert _extract_pr_url(text) == "https://github.com/Medprev/medprev-web-app/pull/42"


def test_extract_pr_url_none_when_absent():
    assert _extract_pr_url("No PR was created.") is None
    assert _extract_pr_url(None) is None
    assert _extract_pr_url("") is None


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_claudecode_stripped_from_env(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    with patch.dict("os.environ", {"CLAUDECODE": "1"}):
        fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
            runner=runner)
    assert "CLAUDECODE" not in runner.calls[0].env


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_allowed_tools_are_code_tools(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
        runner=runner)
    cmd = runner.calls[0].argv
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == ALLOWED_TOOLS
    assert "Bash" in cmd[idx + 1]
    assert "Write" in cmd[idx + 1]
    assert "Edit" in cmd[idx + 1]


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_cwd_is_worktree(mock_count, mock_prep, mock_clean):
    wt = Path("/tmp/fake-worktree")
    mock_prep.return_value = (wt, "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
        runner=runner)
    assert runner.calls[0].cwd == wt


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_successful_fix_extracts_pr_url(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
                 runner=runner)
    assert result.state == "pr_open"
    assert result.pr_url == "https://github.com/Medprev/medprev-web-app/pull/42"
    assert result.usd == 2.15
    # `usd` without the tier that billed it is uninterpretable (ADR-0023),
    # and the fix agent runs on a different pinned tier than the
    # investigation whose cost sits in the same report.
    assert result.model == "sonnet"


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_no_pr_url_means_incomplete(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    payload = json.dumps({
        "result": "I could not find the code to fix.",
        "usage": {"input_tokens": 3000, "output_tokens": 500},
        "duration_ms": 20000, "total_cost_usd": 1.0,
    })
    runner = FakeRunner(_outcome(payload))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
                 runner=runner)
    assert result.state == "incomplete"
    assert result.pr_url is None
    assert result.usd == 1.0


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_timeout_produces_incomplete(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(ModelOutcome(returncode=None, stdout="", stderr="", timed_out=True))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1",
                 REPO_INFO, timeout_s=600, runner=runner)
    assert result.state == "incomplete"
    assert "timed out" in result.error
    assert result.duration_s == 600.0


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_nonzero_exit_without_pr_produces_incomplete(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome("", returncode=1, stderr="CLI error"))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
                 runner=runner)
    assert result.state == "incomplete"
    assert result.pr_url is None


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_nonzero_exit_with_pr_url_is_pr_open(mock_count, mock_prep, mock_clean):
    """The agent may create the PR then hit the budget limit — exit 1 but
    a real PR exists. The PR URL is the strongest signal."""
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(
        json.dumps({
            "is_error": True,
            "subtype": "error_max_budget_usd",
            "result": "Created PR https://github.com/Medprev/medprev-web-app/pull/99 but ran out of budget.",
            "usage": {"input_tokens": 50000, "output_tokens": 5000},
            "duration_ms": 300000, "total_cost_usd": 3.0,
        }),
        returncode=1, stderr="",
    ))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
                 runner=runner)
    assert result.state == "pr_open"
    assert result.pr_url == "https://github.com/Medprev/medprev-web-app/pull/99"
    assert result.usd == 3.0


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=2)
def test_retry_increments_branch_version(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test-v3")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    result = fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
                 runner=runner)
    mock_prep.assert_called_once_with(Path("/tmp/fake-repo"), "et-test", 3)
    assert result.branch == "houston/fix/et-test-v3"


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_cleanup_runs_even_on_timeout(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(ModelOutcome(returncode=None, stdout="", stderr="", timed_out=True))
    fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
        runner=runner)
    mock_clean.assert_called_once()


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_report_markdown_passed_as_prompt_context(mock_count, mock_prep, mock_clean):
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    report_text = "---\nfingerprint: et-test\n---\n## Causa raiz\nBug in city.api.mjs"
    fix("et-test", report_text, "https://github.com/org/repo/issues/1", REPO_INFO,
        runner=runner)
    prompt = runner.calls[0].argv[-1]
    assert "Bug in city.api.mjs" in prompt


@patch("houston.fix_agent._cleanup_worktree")
@patch("houston.fix_agent._prepare_worktree")
@patch("houston.fix_agent._count_existing_attempts", return_value=0)
def test_model_and_effort_are_pinned_not_inherited(mock_count, mock_prep, mock_clean):
    """Same failure mode as the investigation agent (ADR-0023): without
    `--model`, this run's $3.00 cap is priced against whatever model the
    operator last selected in their own Claude Code session."""
    mock_prep.return_value = (Path("/tmp/wt"), "houston/fix/et-test")
    runner = FakeRunner(_outcome(GOOD_PAYLOAD))
    fix("et-test", "report text", "https://github.com/org/repo/issues/1", REPO_INFO,
        runner=runner)
    cmd = runner.calls[0].argv

    assert cmd[cmd.index("--model") + 1] == "sonnet"
    # Writing a fix earns more effort than describing one, but it is still
    # a value this repo chooses, not one it inherits.
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "CLAUDE_EFFORT" not in runner.calls[0].env
