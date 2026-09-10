"""houston investigate: a mocked-agent proof that never fabricates a
result and never spends beyond what it reports."""
import argparse
from unittest.mock import patch

from houston.agent import InvestigationResult
from houston.cli import cmd_investigate
from houston.models import Finding


def _finding(fp="et-cli-test") -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="new", first_seen_ms=1, last_seen_ms=2,
        observed_count=5, severity="medium", regressed=False, raw={},
    )


def _args(**overrides):
    base = {"window_hours": 96, "max_findings": 5, "max_budget_usd": "0.50", "timeout_s": 300,
            "model": "sonnet", "effort": "medium"}
    base.update(overrides)
    return argparse.Namespace(**base)


@patch("houston.cli.write_report")
@patch("houston.cli.agent_investigate")
@patch("houston.cli.cap")
@patch("houston.cli.filter_needing_investigation")
@patch("houston.cli.collect")
def test_successful_investigation_writes_state_new(
    mock_collect, mock_filter_needing_inv, mock_cap, mock_investigate, mock_write, capsys,
):
    finding = _finding()
    mock_collect.return_value = [finding]
    mock_filter_needing_inv.return_value = [finding]
    mock_cap.return_value = ([finding], 0)
    mock_investigate.return_value = InvestigationResult(
        body="## Root cause\nfoo", input_tokens=100, output_tokens=200,
        duration_s=5.0, usd=0.05, state="new", model="claude-sonnet-5",
    )
    mock_write.return_value.written = True
    mock_write.return_value.pii_hits = []

    cmd_investigate(_args())

    written_report = mock_write.call_args.args[0]
    assert written_report.state == "new"
    assert written_report.cost.usd == 0.05
    # `usd` without the model that produced it is what made ADR-0023 a
    # forensic exercise, so the report has to carry both.
    assert written_report.cost.model == "claude-sonnet-5"
    out = capsys.readouterr().out
    assert "total spend this run: $0.05" in out


@patch("houston.cli.write_report")
@patch("houston.cli.agent_investigate")
@patch("houston.cli.cap")
@patch("houston.cli.filter_needing_investigation")
@patch("houston.cli.collect")
def test_timed_out_investigation_writes_incomplete_not_fabricated(
    mock_collect, mock_filter_needing_inv, mock_cap, mock_investigate, mock_write, capsys,
):
    finding = _finding()
    mock_collect.return_value = [finding]
    mock_filter_needing_inv.return_value = [finding]
    mock_cap.return_value = ([finding], 0)
    mock_investigate.return_value = InvestigationResult(
        body=None, input_tokens=0, output_tokens=0, duration_s=300.0,
        usd=0.0, state="incomplete", error="timed out after 300s",
    )
    mock_write.return_value.written = True
    mock_write.return_value.pii_hits = []

    cmd_investigate(_args())

    written_report = mock_write.call_args.args[0]
    assert written_report.state == "incomplete"
    assert "timed out" in written_report.body


@patch("houston.cli.write_report")
@patch("houston.cli.agent_investigate")
@patch("houston.cli.cap")
@patch("houston.cli.filter_needing_investigation")
@patch("houston.cli.collect")
def test_nothing_new_skips_the_agent_entirely(
    mock_collect, mock_filter_needing_inv, mock_cap, mock_investigate, mock_write, capsys,
):
    mock_collect.return_value = []
    mock_filter_needing_inv.return_value = []
    mock_cap.return_value = ([], 0)

    cmd_investigate(_args())

    mock_investigate.assert_not_called()
    assert "nothing needs investigation" in capsys.readouterr().out


@patch("houston.cli.write_report")
@patch("houston.cli.agent_investigate")
@patch("houston.cli.cap")
@patch("houston.cli.filter_needing_investigation")
@patch("houston.cli.collect")
def test_model_and_effort_reach_the_agent(
    mock_collect, mock_filter_needing_inv, mock_cap, mock_investigate, mock_write, capsys,
):
    """The operator's own Claude Code model selection must not be able to
    reprice a run, so the CLI hands the agent an explicit model and effort
    on every call (ADR-0023)."""
    finding = _finding()
    mock_collect.return_value = [finding]
    mock_filter_needing_inv.return_value = [finding]
    mock_cap.return_value = ([finding], 0)
    mock_investigate.return_value = InvestigationResult(
        body="## Root cause\nfoo", input_tokens=1, output_tokens=1,
        duration_s=1.0, usd=0.01, state="new", model="claude-opus-5",
    )
    mock_write.return_value.written = True
    mock_write.return_value.pii_hits = []

    cmd_investigate(_args(model="opus", effort="xhigh"))

    assert mock_investigate.call_args.kwargs["model"] == "opus"
    assert mock_investigate.call_args.kwargs["effort"] == "xhigh"
    # A run priced against a different tier has to say so on stdout, not
    # only after the money is gone.
    assert "opus @ effort xhigh" in capsys.readouterr().out
    assert mock_write.call_args.args[0].cost.model == "claude-opus-5"
