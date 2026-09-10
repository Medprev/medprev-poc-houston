"""Canonical timestamp rendering. The model never converts a date or builds
one itself (same rule ADR-0011 already applies to datadog_url) -- every
timestamp in a report is rendered here, in code, and the prompt only tells
the model where to put one.

Not a fixed UTC-3: Error Tracking findings carry `first_seen` back to 2022
(issue ids like `...-11ed-...`), and Brazil observed DST until 2019-02-17.
`zoneinfo` resolves the correct offset (and label) for any date on either
side of that cutoff.
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")

_OFFSET_LABELS = {
    "-03:00": "BRT",
    "-02:00": "BRST",  # summer time, retired 2019-02-17
}

_MARKER_RE = re.compile(r"\{\{ts:([^}]+)\}\}")
_BARE_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
_CANONICAL_RE = re.compile(
    r"\d{2}:\d{2}:\d{2} \d{2}/\d{2}/\d{4} BRS?T \(epoch \d+ · [^)]+\)"
)


def format_ms(ms: int | None) -> str | None:
    """`HH:MM:SS dd/mm/yyyy BRT (epoch <ms> · <ISO-8601 UTC>)` -- hour
    first, as requested. Integer arithmetic throughout: no float rounding
    of a millisecond epoch."""
    if ms is None:
        return None
    seconds, millis = divmod(int(ms), 1000)
    utc = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=millis * 1000
    )
    local = utc.astimezone(SAO_PAULO)
    offset = local.strftime("%z")
    offset_label = f"{offset[:3]}:{offset[3:]}"
    label = _OFFSET_LABELS.get(offset_label, "BRT")
    return (
        f"{local:%H:%M:%S %d/%m/%Y} {label} "
        f"(epoch {int(ms)} · {utc.isoformat(timespec='milliseconds').replace('+00:00', 'Z')})"
    )


def parse_timestamp(value: str) -> int | None:
    """13-digit epoch milliseconds, or an ISO-8601 datetime (Z / ±HH:MM
    offset, optional fractional seconds). None for anything else -- callers
    decide what to do with an unparseable value, this function never
    guesses."""
    value = value.strip()
    if re.fullmatch(r"\d{13}", value):
        return int(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def canonicalize(text: str) -> tuple[str, list[str]]:
    """Replaces `{{ts:<value>}}` markers and bare ISO-8601 datetimes with
    the canonical string. A marker whose value doesn't parse is left
    intact and reported back so the caller can warn instead of silently
    dropping it. Bare 13-digit digit runs are never touched here -- they
    may be ids, and they sit inside from_ts=/to_ts= URLs this project
    already builds."""
    warnings: list[str] = []

    def _expand_marker(match: re.Match) -> str:
        raw = match.group(1)
        parsed = parse_timestamp(raw)
        if parsed is None:
            warnings.append(match.group(0))
            return match.group(0)
        return format_ms(parsed)

    text = _MARKER_RE.sub(_expand_marker, text)

    def _expand_bare_iso(match: re.Match) -> str:
        parsed = parse_timestamp(match.group(0))
        return format_ms(parsed) if parsed is not None else match.group(0)

    # Skip ISO datetimes that are already inside a canonical string (the
    # "· <ISO>)" tail produced above) so a second pass never double-wraps.
    pieces = []
    last_end = 0
    for m in _CANONICAL_RE.finditer(text):
        pieces.append(_BARE_ISO_RE.sub(_expand_bare_iso, text[last_end:m.start()]))
        pieces.append(m.group(0))
        last_end = m.end()
    pieces.append(_BARE_ISO_RE.sub(_expand_bare_iso, text[last_end:]))
    text = "".join(pieces)

    return text, warnings
