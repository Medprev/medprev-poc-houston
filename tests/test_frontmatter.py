"""E5 proof: a synthetic report contaminated by each PII class never reaches
reports/ — it lands in reports/.quarantine/ instead."""
from houston.frontmatter import Cost, Report, read_report, write_report
from houston.models import Finding


def _finding(fp="et-test") -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="new", first_seen_ms=1700000000000,
        last_seen_ms=1700000001000, observed_count=42, severity="high",
        regressed=True, raw={},
        datadog_url="https://app.datadoghq.com/error-tracking/issue/et-test",
    )


def test_datadog_url_is_injected_in_front_matter_and_visibly_in_body(tmp_path, monkeypatch):
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

    report = Report.from_finding(_finding(), body="Causa raiz: timeout.")
    result = write_report(report)

    text = result.path.read_text()
    assert "datadog_url: https://app.datadoghq.com/error-tracking/issue/et-test" in text
    assert "**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-test" in text

    parsed = read_report(result.path)
    assert parsed["datadog_url"] == "https://app.datadoghq.com/error-tracking/issue/et-test"


def test_clean_report_reaches_reports_dir(tmp_path, monkeypatch):
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

    report = Report.from_finding(_finding(), body="Root cause: timeout in axios client.")
    result = write_report(report)

    assert result.written is True
    assert result.path == tmp_path / "et-test.md"
    assert result.path.exists()
    assert not (tmp_path / ".quarantine" / "et-test.md").exists()


def test_reason_reflects_regression_signal():
    regressed = Report.from_finding(_finding(), body="x")
    assert regressed.reason == "regression"

    fresh = Report.from_finding(
        Finding(fingerprint="et-fresh", source="error_tracking", query="q",
                service="s", reason="new", first_seen_ms=1, last_seen_ms=2,
                observed_count=1, severity="low", regressed=False, raw={}),
        body="x",
    )
    assert fresh.reason == "new"


def test_contaminated_report_goes_to_quarantine_not_reports(tmp_path, monkeypatch):
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

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
        assert not (tmp_path / f"et-dirty-{i}.md").exists()
        assert result.path == tmp_path / ".quarantine" / f"et-dirty-{i}.md"
        assert result.pii_hits


def test_written_report_round_trips_through_read_report(tmp_path, monkeypatch):
    import houston.frontmatter as fm
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")

    report = Report.from_finding(_finding(), body="Root cause: timeout.")
    report.cost = Cost(input_tokens=1200, output_tokens=340, duration_s=8.2, usd=0.011)
    result = write_report(report)

    parsed = read_report(result.path)
    assert parsed["fingerprint"] == "et-test"
    assert parsed["state"] == "new"
    assert parsed["cost"]["input_tokens"] == 1200
    assert parsed["observed"]["count"] == 42
