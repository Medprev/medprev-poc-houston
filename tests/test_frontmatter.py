"""E5 proof: a synthetic report contaminated by each PII class never reaches
reports/ as text — the body lands in reports/.quarantine/ and only a
redacted record stays behind."""
from houston.frontmatter import Cost, Report, read_report, write_report
from houston.models import Finding


def _finding(fp="et-test", regressed=True) -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="ProfessionalNotFoundException",
        first_seen_ms=1700000000000, last_seen_ms=1700000001000,
        observed_count=42, severity="high", regressed=regressed, raw={},
        datadog_url="https://app.datadoghq.com/error-tracking/issue/et-test",
    )


def _use_tmp(tmp_path, monkeypatch):
    import houston.dedup as dedup_mod
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")


def test_datadog_url_is_injected_in_front_matter_and_visibly_in_body(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    report = Report.from_finding(_finding(), body="Causa raiz: timeout.")
    result = write_report(report)

    text = result.path.read_text()
    assert "datadog_url: https://app.datadoghq.com/error-tracking/issue/et-test" in text
    assert "**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-test" in text

    parsed = read_report(result.path)
    assert parsed["datadog_url"] == "https://app.datadoghq.com/error-tracking/issue/et-test"


def test_clean_report_reaches_reports_dir(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    report = Report.from_finding(_finding(), body="Root cause: timeout in axios client.")
    result = write_report(report)

    assert result.written is True
    assert result.path == tmp_path / "et-test.md"
    assert result.path.exists()
    assert not (tmp_path / ".quarantine" / "et-test.md").exists()


def test_reason_is_the_diagnostic_label_and_novelty_is_its_own_field(tmp_path, monkeypatch):
    """Regression test: `reason` used to be overwritten with "new"/
    "regression", so the error type never reached disk and every promoted
    issue was titled by how new the finding was (ADR-0019)."""
    _use_tmp(tmp_path, monkeypatch)

    regressed = Report.from_finding(_finding(), body="x")
    assert regressed.reason == "ProfessionalNotFoundException"
    assert regressed.novelty == "regression"

    fresh = Report.from_finding(_finding(fp="et-fresh", regressed=False), body="x")
    assert fresh.reason == "ProfessionalNotFoundException"
    assert fresh.novelty == "new"

    parsed = read_report(write_report(fresh).path)
    assert parsed["reason"] == "ProfessionalNotFoundException"
    assert parsed["novelty"] == "new"


def test_cache_tokens_are_recorded_in_front_matter(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    report = Report.from_finding(_finding(), body="Root cause: timeout.")
    report.cost = Cost(
        input_tokens=23881, output_tokens=340, duration_s=8.2, usd=0.32,
        cache_read_input_tokens=10596, cache_creation_input_tokens=13285,
    )
    parsed = read_report(write_report(report).path)

    assert parsed["cost"]["input_tokens"] == 23881
    assert parsed["cost"]["cache_read_input_tokens"] == 10596
    assert parsed["cost"]["cache_creation_input_tokens"] == 13285
    assert parsed["cost"]["usd"] == 0.32


def test_contaminated_report_body_never_reaches_reports(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    contaminated_bodies = [
        "Customer document 123.456.789-09 failed lookup.",
        "Partner CNPJ 12.345.678/0001-95 not found.",
        "Contact carla.cury@medprevonline.com for details.",
        "Called back at (11) 98888-7766 with no answer.",
        "Card 4111 1111 1111 1111 declined at checkout.",
    ]
    for i, body in enumerate(contaminated_bodies):
        report = Report.from_finding(_finding(f"et-dirty-{i}"), body=body)
        result = write_report(report)

        assert result.written is False, f"PII leaked through for body: {body!r}"
        assert result.path == tmp_path / ".quarantine" / f"et-dirty-{i}.md"
        assert result.pii_hits
        assert body not in (tmp_path / f"et-dirty-{i}.md").read_text()


def test_pii_hit_leaves_a_redacted_record_so_the_finding_is_not_re_investigated(
    tmp_path, monkeypatch,
):
    """Regression test: writing nothing to reports/ meant dedup never
    learned the finding had been handled, so cap() -- which orders by
    descending volume -- put the same high-volume finding back at the front
    of the queue on the next run, at ~$0.32 a time, invisibly (ADR-0015)."""
    _use_tmp(tmp_path, monkeypatch)
    from houston.dedup import needs_investigation

    report = Report.from_finding(
        _finding("et-dirty"), body="Contact carla.cury@medprevonline.com for details.",
    )
    report.cost = Cost(input_tokens=23881, output_tokens=340, duration_s=8.2, usd=0.32)
    result = write_report(report)

    assert result.written is False
    assert result.record_path == tmp_path / "et-dirty.md"

    recorded = read_report(result.record_path)
    assert recorded["state"] == "quarantined"
    assert recorded["cost"]["usd"] == 0.32  # the spend stays visible to metrics
    assert "carla.cury@medprevonline.com" not in result.record_path.read_text()
    assert needs_investigation("et-dirty") is False


def test_written_report_round_trips_through_read_report(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    report = Report.from_finding(_finding(), body="Root cause: timeout.")
    report.cost = Cost(input_tokens=1200, output_tokens=340, duration_s=8.2, usd=0.011)
    result = write_report(report)

    parsed = read_report(result.path)
    assert parsed["fingerprint"] == "et-test"
    assert parsed["state"] == "new"
    assert parsed["cost"]["input_tokens"] == 1200
    assert parsed["observed"]["count"] == 42
