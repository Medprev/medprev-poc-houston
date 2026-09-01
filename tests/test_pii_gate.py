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
