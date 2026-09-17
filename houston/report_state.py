"""The report's state vocabulary, and the two questions the rest of the
package asks about it.

Before this module the vocabulary was four lists in four modules, none of
them authoritative: `dedup.NEEDS_INVESTIGATION_STATES`,
`metrics.BLOCKING_STATES`, `generate_site._STATE_ORDER`, and a comment on
`Report.state`. The only exhaustive ones were that comment and a set literal
inside a test. Nothing validated a state on the way to disk, so `state:
promted` would have been written, parsed back, and counted as its own state
by `houston metrics`.

Values are kept as plain `str` on `Report`, not as enum members:
`yaml.safe_dump` refuses a `StrEnum` (`RepresenterError`), and the rendered
bytes of 153 committed reports are the product (ADR-0029). The enum is what
code compares and decides with; `to_markdown` coerces with `str()` so
passing a member is safe rather than a crash at write time.
"""
from enum import StrEnum


class ReportState(StrEnum):
    """What a report is waiting on. The first four are written by code, the
    last two by a human -- that decision is the instrument measuring the
    false-positive rate, so it stays a human gesture (ADR-0028)."""

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


# Work the phase still owes, in the order the incident page lists it.
BLOCKING = (ReportState.NEW, ReportState.INCOMPLETE, ReportState.QUARANTINED)
DISPLAY_ORDER = (
    ReportState.NEW,
    ReportState.INCOMPLETE,
    ReportState.QUARANTINED,
    ReportState.PROMOTED,
    ReportState.DISCARDED,
    ReportState.SEEDED,
)
# `seeded` is deliberate pre-existing debt and `incomplete` is a run to redo;
# both are still owed an investigation, and neither blocks the phase for it
# (ADR-0010, ADR-0015).
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


def validated(raw: str) -> str:
    """The state a writer is about to put on disk, or a refusal.

    Fail closed on the way in, not on the way out: nothing validated this
    before, so a typo reached `reports/`, parsed back as itself, and became
    its own row in `houston metrics`'s by-state table."""
    if parse(raw) is None:
        known = ", ".join(s.value for s in ReportState)
        raise ValueError(f"unknown report state {raw!r} -- known states are: {known}")
    return str(raw)


def validated_fix(raw: str) -> str:
    """Same, for the fix lifecycle."""
    try:
        FixState(raw)
    except ValueError:
        known = ", ".join(s.value for s in FixState)
        raise ValueError(
            f"unknown fix state {raw!r} -- known states are: {known}"
        ) from None
    return str(raw)
