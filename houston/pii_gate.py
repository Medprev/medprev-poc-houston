"""Gate before every write to reports/. Catches CPF, CNPJ, email, Brazilian
phone, and Luhn-validated card numbers. Does NOT catch a person's proper
name in free text — that gap is real and documented in ADR-0003; the
mitigating practice is evidence as pointer+query, never pasted log text."""
import re

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_BR_PHONE = re.compile(r"\b(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b")
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


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
        raw_digits = re.sub(r"[ -]", "", match.group())
        if 13 <= len(raw_digits) <= 19 and _luhn_valid(raw_digits):
            hits.append("pan")
            break
    return hits


def is_clean(text: str) -> bool:
    return not scan(text)
