"""Gate before every write to reports/. Catches CPF, CNPJ, email, Brazilian
phone, and Luhn-validated card numbers. Does NOT catch a person's proper
name in free text — that gap is real and documented in ADR-0003; the
mitigating practice is evidence as pointer+query, never pasted log text."""
import re

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Requires a real separator between the area code and the number, and a
# dash before the last four digits -- a bare, unformatted 10-digit run
# (e.g. a repeating pattern lifted from a malformed URL, or any other
# technical digit string that happens to be 10 digits long) is not scanned.
# Found live (2026-09-02): a real investigation quoted "2525252525" -- a
# fragment of a cascading percent-encoded slug in the evidence section --
# and the old permissive regex (no separator required at all) matched it
# as a phone number.
_BR_PHONE = re.compile(
    r"(?:\+?55\s?)?(?:\(\d{2}\)|\b\d{2})[\s.-]9?\d{4}-\d{4}\b"
)
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# Real PANs are almost always 15 (Amex) or 16 (Visa/Mastercard/Discover)
# digits. A bare 13-digit run with no separators is far more likely a Unix
# epoch-millisecond timestamp than a card number — front-matter fields like
# observed.first_seen/last_seen are exactly 13 digits and pass Luhn by pure
# chance roughly 1 in 10 times. Only treat a 13/14/17-19 digit run as a card
# candidate when it carries card-like formatting (a space or dash separator);
# an unformatted machine-generated integer of that length is not scanned.
_COMMON_PAN_LENGTHS = {15, 16}


def _luhn_valid(digits: str) -> bool:
    digits = digits[::-1]
    total = 0
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PiiFinding(str):
    """A PII class name, e.g. 'cpf', 'email'."""


def scan(text: str) -> list[str]:
    """Returns the list of PII classes found, empty if clean."""
    hits: list[str] = []
    if _CPF.search(text):
        hits.append("cpf")
    if _CNPJ.search(text):
        hits.append("cnpj")
    if _EMAIL.search(text):
        hits.append("email")
    if _BR_PHONE.search(text):
        hits.append("br_phone")
    for match in _CARD_CANDIDATE.finditer(text):
        candidate = match.group()
        raw_digits = re.sub(r"[ -]", "", candidate)
        length = len(raw_digits)
        if length not in range(13, 20):
            continue
        has_separator = " " in candidate or "-" in candidate
        if length not in _COMMON_PAN_LENGTHS and not has_separator:
            continue  # unformatted 13/14/17-19-digit run: likely a timestamp or id, not a card
        if _luhn_valid(raw_digits):
            hits.append("pan")
            break
    return hits


def is_clean(text: str) -> bool:
    return not scan(text)
