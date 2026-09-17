"""The report's state vocabulary, and the two questions the rest of the
package asks about it.

Before this module the vocabulary was six partial lists, none of them
authoritative: four that ran -- `dedup.NEEDS_INVESTIGATION_STATES`,
`metrics.BLOCKING_STATES`, `generate_site._STATE_ORDER`,
`frontmatter.QUARANTINED_STATE` -- and two written as comments, on
`Report.state` and `Report.fix_state`, which were the only exhaustive ones
along with a set literal inside a test. Nothing validated a state on the way
to disk, so `state: promted` would have been written, parsed back, and
counted as its own state by `houston metrics`.

Values are kept as plain `str` on `Report`, not as enum members:
`yaml.safe_dump` refuses a `StrEnum` (`RepresenterError`), and the rendered
bytes of 153 committed reports are the product (ADR-0029). The enum is what
code compares and decides with; `frontmatter._dump_front_matter` coerces the
whole mapping in the one place both render paths pass through, so passing a
member is safe rather than a crash at write time.
"""
from enum import StrEnum


class ReportState(StrEnum):
    """What a report is waiting on.

    `SEEDED`/`NEW`/`INCOMPLETE`/`QUARANTINED` are written only by code.
    `PROMOTED` has two writers -- a human decides it, but `record_promotion`
    is the one that writes it, right after `houston promote --create` files
    the issue. `DISCARDED` has none: nothing in the package ever writes it,
    on purpose, because the promoted/discarded split is the instrument
    measuring the false-positive rate and stays a human gesture end to end
    (ADR-0028) -- see the ADR's "Bad" section for the cost of that."""

    SEEDED = "seeded"            # pre-existing debt, recorded without investigating (ADR-0010)
    NEW = "new"                  # investigated, waiting on a human decision
    INCOMPLETE = "incomplete"    # the run failed or timed out; cost still recorded (ADR-0013)
    QUARANTINED = "quarantined"  # investigated and paid for, text withheld by the PII gate (ADR-0015)
    PROMOTED = "promoted"        # a human filed it into the backlog
    DISCARDED = "discarded"      # a human judged it noise


class FixState(StrEnum):
    """Where `houston fix` got to on a finding.

    `PR_OPEN` and `INCOMPLETE` are written by `fix_agent.fix`. `MERGED` and
    `REJECTED` are the reviewer's verdict on the PR and **no code writes
    them** -- `docs/pipeline.md` draws them because that is the real
    workflow, not because Houston records it. A fifth value, `attempted`,
    was listed on `Report.fix_state` and appeared nowhere else in the
    package or the corpus; it is gone rather than kept as vocabulary that
    means nothing."""

    PR_OPEN = "pr_open"
    INCOMPLETE = "incomplete"
    MERGED = "merged"      # human-owned, no writer
    REJECTED = "rejected"  # human-owned, no writer


# A tuple, not a set: it renders into an error message, and a frozenset's
# iteration order is not guaranteed across runs.
WRITABLE_FIX_ORDER = ("pr_open", "incomplete")

# The fix states code is allowed to write. `MERGED`/`REJECTED` are the
# reviewer's verdict on the PR: readable vocabulary, so a human who edits the
# file by hand gets a name for what they mean -- and unwritable, so no call
# site can record a verdict nobody gave. The `# human-owned` comment promised
# this; only the frozenset enforces it.
WRITABLE_FIX = frozenset(FixState(v) for v in WRITABLE_FIX_ORDER)

# Work the phase still owes, in the order the incident page lists it.
BLOCKING = (ReportState.NEW, ReportState.INCOMPLETE, ReportState.QUARANTINED)
# One entry per state, in the order the incident page lists it -- checked
# for length as well as membership (tests/test_report_state.py), because a
# duplicate here renders a state's tile twice on the page and a set
# comparison alone would not see it.
DISPLAY_ORDER = (
    ReportState.NEW,
    ReportState.INCOMPLETE,
    ReportState.QUARANTINED,
    ReportState.PROMOTED,
    ReportState.DISCARDED,
    ReportState.SEEDED,
)
# Still owed an investigation. The two sets overlap on purpose: `incomplete`
# is both owed a rerun and a blocker (the run failed and was paid for), while
# `seeded` is deliberate pre-existing debt that blocks nothing (ADR-0010,
# ADR-0015).
NEEDS_INVESTIGATION = frozenset({ReportState.SEEDED, ReportState.INCOMPLETE})


def parse(raw: str | None) -> ReportState | None:
    """The state a document carries, or None when it carries something this
    package has no meaning for -- an empty string from a front-matter with
    no `state` key (ADR-0033 made the parser total), or a typo.

    Returning None rather than raising is what lets the two questions below
    answer it differently: one of them spends money."""
    try:
        return ReportState(raw)
    except ValueError:
        return None


def needs_investigation(raw: str | None) -> bool:
    """Whether the agent should run on this report again. An unreadable
    state answers **no**: re-investigating costs real money against a
    document nobody can vouch for, and `blocks_phase` already makes sure it
    is not silently forgotten."""
    return parse(raw) in NEEDS_INVESTIGATION


def blocks_phase(raw: str | None) -> bool:
    """Whether this report keeps the phase open. An unreadable state answers
    **yes**: before this module it answered no, because `"" not in
    BLOCKING_STATES`, so a report whose state nobody could read left the
    queue permanently and let the phase close over it (ADR-0033 recorded
    this as measured debt)."""
    state = parse(raw)
    return state is None or state in BLOCKING


def check_state(raw: str) -> None:
    """Refuses a state a writer is about to put on disk.

    Fail closed on the way in, not on the way out: nothing validated this
    before, so a typo reached `reports/`, parsed back as itself, and became
    its own row in `houston metrics`'s by-state table."""
    if parse(raw) is None:
        known = ", ".join(s.value for s in ReportState)
        raise ValueError(
            f"unknown report state {str(raw)!r} -- known states are: {known}"
        )


def check_fix_state(raw: str) -> None:
    """Refuses a fix state outside the vocabulary.

    Document-level: `merged`/`rejected` pass, because a human is told to
    record them by hand (`docs/pipeline.md`), and the migration that
    rewrites all 153 reports has to carry what a human wrote."""
    try:
        FixState(raw)
    except ValueError:
        known = ", ".join(s.value for s in FixState)
        raise ValueError(
            f"unknown fix state {str(raw)!r} -- known states are: {known}"
        ) from None


def check_writable_fix_state(raw: str) -> None:
    """Refuses a fix state *code* may not write, the reviewer's verdict
    included. Narrower than `check_fix_state` on purpose: the two questions
    are "is this a fix state at all" (a document, which a human may have
    edited) and "may Houston record this" (a call site)."""
    check_fix_state(raw)
    if FixState(raw) not in WRITABLE_FIX:
        writable = ", ".join(WRITABLE_FIX_ORDER)
        raise ValueError(
            f"fix state {str(raw)!r} is the reviewer's verdict on the PR, not "
            f"something Houston observes -- code may write: {writable}"
        )
