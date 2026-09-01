"""E6 proof: every number comes from front-matter, none typed by hand."""
from houston.metrics import can_close_phase, compute


def _report(state, input_tokens=0, duration_s=0.0, issue=None):
    return {
        "state": state,
        "cost": {"input_tokens": input_tokens, "output_tokens": 0,
                  "duration_s": duration_s, "usd": 0.0},
        "issue": issue,
    }


def test_fp_rate_is_none_when_nothing_decided_yet():
    reports = [_report("seeded"), _report("new")]
    m = compute(reports)
    assert m.false_positive_rate is None


def test_fp_rate_is_discarded_over_promoted_plus_discarded():
    reports = [_report("promoted"), _report("promoted"), _report("discarded")]
    m = compute(reports)
    assert m.false_positive_rate == 1 / 3


def test_phase_cannot_close_while_any_report_is_state_new():
    reports = [_report("promoted"), _report("new")]
    can_close, pending = can_close_phase(reports)
    assert can_close is False
    assert pending == 1


def test_phase_can_close_when_nothing_is_state_new():
    reports = [_report("promoted"), _report("discarded"), _report("seeded")]
    can_close, pending = can_close_phase(reports)
    assert can_close is True
    assert pending == 0


def test_already_had_issue_counts_non_null_issue_field():
    reports = [_report("promoted", issue="Medprev/medprev-product-backlog#123"),
               _report("promoted", issue=None)]
    m = compute(reports)
    assert m.already_had_issue == 1
