"""Gate before every write to reports/. Catches CPF, CNPJ, email, Brazilian
phone, and Luhn-validated card numbers. Does NOT catch a person's proper
name in free text — that gap is real and documented in ADR-0003; the
mitigating practice is evidence as pointer+query, never pasted log text.

Every class here is validated by structure, not by digit count alone: a
report body is full of epoch timestamps, trace ids and ISO dates, and each
false positive quarantines an investigation that was already paid for
(ADR-0017). The reverse is also true — the phone rule is shape + real area
code, not "requires a dash", so the common unformatted Brazilian formats
are caught.
"""
import re

# CPF/CNPJ candidates are matched by shape first; a bare digit run then has
# to pass the real check-digit algorithm. Punctuation is itself a
# declaration of intent, so a formatted run is treated as PII either way.
_CPF_CANDIDATE = re.compile(r"\b(\d{3})([.\s-]?)(\d{3})[.\s-]?(\d{3})[.\s-]?(\d{2})\b")
_CNPJ_CANDIDATE = re.compile(
    r"\b(\d{2})([.\s-]?)(\d{3})[.\s-]?(\d{3})[/\s-]?(\d{4})[-\s]?(\d{2})\b"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Real Brazilian area codes (DDD). "2525252525" — the live false positive
# in ADR-0012 — is rejected here because 25 is not an assigned DDD, which
# is what lets this rule accept the unformatted forms that ADR-0012's
# dash requirement had to drop: (41) 999998888, 41999998888, 4133334444.
_DDD = r"(?:1[1-9]|2[12478]|3[1-578]|4[1-9]|5[1345]|6[1-9]|7[134579]|8[1-9]|9[1-9])"
_BR_PHONE = re.compile(
    r"(?:\+?55[\s.-]?)?"                      # optional country code
    rf"(?:\({_DDD}\)|\b{_DDD})"               # area code, parenthesised or bare
    r"[\s.-]?"
    r"(?:9[\s.-]?\d{4}[\s.-]?\d{4}"           # mobile: 9 + 8 digits
    r"|[2-5]\d{3}[\s.-]?\d{4})"               # landline: 2-5 + 7 digits
    r"\b"
)

# Separators may only sit *between* digits: an earlier version allowed a
# trailing one, so "1788293058029 " (epoch ms + the following space) was
# read as separator-formatted and Luhn-checked (ADR-0017).
_CARD_CANDIDATE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")

# Real PANs are almost always 15 (Amex) or 16 (Visa/Mastercard/Discover)
# digits. A bare 13-digit run with no separators is far more likely a Unix
# epoch-millisecond timestamp than a card number — front-matter fields like
# observed.first_seen/last_seen are exactly 13 digits and pass Luhn by pure
# chance roughly 1 in 10 times (ADR-0004).
_COMMON_PAN_LENGTHS = {15, 16}

# Accepted gap (ADR-0017): a digit run of 20+ characters is not scanned for
# an embedded PAN. Sliding a 16-digit window over a 28-digit id yields 13
# windows, each ~10% likely to pass Luhn by chance — around a 75% chance of
# quarantining any report that quotes one long id.


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


def _cpf_valid(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != int(digits[size]):
            return False
    return True


def _cnpj_valid(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for weights, position in (
        ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], 12),
        ([6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], 13),
    ):
        total = sum(int(digits[i]) * w for i, w in enumerate(weights))
        check = 11 - total % 11
        if (0 if check >= 10 else check) != int(digits[position]):
            return False
    return True


def _is_card_shaped(candidate: str) -> bool:
    """Card grouping, not merely "has a separator": one separator character
    throughout and groups of 4+ digits (the last may be 3+). Two ISO dates
    in a row — "2022-07-25 2026-09-01" — are 16 Luhn-valid digits and are
    rejected here, which matters because the report contract mandates a
    `## Linha do tempo` section of dates."""
    separators = set(re.findall(r"[ -]", candidate))
    if len(separators) != 1:
        return False
    groups = re.split(r"[ -]", candidate)
    return all(len(g) >= 4 for g in groups[:-1]) and len(groups[-1]) >= 3


def _document_hit(
    candidate_re: re.Pattern[str], text: str, validator
) -> bool:
    for match in candidate_re.finditer(text):
        raw = re.sub(r"\D", "", match.group())
        # Only canonical document punctuation counts as a declaration of
        # intent; space-separated digit groups occur in ordinary report
        # text, so those still have to pass the check digits.
        formatted = bool(re.search(r"[.\-/]", match.group()))
        if formatted or validator(raw):
            return True
    return False


class PiiFinding(str):
    """A PII class name, e.g. 'cpf', 'email'."""


def scan(text: str) -> list[str]:
    """Returns the list of PII classes found, empty if clean."""
    hits: list[str] = []
    if _document_hit(_CPF_CANDIDATE, text, _cpf_valid):
        hits.append("cpf")
    if _document_hit(_CNPJ_CANDIDATE, text, _cnpj_valid):
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
        card_shaped = _is_card_shaped(candidate)
        bare_common_length = (
            length in _COMMON_PAN_LENGTHS and not re.search(r"[ -]", candidate)
        )
        if not (card_shaped or bare_common_length):
            continue
        if _luhn_valid(raw_digits):
            hits.append("pan")
            break
    return hits


def is_clean(text: str) -> bool:
    return not scan(text)
