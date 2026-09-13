from houston.dedup import cap, filter_new
from houston.models import Finding


def _finding(fp: str, count: int = 1) -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="new", first_seen_ms=1, last_seen_ms=2,
        observed_count=count, severity="medium", regressed=False, raw={},
    )


def test_filter_new_excludes_findings_with_existing_report(store):
    (store / "et-already-seen.md").write_text("---\nstate: new\n---\n")

    findings = [_finding("et-already-seen"), _finding("et-brand-new")]
    result = filter_new(findings)

    assert [f.fingerprint for f in result] == ["et-brand-new"]


def test_second_run_with_no_new_signal_investigates_nothing(store):
    findings = [_finding("et-a"), _finding("et-b")]

    first_run = filter_new(findings)
    assert len(first_run) == 2
    for f in first_run:
        (store / f"{f.fingerprint}.md").write_text("---\nstate: new\n---\n")

    second_run = filter_new(findings)
    assert second_run == []


def test_cap_keeps_highest_volume_and_reports_dropped_count():
    findings = [_finding(f"et-{i}", count=i) for i in range(1, 21)]  # 20 findings
    kept, dropped = cap(findings, max_findings=15)

    assert len(kept) == 15
    assert dropped == 5
    assert [f.observed_count for f in kept] == list(range(20, 5, -1))


def test_filter_needing_investigation_targets_seeded_reports(store):
    """Regression test for ADR-0010: a seeded report has no real evidence/
    cause/timeline. Before this fix, filter_new excluded anything with a
    report on disk -- including seeded ones -- so a seeded finding could
    never get real investigation through `houston investigate`."""
    from houston.dedup import filter_needing_investigation

    seeded = _finding("et-seeded")
    (store / "et-seeded.md").write_text(
        "---\nstate: seeded\ncost: {input_tokens: 0}\n---\nSeeded, not investigated."
    )
    promoted = _finding("et-promoted")
    (store / "et-promoted.md").write_text(
        "---\nstate: promoted\ncost: {input_tokens: 0}\n---\nAlready decided."
    )
    brand_new = _finding("et-brand-new")

    result = filter_needing_investigation([seeded, promoted, brand_new])

    fingerprints = {f.fingerprint for f in result}
    assert fingerprints == {"et-seeded", "et-brand-new"}
    assert "et-promoted" not in fingerprints


def _sev_finding(fp: str, source: str, severity: str, count: int) -> Finding:
    return Finding(
        fingerprint=fp, source=source, query="q", service="s", reason="r",
        first_seen_ms=1, last_seen_ms=2, observed_count=count,
        severity=severity, regressed=False, raw={},
    )


def test_cap_ranks_severity_above_raw_volume():
    """Regression test: cap() was the pipeline's only prioritization and
    sorted on observed_count alone, so a P1 monitor alert with 45 events
    lost to 401-noise with 13,000 -- and severity, computed at real effort
    by each source, was never read by any decision (ADR-0018)."""
    findings = [
        _sev_finding("et-noise", "error_tracking", "medium", 13643),
        _sev_finding("mon-p1", "monitor", "high", 45),
    ]
    kept, dropped = cap(findings, max_findings=1)

    assert [f.fingerprint for f in kept] == ["mon-p1"]
    assert dropped == 1


def test_cap_reaches_every_source_within_a_severity_tier():
    """observed_count counts three incommensurable things, so the top slots
    went to error_tracking every time: on the real corpus the first
    kubernetes finding ranked 17th and no monitor finding was ever
    investigated."""
    findings = (
        [_sev_finding(f"et-{i}", "error_tracking", "medium", 10000 + i) for i in range(10)]
        + [_sev_finding("k8s-1", "kubernetes", "medium", 1152)]
        + [_sev_finding("mon-1", "monitor", "medium", 45)]
    )
    kept, _ = cap(findings, max_findings=5)

    assert {f.source for f in kept} == {"error_tracking", "kubernetes", "monitor"}


def test_cap_is_deterministic_for_equal_volumes():
    findings = [_sev_finding(f"et-{i}", "error_tracking", "high", 7) for i in range(5)]
    first, _ = cap(findings, max_findings=3)
    second, _ = cap(list(reversed(findings)), max_findings=3)
    assert [f.fingerprint for f in first] == [f.fingerprint for f in second]


def test_findings_of_unknown_severity_rank_last():
    findings = [
        _sev_finding("et-unenriched", "error_tracking", "unknown", 99999),
        _sev_finding("et-low", "error_tracking", "low", 1),
    ]
    kept, _ = cap(findings, max_findings=1)
    assert [f.fingerprint for f in kept] == ["et-low"]
