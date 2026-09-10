"""E4 proof: CLAUDECODE stripped for nesting, write tools always denied,
a timeout or failure never fabricates a result — it becomes incomplete,
and it never reports the cost of a failed run as zero."""
import json
import subprocess
from unittest.mock import patch

from houston.agent import ALLOWLIST_PATH, PROMPT, investigate
from houston.models import EvidenceLink, Finding


def _finding(**overrides) -> Finding:
    defaults = {
        "fingerprint": "et-test", "source": "error_tracking", "query": "env:production",
        "service": "medprev-rest-api", "reason": "ProfessionalNotFoundException",
        "first_seen_ms": 1739292088005, "last_seen_ms": 1788285609984,
        "observed_count": 406, "severity": "medium", "regressed": False,
        "raw": {"sample_workload": "medprev-rest-api-ag-58b5f96bd5-fwq5t"},
        "window_from_ms": 1787940071675, "window_to_ms": 1788285671675,
        "evidence_links": (
            EvidenceLink("Issue no Error Tracking",
                         "https://app.datadoghq.com/error-tracking/issue/et-test",
                         "env:production"),
        ),
    }
    defaults.update(overrides)
    return Finding(**defaults)


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
def test_payload_carries_prerendered_canonical_timestamps(mock_run):
    """The model must never compute a date itself -- code renders every
    finding-owned timestamp and the payload carries the final string."""
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0}
    ))
    investigate(_finding())

    payload = json.loads(mock_run.call_args.kwargs["input"])
    assert payload["window_from"] == (
        "15:01:11 28/08/2026 BRT (epoch 1787940071675 · 2026-08-28T18:01:11.675Z)"
    )
    assert payload["first_seen"] is not None
    assert payload["last_seen"] is not None


@patch("houston.agent.subprocess.run")
def test_payload_timestamps_are_none_safe(mock_run):
    """Kubernetes/monitor findings can have no first/last sighting at all
    (empty event sample) -- the payload must carry null, not raise."""
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0}
    ))
    investigate(_finding(first_seen_ms=None, last_seen_ms=None))

    payload = json.loads(mock_run.call_args.kwargs["input"])
    assert payload["first_seen"] is None
    assert payload["last_seen"] is None


@patch("houston.agent.subprocess.run")
def test_payload_carries_evidence_links_and_target_repo(mock_run):
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0}
    ))
    investigate(_finding(), target_repo="Medprev/medprev-rest-api")

    payload = json.loads(mock_run.call_args.kwargs["input"])
    assert payload["evidence_links"] == [{
        "label": "Issue no Error Tracking",
        "url": "https://app.datadoghq.com/error-tracking/issue/et-test",
        "query": "env:production",
    }]
    assert payload["target_repo"] == "Medprev/medprev-rest-api"


@patch("houston.agent.subprocess.run")
def test_target_repo_defaults_to_none_for_infra_findings(mock_run):
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0}
    ))
    investigate(_finding())

    payload = json.loads(mock_run.call_args.kwargs["input"])
    assert payload["target_repo"] is None


@patch("houston.agent.subprocess.run")
def test_body_timestamp_markers_are_expanded_to_canonical_strings(mock_run):
    mock_run.return_value = _fake_completed(json.dumps({
        "result": "## Causa raiz\nfoo\n\n## Linha do tempo\n"
                   "- {{ts:1781786117679}} — evento X",
        "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0,
    }))
    result = investigate(_finding())

    assert result.state == "new"
    assert "09:35:17 18/06/2026 BRT" in result.body
    assert "{{ts:" not in result.body
    assert result.warnings == []


@patch("houston.agent.subprocess.run")
def test_malformed_timestamp_marker_is_reported_as_a_warning(mock_run):
    mock_run.return_value = _fake_completed(json.dumps({
        "result": "## Causa raiz\nfoo\n\n## Linha do tempo\n- {{ts:not-a-date}}",
        "usage": {}, "duration_ms": 1, "total_cost_usd": 0.0,
    }))
    result = investigate(_finding())

    assert result.state == "new"
    assert "{{ts:not-a-date}}" in result.body
    assert result.warnings == ["{{ts:not-a-date}}"]


def test_prompt_headings_are_in_order_and_issue_body_is_last():
    headings = [
        "## Causa raiz", "## Linha do tempo", "## Evidência",
        "## Ação recomendada", "## Corpo da issue",
    ]
    positions = [PROMPT.index(h) for h in headings]
    assert positions == sorted(positions)
    assert PROMPT.rindex("## Corpo da issue") == positions[-1]


