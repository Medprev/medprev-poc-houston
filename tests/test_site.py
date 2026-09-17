"""ADR-0005: the incident summary page shows only structured front-matter
fields, never a report's body -- the body is the free-text surface the PII
gate's documented proper-name gap applies to, and the page is meant to be
publishable.

That used to be guaranteed by shape: `load_all_reports` returned front-matter
dicts, and a body was not in the generator's process at all. ADR-0033 made it
return `Report`, so `r.body` is now one attribute away and the guarantee is a
rule instead of an impossibility. This test is the rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_site import render

from houston.frontmatter import Report


def _report(fingerprint: str, body: str) -> Report:
    return Report(
        fingerprint=fingerprint, source="error_tracking", reason="SomeError",
        novelty="new", service="medprev-rest-api", environment="production",
        window_from_ms=1, window_to_ms=2, observed_count=7,
        first_seen_ms=1700000000000, last_seen_ms=1700000001000,
        severity="medium", state="promoted", body=body,
    )


def test_no_report_body_reaches_the_rendered_page():
    secret = "Atendimento de Maria Aparecida da Silva no dia 12"
    page = render([_report("et-body", f"## Causa raiz\n{secret}\n")])

    assert secret not in page
    assert "Causa raiz" not in page
    assert "et-body" in page  # the structured fields are what the page is for


def test_the_page_renders_the_structured_fields_it_is_meant_to_show():
    page = render([_report("et-shown", "irrelevant body")])

    assert "medprev-rest-api" in page
    assert "SomeError" in page
    assert "promoted" in page
