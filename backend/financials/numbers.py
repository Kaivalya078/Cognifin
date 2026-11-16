"""Parsing of printed numbers, unit headers and dates."""
import re
from datetime import date, datetime

from financials.metrics import METRICS

_NUM = re.compile(r"^\(?[-–−]?\(?\d[\d,]*(\.\d+)?\)?$")
# plain, western (1,234,567) or Indian (12,34,567) grouping; anything else is an OCR slip
_GROUPED = re.compile(r"^(\d+|\d{1,3}(,\d{3})+|\d{1,2}(,\d{2})*,\d{3})(\.\d+)?$")


def parse_number(s: str) -> float | None:
    """'1,08,532.40' -> 108532.4; '(625.30)' / '-625.30' -> -625.3; '', '-', '—' -> None."""
    t = re.sub(r"(?<=[(\-–−])\s+|\s+(?=\))", "", (s or "").strip())
    if not t or not _NUM.match(t):   # internal spaces (OCR "3 4 . 2 2") never match
        return None
    if not _GROUPED.match(re.sub(r"[()\-–−]", "", t)):
        return None
    neg = t.startswith("(") or t.lstrip("(")[:1] in "-–−"
    v = float(re.sub(r"[^\d.]", "", t))
    return -v if neg else v


_UNITS = [
    (re.compile(r"\bcrores?[a-z]?\b|\bcr\b\.?", re.I), 1e7),   # "croresl": OCR
    (re.compile(r"\blakhs?\b|\blacs?\b", re.I), 1e5),
    (re.compile(r"\bmillions?\b|\bmn\b", re.I), 1e6),
    (re.compile(r"\bin\s+actuals?\b", re.I), 1.0),
]


def unit_multiplier(header_text: str) -> float | None:
    """Multiplier to rupees from a unit header like '(₹ in crore except per share data)'."""
    for rx, mult in _UNITS:
        if rx.search(header_text or ""):
            return mult
    return None


def to_value(printed: str, metric: str, multiplier: float) -> float:
    v = parse_number(printed)
    if v is None:
        raise ValueError(f"not a number: {printed!r}")
    return v * multiplier if METRICS[metric][1] == "INR" else v


_DATE_FMTS = ("%d-%m-%Y", "%d-%b-%Y", "%d.%m.%Y", "%d/%m/%Y", "%B %d, %Y", "%d %B, %Y",
              "%d %B %Y", "%d-%B-%Y", "%d %b %Y", "%d.%m.%y", "%b %d, %Y")


def parse_date(s: str) -> date:
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s.strip())
    t = re.sub(r"\s+", " ", t)
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"bad date: {s!r}")
