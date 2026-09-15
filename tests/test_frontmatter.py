"""E5 proof: a synthetic report contaminated by each PII class never reaches
reports/ as text — the body lands in reports/.quarantine/ and only a
redacted record stays behind."""
import dataclasses

from houston.frontmatter import Cost, Report, load_report, write_report
from houston.models import Finding


def _finding(fp="et-test", regressed=True) -> Finding:
    return Finding(
        fingerprint=fp, source="error_tracking", query="env:production",
        service="medprev-rest-api", reason="ProfessionalNotFoundException",
        first_seen_ms=1700000000000, last_seen_ms=1700000001000,
        observed_count=42, severity="high", regressed=regressed, raw={},
        datadog_url="https://app.datadoghq.com/error-tracking/issue/et-test",
    )


def test_datadog_url_is_injected_in_front_matter_and_visibly_in_body(store):
    report = Report.from_finding(_finding(), body="Causa raiz: timeout.")
    result = write_report(report)

    text = result.path.read_text()
    assert "datadog_url: https://app.datadoghq.com/error-tracking/issue/et-test" in text
    assert "**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-test" in text

    parsed = load_report(result.path)
    assert parsed.datadog_url == "https://app.datadoghq.com/error-tracking/issue/et-test"


def test_clean_report_reaches_reports_dir(store):
    report = Report.from_finding(_finding(), body="Root cause: timeout in axios client.")
    result = write_report(report)

    assert result.written is True
    assert result.path == store / "et-test.md"
    assert result.path.exists()
    assert not (store / ".quarantine" / "et-test.md").exists()


def test_reason_is_the_diagnostic_label_and_novelty_is_its_own_field(store):
    """Regression test: `reason` used to be overwritten with "new"/
    "regression", so the error type never reached disk and every promoted
    issue was titled by how new the finding was (ADR-0019)."""
    regressed = Report.from_finding(_finding(), body="x")
    assert regressed.reason == "ProfessionalNotFoundException"
    assert regressed.novelty == "regression"

    fresh = Report.from_finding(_finding(fp="et-fresh", regressed=False), body="x")
    assert fresh.reason == "ProfessionalNotFoundException"
    assert fresh.novelty == "new"

    parsed = load_report(write_report(fresh).path)
    assert parsed.reason == "ProfessionalNotFoundException"
    assert parsed.novelty == "new"


def test_cache_tokens_are_recorded_in_front_matter(store):
    report = Report.from_finding(_finding(), body="Root cause: timeout.")
    report.cost = Cost(
        input_tokens=23881, output_tokens=340, duration_s=8.2, usd=0.32,
        cache_read_input_tokens=10596, cache_creation_input_tokens=13285,
    )
    parsed = load_report(write_report(report).path)

    assert parsed.cost.input_tokens == 23881
    assert parsed.cost.cache_read_input_tokens == 10596
    assert parsed.cost.cache_creation_input_tokens == 13285
    assert parsed.cost.usd == 0.32


def test_contaminated_report_body_never_reaches_reports(store):
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
        assert result.path == store / ".quarantine" / f"et-dirty-{i}.md"
        assert result.pii_hits
        assert body not in (store / f"et-dirty-{i}.md").read_text()


def test_pii_hit_leaves_a_redacted_record_so_the_finding_is_not_re_investigated(store):
    """Regression test: writing nothing to reports/ meant dedup never
    learned the finding had been handled, so cap() -- which orders by
    descending volume -- put the same high-volume finding back at the front
    of the queue on the next run, at ~$0.32 a time, invisibly (ADR-0015)."""
    from houston.dedup import needs_investigation

    report = Report.from_finding(
        _finding("et-dirty"), body="Contact carla.cury@medprevonline.com for details.",
    )
    report.cost = Cost(input_tokens=23881, output_tokens=340, duration_s=8.2, usd=0.32)
    result = write_report(report)

    assert result.written is False
    assert result.record_path == store / "et-dirty.md"

    recorded = load_report(result.record_path)
    assert recorded.state == "quarantined"
    assert recorded.cost.usd == 0.32  # the spend stays visible to metrics
    assert "carla.cury@medprevonline.com" not in result.record_path.read_text()
    assert needs_investigation("et-dirty") is False


def test_written_report_round_trips_through_load_report(store):
    report = Report.from_finding(_finding(), body="Root cause: timeout.")
    report.cost = Cost(input_tokens=1200, output_tokens=340, duration_s=8.2, usd=0.011)
    result = write_report(report)

    parsed = load_report(result.path)
    assert parsed.fingerprint == "et-test"
    assert parsed.state == "new"
    assert parsed.cost.input_tokens == 1200
    assert parsed.observed_count == 42


def test_from_markdown_recovers_every_field_to_markdown_rendered():
    """The whole point of the read path: no field is lost on the way back.
    Field-by-field equality, not a spot check -- a field added to `Report`
    and rendered but not parsed fails here, which is the drift that made the
    backfill script rebuild a report by hand and drop `fix_pr`/`fix_state`."""
    report = Report.from_finding(_finding(), state="promoted", body="Root cause: timeout.")
    report.cost = Cost(
        input_tokens=1200, output_tokens=340, duration_s=8.2, usd=0.011,
        cache_read_input_tokens=90, cache_creation_input_tokens=7, model="sonnet",
    )
    report.issue = "https://github.com/Medprev/medprev-product-backlog/issues/1"
    report.fix_pr = "https://github.com/Medprev/medprev-web-app/pull/1372"
    report.fix_state = "pr_open"

    # Without this, the test passes vacuously for exactly the drift it exists
    # to catch: a field rendered but not parsed falls to its default on both
    # sides, and dataclass __eq__ returns True.
    for f in dataclasses.fields(report):
        if f.default is not dataclasses.MISSING:
            assert getattr(report, f.name) != f.default, f"{f.name} is not exercised"
    for f in dataclasses.fields(report.cost):
        assert getattr(report.cost, f.name) != f.default, f"cost.{f.name} not exercised"

    assert Report.from_markdown(report.to_markdown()) == report


def test_re_rendering_a_parsed_report_does_not_stack_the_link_line():
    """`to_markdown` injects `**Link do Datadog:**` into the body. Without an
    inverse in the read path, load-then-write duplicated it on every cycle."""
    once = Report.from_finding(_finding(), body="Causa raiz: timeout.").to_markdown()
    twice = Report.from_markdown(once).to_markdown()

    assert twice.count("**Link do Datadog:**") == 1
    assert twice == once


def test_a_report_on_disk_does_not_re_render_byte_identically():
    """Pins the asymmetry the corpus actually has. Measured: **153 of 153**
    committed reports gain keys on a re-render, not just the 16 legacy ones --
    no report carries ADR-0023's `cost.model`, which is enough on its own.
    Patching a report in place therefore has to preserve the document rather
    than re-render it, which is what `update_front_matter` does."""
    legacy = (
        "---\nfingerprint: et-legacy\nsource: error_tracking\nreason: new\n"
        "service: medprev-rest-api\nenvironment: production\n"
        "window:\n  from: 1\n  to: 2\nobserved:\n  count: 12\n"
        "  first_seen: 3\n  last_seen: 4\nseverity: medium\nstate: seeded\n"
        "cost:\n  input_tokens: 0\n  usd: 0.0\nissue: null\n---\n\nSeeded.\n"
    )
    report = Report.from_markdown(legacy)

    assert report.novelty == ""  # absent on disk, not invented
    assert report.cost.model is None
    assert "novelty:" not in legacy
    assert "novelty: ''" in report.to_markdown()
