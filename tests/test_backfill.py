"""The backfill migration rewrites every report in `reports/` in one pass, so
what it preserves is not a detail. Before ADR-0033 it rebuilt a `Report` by
hand from 17 of its 19 fields, and `fix_pr`/`fix_state` were erased on every
run (#35) -- against the three reports in the corpus that carry a real PR URL.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest
from backfill_datadog_url import refreshed

from houston.frontmatter import Cost, Report
from houston.models import Finding

SITE = "datadoghq.com"


def _finding(**overrides) -> Finding:
    defaults = {
        "fingerprint": "et-backfill", "source": "error_tracking",
        "query": "env:production", "service": "medprev-rest-api",
        "reason": "ProfessionalNotFoundException", "first_seen_ms": 1, "last_seen_ms": 2,
        "observed_count": 9, "severity": "high", "regressed": False, "raw": {},
        "datadog_url": "https://app.datadoghq.com/error-tracking/issue/backfill",
    }
    return Finding(**{**defaults, **overrides})


def _report(**overrides) -> Report:
    defaults = {
        "fingerprint": "et-backfill", "source": "error_tracking",
        "reason": "ProfessionalNotFoundException", "novelty": "new",
        "service": "medprev-rest-api", "environment": "production",
        "window_from_ms": 1787947458029, "window_to_ms": 1788293058029,
        "observed_count": 26050, "first_seen_ms": 1781785616437,
        "last_seen_ms": 1788292942762, "severity": "medium", "state": "promoted",
        "body": "Causa raiz: timeout.",
    }
    return Report(**{**defaults, **overrides})


def test_a_recorded_fix_pr_survives_the_migration():
    """#35, measured rather than reasoned: the field list used to live in two
    places and only one was authoritative."""
    existing = _report(
        fix_pr="https://github.com/Medprev/medprev-web-app/pull/1372",
        fix_state="pr_open",
        issue="https://github.com/Medprev/medprev-product-backlog/issues/6377",
        cost=Cost(input_tokens=12, output_tokens=7070, duration_s=87.042, usd=0.349),
    )

    result = refreshed(existing, _finding(), SITE)

    assert result.fix_pr == "https://github.com/Medprev/medprev-web-app/pull/1372"
    assert result.fix_state == "pr_open"
    assert result.issue == "https://github.com/Medprev/medprev-product-backlog/issues/6377"
    assert result.cost.usd == 0.349


def test_every_measured_field_is_carried_unchanged():
    """The three derived fields are the only ones allowed to move. Compares
    field by field so a field added to `Report` later is covered without
    anyone remembering to list it here."""
    existing = _report(
        fix_pr="https://github.com/Medprev/medprev-web-app/pull/1",
        fix_state="pr_open", issue="https://example.invalid/1",
        cost=Cost(input_tokens=5, usd=0.2, model="sonnet"),
    )
    derived = {"reason", "novelty", "datadog_url"}

    result = refreshed(existing, _finding(), SITE)

    for name in vars(existing):
        if name not in derived:
            assert getattr(result, name) == getattr(existing, name), name


def test_a_legacy_reason_holding_the_novelty_is_repaired():
    """Pre-ADR-0019 reports stored "new"/"regression" in `reason`. The
    collector's real label is restored and the novelty moves to its own
    field."""
    legacy = _report(reason="new", novelty="", state="seeded")

    result = refreshed(legacy, _finding(reason="EmailCodeInvalidException"), SITE)

    assert result.reason == "EmailCodeInvalidException"
    assert result.novelty == "new"


def test_the_migration_refuses_a_report_it_could_not_parse():
    """`from_markdown` is tolerant, so a malformed document arrives here as
    empty strings rather than as an exception. The old code raised KeyError
    and stopped; this rewrites 153 files in one pass, so it has to refuse
    rather than write the emptiness back."""
    with pytest.raises(ValueError, match="no state/fingerprint"):
        refreshed(_report(state=""), _finding(), SITE)
