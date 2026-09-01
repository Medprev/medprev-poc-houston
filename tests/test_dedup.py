from houston.dedup import cap, filter_new
from houston.models import Finding


def _finding(fp: str, count: int = 1) -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="new", first_seen_ms=1, last_seen_ms=2,
        observed_count=count, severity="medium", regressed=False, raw={},
    )


def test_filter_new_excludes_findings_with_existing_report(tmp_path, monkeypatch):
    import houston.dedup as dedup_mod
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    (tmp_path / "et-already-seen.md").write_text("---\nstate: new\n---\n")

    findings = [_finding("et-already-seen"), _finding("et-brand-new")]
    result = filter_new(findings)

    assert [f.fingerprint for f in result] == ["et-brand-new"]


def test_second_run_with_no_new_signal_investigates_nothing(tmp_path, monkeypatch):
    import houston.dedup as dedup_mod
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    findings = [_finding("et-a"), _finding("et-b")]

    first_run = filter_new(findings)
    assert len(first_run) == 2
    for f in first_run:
        (tmp_path / f"{f.fingerprint}.md").write_text("---\nstate: new\n---\n")

    second_run = filter_new(findings)
    assert second_run == []


def test_cap_keeps_highest_volume_and_reports_dropped_count():
    findings = [_finding(f"et-{i}", count=i) for i in range(1, 21)]  # 20 findings
    kept, dropped = cap(findings, max_findings=15)

    assert len(kept) == 15
    assert dropped == 5
    assert [f.observed_count for f in kept] == list(range(20, 5, -1))


def test_filter_needing_investigation_targets_seeded_reports(tmp_path, monkeypatch):
    """Regression test for ADR-0010: a seeded report has no real evidence/
    cause/timeline. Before this fix, filter_new excluded anything with a
    report on disk -- including seeded ones -- so a seeded finding could
    never get real investigation through `houston investigate`."""
    import houston.dedup as dedup_mod
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    from houston.dedup import filter_needing_investigation

    seeded = _finding("et-seeded")
    (tmp_path / "et-seeded.md").write_text(
        "---\nstate: seeded\ncost: {input_tokens: 0}\n---\nSeeded, not investigated."
    )
    promoted = _finding("et-promoted")
    (tmp_path / "et-promoted.md").write_text(
        "---\nstate: promoted\ncost: {input_tokens: 0}\n---\nAlready decided."
    )
    brand_new = _finding("et-brand-new")

    result = filter_needing_investigation([seeded, promoted, brand_new])

    fingerprints = {f.fingerprint for f in result}
    assert fingerprints == {"et-seeded", "et-brand-new"}
    assert "et-promoted" not in fingerprints
