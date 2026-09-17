"""The state vocabulary, and the two questions the package asks about it.

Before ADR-0035 the vocabulary was four lists in four modules and nothing
validated a state on the way to disk. The tests that matter here are the
ones about a state this package *cannot* read: the answer differs by
question, and one of the two used to be silently wrong.
"""
import pytest

from houston.frontmatter import (
    Cost,
    Report,
    load_report,
    record_fix_attempt,
    write_report,
)
from houston.metrics import can_close_phase
from houston.models import Finding
from houston.report_state import (
    DISPLAY_ORDER,
    FixState,
    ReportState,
    blocks_phase,
    check_fix_state,
    check_state,
    needs_investigation,
    parse,
)


def _finding(fp="et-state") -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="ProfessionalNotFoundException",
        first_seen_ms=1700000000000, last_seen_ms=1700000001000,
        observed_count=42, severity="high", regressed=False, raw={},
        datadog_url="https://app.datadoghq.com/error-tracking/issue/et-state",
        window_from_ms=1700000000000, window_to_ms=1700086400000,
    )


def _report(state, fingerprint="et-state") -> Report:
    return Report.from_finding(_finding(fingerprint), state=state, body="Causa raiz: x.")


# ---------------------------------------------------------------------------
# a state nobody can read: the two questions answer it differently, on purpose
# ---------------------------------------------------------------------------

def test_an_unreadable_state_keeps_the_phase_open():
    """The bug ADR-0033 recorded and left: `"" not in BLOCKING_STATES` was
    False, so a report whose state nobody could read let the phase close
    over it. It now blocks, which is the answer that makes a human look."""
    assert blocks_phase("") is True
    assert blocks_phase("promted") is True  # a typo is not a state
    assert blocks_phase(None) is True
    assert blocks_phase(ReportState.PROMOTED) is False


def test_an_unreadable_state_does_not_buy_a_second_investigation():
    """The other question spends money, so it answers the other way: an
    agent run against a document nobody can vouch for is a real charge."""
    assert needs_investigation("") is False
    assert needs_investigation("promted") is False
    assert needs_investigation(ReportState.SEEDED) is True
    assert needs_investigation(ReportState.INCOMPLETE) is True


def test_an_unreadable_state_blocks_the_phase_end_to_end(store):
    """Through `can_close_phase`, not just the predicate: the report is on
    disk, `houston metrics` reads it, and the phase stays open."""
    path = write_report(_report(ReportState.PROMOTED)).path
    path.write_text(path.read_text().replace("state: promoted", "state: promted"))

    can_close, pending = can_close_phase([load_report(path)])

    assert can_close is False
    assert pending == 1


# ---------------------------------------------------------------------------
# the vocabulary is enforced on the way in
# ---------------------------------------------------------------------------

def test_a_state_outside_the_vocabulary_never_reaches_disk(store):
    """`write_report` used to take any string. A typo reached `reports/`,
    parsed back as itself, and became its own row in the by-state table."""
    with pytest.raises(ValueError, match="unknown report state 'promted'"):
        write_report(_report("promted"))

    assert not (store / "et-state.md").exists()


def test_the_refusal_names_the_states_it_knows(store):
    with pytest.raises(ValueError, match="seeded, new, incomplete"):
        check_state("nonsense")


def test_a_fix_state_outside_the_vocabulary_never_reaches_disk(store):
    path = write_report(_report(ReportState.PROMOTED)).path

    with pytest.raises(ValueError, match="unknown fix state 'opened'"):
        record_fix_attempt(path, pr_url=None, state="opened", cost=Cost(usd=0.1))

    assert load_report(path).fix_cost is None  # nothing was written


def test_every_state_a_writer_produces_is_in_the_vocabulary():
    """The values `pipeline.py` and `fix_agent.py` hand to the writers --
    as members now, which is what this asserts: the enum and the writers
    cannot drift apart silently."""
    for state in (ReportState.SEEDED, ReportState.NEW, ReportState.INCOMPLETE,
                  ReportState.QUARANTINED, ReportState.PROMOTED):
        check_state(state)
    for fix_state in (FixState.PR_OPEN, FixState.INCOMPLETE):
        check_fix_state(fix_state)


def test_a_reviewers_verdict_is_readable_vocabulary_that_code_cannot_write(store):
    """`merged`/`rejected` name what a human means when they edit the file.
    Nothing observes them, so no call site may record one: the `# human-owned`
    comment promised that and only this refusal delivers it."""
    path = write_report(_report(ReportState.PROMOTED)).path

    with pytest.raises(ValueError, match="reviewer's verdict"):
        record_fix_attempt(
            path, pr_url=None, state=FixState.MERGED, cost=Cost(usd=0.1),
        )

    assert load_report(path).fix_state is None


# ---------------------------------------------------------------------------
# the enum is a value, not a shape that breaks the renderer
# ---------------------------------------------------------------------------

def test_a_state_passed_as_an_enum_member_still_renders(store):
    """A `ReportState` satisfies the `str` annotation everywhere, and
    `yaml.safe_dump` raises RepresenterError on one -- at write time, after
    the investigation is paid for. `to_markdown` coerces instead."""
    result = write_report(_report(ReportState.NEW))

    assert result.written
    assert "state: new\n" in result.path.read_text()
    assert load_report(result.path).state == "new"


def test_parse_maps_a_known_state_and_refuses_the_rest():
    assert parse("quarantined") is ReportState.QUARANTINED
    assert parse("") is None
    assert parse(None) is None


def test_the_display_order_covers_every_state():
    """`generate_site` renders by this order and drops what is missing from
    it -- a state added to the enum and forgotten here disappears from the
    page rather than showing up unsorted."""
    assert set(DISPLAY_ORDER) == set(ReportState)


def test_the_fix_vocabulary_says_which_values_have_a_writer():
    """`merged` and `rejected` are the reviewer's verdict and no code writes
    them; `attempted` was listed on the field and existed nowhere else."""
    assert {s.value for s in FixState} == {"pr_open", "incomplete", "merged", "rejected"}


def test_a_fix_state_passed_as_an_enum_member_reaches_disk(store):
    """The symmetric case to the one above it, and the one that was missing:
    `fix_agent` hands `FixState.PR_OPEN` through `pipeline` into
    `record_fix_attempt`, which writes through this module's *other*
    `safe_dump`. Coercing only the fields `to_markdown` renders left that
    path raising RepresenterError -- swallowed by `WRITE_BACK_ERRORS` into a
    warning, so every `houston fix` lost its PR, state, cost and count."""
    path = write_report(_report(ReportState.PROMOTED)).path

    record_fix_attempt(
        path, pr_url="https://github.com/org/repo/pull/7",
        state=FixState.PR_OPEN, cost=Cost(usd=0.9, model="claude-sonnet-5"),
    )

    parsed = load_report(path)
    assert parsed.fix_state == "pr_open"
    assert parsed.fix_pr == "https://github.com/org/repo/pull/7"
    assert parsed.fix_cost.usd == 0.9
    assert "fix_state: pr_open" in path.read_text()  # the value, not a tag
