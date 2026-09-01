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
