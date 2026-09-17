"""E6 proof: every number comes from front-matter, none typed by hand."""
from houston.frontmatter import Cost, Report
from houston.metrics import can_close_phase, compute


def _report(state, input_tokens=0, duration_s=0.0, issue=None, usd=0.0,
            fix_usd=None) -> Report:
    return Report(
        fingerprint="et-metrics", source="error_tracking", reason="SomeError",
        novelty="new", service="medprev-rest-api", environment="production",
        window_from_ms=0, window_to_ms=0, observed_count=0,
        first_seen_ms=None, last_seen_ms=None, severity="medium",
        state=state, body="",
        cost=Cost(input_tokens=input_tokens, duration_s=duration_s, usd=usd),
        issue=issue,
        fix_cost=Cost(usd=fix_usd, model="claude-sonnet-5") if fix_usd else None,
    )


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


def test_phase_cannot_close_while_an_investigation_is_incomplete():
    """Regression test: counting only state: new let the gate print "phase
    can close" for a run where all five investigations had timed out, which
    contradicted dedup's own NEEDS_INVESTIGATION_STATES (ADR-0015)."""
    reports = [_report("incomplete") for _ in range(5)]
    can_close, pending = can_close_phase(reports)
    assert can_close is False
    assert pending == 5


def test_phase_cannot_close_while_a_report_is_quarantined():
    can_close, pending = can_close_phase([_report("promoted"), _report("quarantined")])
    assert can_close is False
    assert pending == 1


def test_phase_can_close_with_only_decided_and_seeded_reports():
    reports = [_report("promoted"), _report("discarded"), _report("seeded")]
    can_close, pending = can_close_phase(reports)
    assert can_close is True
    assert pending == 0


def test_with_issue_link_counts_non_null_issue_field():
    reports = [_report("promoted", issue="Medprev/medprev-product-backlog#123"),
               _report("promoted", issue=None)]
    m = compute(reports)
    assert m.with_issue_link == 1


def test_spend_is_aggregated_from_front_matter():
    """Regression test: metrics.py had no reference to `usd` at all, so the
    one number this PoC exists to establish -- cost per finding -- had to be
    added up by hand from the report files (ADR-0013)."""
    reports = [
        _report("new", usd=0.30), _report("new", usd=0.40),
        _report("incomplete", usd=0.14), _report("seeded", usd=0.0),
    ]
    m = compute(reports)

    assert round(m.usd_total, 4) == 0.84
    assert round(m.usd_mean, 4) == 0.28  # over the three that actually spent
    assert m.usd_p50 == 0.30
    assert {k: round(v, 4) for k, v in m.usd_by_state.items()} == {
        "new": 0.70, "incomplete": 0.14,
    }


def test_percentiles_tolerate_reports_written_before_a_cost_field_existed():
    """The tolerance is asserted at the real boundary -- a document on disk
    with no `cost:` block at all -- not against a hand-built dict. `Cost`'s
    own defaults are what make it hold, so metrics does not re-implement
    them."""
    legacy = Report.from_markdown("---\nstate: seeded\n---\n\nSeeded.\n")
    m = compute([legacy, _report("new", input_tokens=100, usd=0.1)])

    assert m.total == 2
    assert m.input_tokens_p50 == 100
    assert m.usd_total == 0.1


def test_fix_spend_is_counted_and_kept_apart_from_the_investigation():
    """The dollars `houston fix` bills reached no metric: `FixResult.usd`
    was never written, and `usd_total` reads `cost.usd` -- the
    investigation's price. Measured on the corpus: `et-082448ee...` carries
    `fix_state: pr_open` with `usd: 0.349` -- the investigation's cost, while
    the fix ran against a $3.00 cap. Amounts below are binary-exact so the
    sums can be asserted without rounding."""
    reports = [
        _report("promoted", usd=0.25, fix_usd=1.5),
        _report("promoted", usd=0.5),
    ]

    m = compute(reports)

    assert m.usd_total == 0.75  # investigation only, unchanged meaning
    assert m.fix_usd_total == 1.5
    assert m.with_fix_run == 1
    assert m.usd_grand_total == 2.25


def test_no_fix_run_leaves_the_fix_numbers_at_zero():
    m = compute([_report("promoted", usd=0.25)])

    assert m.fix_usd_total == 0.0
    assert m.with_fix_run == 0
    assert m.usd_grand_total == m.usd_total
