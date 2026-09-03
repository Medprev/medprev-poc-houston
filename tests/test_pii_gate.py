"""E5 proof: a synthetic report contaminated by each PII class never passes."""
from houston.pii_gate import is_clean, scan


def test_clean_report_passes():
    assert is_clean("Root cause: connection timeout after 5000ms in axios client.")


def test_cpf_is_caught():
    assert "cpf" in scan("Customer document 123.456.789-09 failed lookup.")


def test_cnpj_is_caught():
    assert "cnpj" in scan("Partner CNPJ 12.345.678/0001-95 not found.")


def test_email_is_caught():
    assert "email" in scan("Contact carla.cury@medprevonline.com for details.")


def test_br_phone_is_caught():
    assert "br_phone" in scan("Called back at (11) 98888-7766 with no answer.")


def test_br_phone_without_parens_is_still_caught():
    assert "br_phone" in scan("Called from 11 98888-7766 yesterday.")


def test_bare_digit_run_is_not_a_false_positive_br_phone():
    # Found live (2026-09-02): a real investigation quoted "2525252525",
    # a fragment of a cascading percent-encoded URL slug, as evidence.
    # No separators at all -- must not be scanned as a phone number.
    assert scan(
        "the slug is fazenda-rio%2525252525252525252525252520grande"
    ) == []


def test_luhn_valid_pan_is_caught():
    # 4111111111111111 is a well-known Luhn-valid test Visa number
    assert "pan" in scan("Card 4111 1111 1111 1111 declined at checkout.")


def test_luhn_invalid_number_is_not_a_false_positive():
    # a 16-digit number that fails Luhn should not be flagged as a card
    assert scan("Order reference 1234567812345678 was cancelled.") == []


def test_multiple_pii_classes_all_caught():
    text = "User carla.cury@medprevonline.com, CPF 123.456.789-09, called (11) 98888-7766."
    hits = scan(text)
    assert set(hits) == {"email", "cpf", "br_phone"}


def test_bare_epoch_millisecond_timestamp_is_not_a_false_positive_pan():
    # Found live against production data (2026-09-01): observed.last_seen
    # 1788270085136 is a 13-digit epoch-ms value that happens to pass Luhn.
    # A bare, unformatted 13-digit integer is not scannable as a card number.
    assert scan("last_seen: 1788270085136") == []
    assert scan("first_seen: 1785960141573\nlast_seen: 1788270085136") == []


def test_16_digit_card_with_separators_still_caught_at_common_length():
    assert "pan" in scan("Card 4111 1111 1111 1111 declined.")
    assert "pan" in scan("Card 4111-1111-1111-1111 declined.")


def test_bare_16_digit_card_still_caught_even_without_separators():
    # 16 digits is a common PAN length, so it's scanned regardless of formatting
    assert "pan" in scan("Card 4111111111111111 declined.")


def test_epoch_timestamp_followed_by_a_space_is_not_a_card():
    """Regression test: the separator check read the match text, whose
    trailing optional [ -] had already swallowed the following space -- so a
    bare 13-digit epoch was classified as card-formatted and Luhn-checked,
    reopening exactly the bug ADR-0004 closed. 1788293058029 is this
    branch's own window.to_ms (ADR-0017)."""
    assert scan("em 1788293058029 ocorreu") == []
    assert scan("duration 1788270085136 ns") == []


def test_two_iso_dates_in_a_row_are_not_a_card():
    """The report contract mandates a `## Linha do tempo` section of dates,
    and two space-separated ISO dates are 16 Luhn-valid digits."""
    assert scan("Primeira ocorrencia 2022-07-25 2026-09-01 ainda ativo") == []
    assert scan("2022-07-25 2026-09-01") == []


def test_amex_grouping_is_still_a_card():
    assert "pan" in scan("Card 3782 822463 10005 on file.")


def test_technical_ids_are_not_documents():
    """A bare 11- or 14-digit run is only a CPF/CNPJ if it passes the real
    check digits; span and trace ids do not (ADR-0017)."""
    assert scan("span_id: 12345678901") == []
    assert scan("trace_id: 12345678901234") == []


def test_bare_but_valid_documents_are_caught():
    assert "cpf" in scan("documento 12345678909 do paciente")
    assert "cnpj" in scan("cnpj 12345678000195 do parceiro")


def test_repeated_digit_run_is_not_a_document():
    assert scan("id 11111111111 no cache") == []


def test_unformatted_brazilian_phone_formats_are_caught():
    """ADR-0012 narrowed the phone rule to "requires a dash before the last
    four digits", which dropped the most common real formats. The rule is
    now shape plus a real area code (ADR-0017)."""
    for text in ("(41) 999998888", "41999998888", "+55 41 99999 8888", "4133334444"):
        assert "br_phone" in scan(text), text


def test_a_digit_run_with_an_unassigned_area_code_is_not_a_phone():
    # 25 is not an assigned DDD -- this is the live false positive of ADR-0012
    assert scan("the slug is fazenda-rio%2525252525252525252525252520grande") == []
    assert scan("2525252525") == []


def test_accepted_gap_a_pan_inside_a_longer_digit_run_is_not_scanned():
    """Documented, measured tradeoff (ADR-0017): sliding a 16-digit window
    over a 28-digit id gives 13 windows, each ~10% likely to pass Luhn by
    chance -- around 75% odds of quarantining any report that quotes one
    long id. This asserts the gap exists on purpose."""
    assert scan("id=12344111111111111111") == []
