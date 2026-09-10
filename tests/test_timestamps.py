"""houston/timestamps.py -- the model never converts a date itself; this
module is what guarantees a timestamp shown in a report is exactly right."""
from houston.timestamps import canonicalize, format_ms, parse_timestamp


def test_format_ms_matches_the_owner_specified_shape():
    assert format_ms(1781786117679) == (
        "09:35:17 18/06/2026 BRT (epoch 1781786117679 · 2026-06-18T12:35:17.679Z)"
    )


def test_format_ms_crosses_midnight_between_utc_and_brt():
    """UTC 03:35:12 is 00:35:12 the SAME calendar day in BRT (UTC-3) -- a
    model computing this by hand is exactly the case that produced vague
    dates like "~2026-09-05/06" in real reports."""
    assert format_ms(1788924912000) == (
        "00:35:12 09/09/2026 BRT (epoch 1788924912000 · 2026-09-09T03:35:12.000Z)"
    )


def test_format_ms_none_passes_through():
    assert format_ms(None) is None


def test_format_ms_uses_brst_before_2019_dst_retirement():
    # 2019-02-01T03:00:00Z was still Brazilian summer time (-02:00).
    assert format_ms(1548990000000) == (
        "01:00:00 01/02/2019 BRST (epoch 1548990000000 · 2019-02-01T03:00:00.000Z)"
    )


def test_parse_timestamp_accepts_epoch_ms():
    assert parse_timestamp("1781786117679") == 1781786117679


def test_parse_timestamp_accepts_iso_variants():
    assert parse_timestamp("2026-06-18T12:35:17Z") == 1781786117000
    assert parse_timestamp("2026-06-18T12:35:17.679Z") == 1781786117679
    assert parse_timestamp("2026-06-18T09:35:17-03:00") == 1781786117000


def test_parse_timestamp_rejects_garbage():
    assert parse_timestamp("banana") is None
    assert parse_timestamp("not-a-date") is None


def test_canonicalize_expands_epoch_marker():
    text, warnings = canonicalize("evento em {{ts:1781786117679}}")
    assert text == (
        "evento em 09:35:17 18/06/2026 BRT (epoch 1781786117679 · "
        "2026-06-18T12:35:17.679Z)"
    )
    assert warnings == []


def test_canonicalize_expands_iso_marker():
    text, warnings = canonicalize("{{ts:2026-06-18T12:35:17Z}}")
    assert "18/06/2026" in text
    assert warnings == []


def test_canonicalize_leaves_malformed_marker_intact_and_reports_it():
    text, warnings = canonicalize("evento em {{ts:banana}} nada mais")
    assert "{{ts:banana}}" in text
    assert warnings == ["{{ts:banana}}"]


def test_canonicalize_converts_bare_iso_datetime():
    text, warnings = canonicalize("visto em 2026-09-06T15:33:17.123Z antes")
    assert "12:33:17 06/09/2026 BRT" in text
    assert warnings == []


def test_canonicalize_does_not_double_wrap_already_canonical_text():
    canonical = format_ms(1781786117679)
    text, warnings = canonicalize(f"data: {canonical}")
    assert text == f"data: {canonical}"
    assert warnings == []


def test_canonicalize_leaves_event_explorer_url_untouched():
    url = (
        "https://app.datadoghq.com/event/explorer?query=x"
        "&from_ts=1788705982115&to_ts=1789051582115&live=false"
    )
    text, warnings = canonicalize(url)
    assert text == url
    assert warnings == []


def test_canonicalize_leaves_bare_13_digit_run_untouched():
    text, warnings = canonicalize("span_id 1788705982115 no rastreio")
    assert text == "span_id 1788705982115 no rastreio"
    assert warnings == []
