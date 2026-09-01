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