def test_prompt_issue_body_has_the_mandated_subsections():
    issue_body_prompt = PROMPT[PROMPT.index("## Corpo da issue"):]
    for heading in (
        "### Descrição do incidente", "### Causa raiz", "### Linha do tempo",
        "### Evidências", "### Ação recomendada", "### Volume",
        "### Severidade e criticidade",
    ):
        assert heading in issue_body_prompt


def test_prompt_names_the_log_tools_it_requires():
    """ADR-0024: the run that stopped at "causa não determinada" claimed
    application logs were out of scope. The tools were allowlisted the
    whole time, so the prompt has to name them."""
    allowlist = ALLOWLIST_PATH.read_text().splitlines()
    for tool in ("search_datadog_logs", "analyze_datadog_logs"):
        assert any(line.strip().endswith(tool) for line in allowlist)
        assert tool in PROMPT


def test_prompt_separates_querying_logs_from_pasting_their_content():
    """ADR-0024: read as one rule, the paste ban read as a read ban. The
    paste ban itself stays -- the PII gate cannot catch a proper name."""
    assert "CONSULTAR É OBRIGATÓRIO; COLAR É PROIBIDO" in PROMPT
    assert "Nunca cole linha de log" in PROMPT
    # the phrase the bad report used is named only so it can be forbidden
    assert "fora do escopo de leitura seguro" in PROMPT
    assert "NUNCA escreva que uma consulta ficou" in PROMPT


def test_prompt_requires_trace_correlation_and_signal_vs_noise():
    """ADR-0024: the record explaining the error sat in the same trace, and
    the error was 100% `handled` -- noise. Both had to be asked for."""
    assert "trace_id" in PROMPT
    assert "SINAL OU RUÍDO" in PROMPT
    assert "@error.handling" in PROMPT
    assert "handled" in PROMPT

    causa_raiz = PROMPT[PROMPT.index("## Causa raiz"):PROMPT.index("## Linha do tempo")]
    assert "sinal ou ruído" in causa_raiz
    # "não determinada" now has to show the queries behind it
    assert "efetivamente rodadas" in causa_raiz or "efetivamente rodou" in causa_raiz


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


@patch("houston.agent.subprocess.run")
def test_model_and_effort_are_pinned_not_inherited(mock_run):
    """Measured live (2026-09-10, CLI 2.1.267): the same trivial prompt
    through the same subprocess shape cost $0.3915 on the operator's
    inherited default (`claude-opus-5[1m]` @ effort xhigh) and $0.0777 on
    `--model sonnet` @ medium — 5.0x. Without `--model`, `--max-budget-usd
    0.50` is priced against a setting this repo does not control, and three
    real findings died in `error_max_budget_usd` having spent $2.41
    (ADR-0023)."""
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 10, "total_cost_usd": 0.0}
    ))
    investigate(_finding())
    cmd = mock_run.call_args.args[0]

    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--effort") + 1] == "medium"


@patch("houston.agent.subprocess.run")
def test_claude_effort_env_var_cannot_reprice_the_run(mock_run):
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 10, "total_cost_usd": 0.0}
    ))
    with patch.dict("os.environ", {"CLAUDE_EFFORT": "max"}):
        investigate(_finding())
    assert "CLAUDE_EFFORT" not in mock_run.call_args.kwargs["env"]


@patch("houston.agent.subprocess.run")
def test_billed_model_comes_from_the_envelope_not_the_alias(mock_run):
    """`--model sonnet` is an alias; the report has to record what was
    actually billed, because `usd` is uninterpretable without it."""
    mock_run.return_value = _fake_completed(json.dumps(
        {"result": "ok", "usage": {}, "duration_ms": 10, "total_cost_usd": 0.05,
         "modelUsage": {"claude-sonnet-5": {"costUSD": 0.05}}}
    ))
    result = investigate(_finding())
    assert result.model == "claude-sonnet-5"


@patch("houston.agent.subprocess.run")
def test_budget_death_before_any_billed_request_falls_back_to_the_alias(mock_run):
    """One of the three findings in the ADR-0023 run recorded $0.5139 with
    an all-zero usage block and no `modelUsage` — the run died before the
    envelope named a model. Recording nothing there would lose the only
    field that explains the spend."""
    mock_run.return_value = _fake_completed(
        json.dumps({"is_error": True, "subtype": "error_max_budget_usd",
                    "duration_ms": 7523, "total_cost_usd": 0.51388725, "usage": {}}),
        returncode=1, stderr="",
    )
    result = investigate(_finding(), model="opus")
    assert result.state == "incomplete"
    assert result.model == "opus"
