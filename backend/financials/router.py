"""Rule-based numeric router: question -> rows from the financials table (Phase 4).
A miss returns None and the caller answers from RAG alone, exactly as before."""
import re
from dataclasses import dataclass
from datetime import date

_QEND = {1: (6, 30), 2: (9, 30), 3: (12, 31), 4: (3, 31)}   # Indian FY quarter -> (month, day)
_MONTH_END = {"mar": (3, 31), "jun": (6, 30), "sep": (9, 30), "dec": (12, 31)}

_Q_FY = re.compile(r"\bq([1-4])\s*(?:of\s+)?fy\s*'?(\d{4}|\d{2})\b", re.I)
_MONTH = re.compile(r"\b(mar(?:ch)?|june?|sep(?:t(?:ember)?)?|dec(?:ember)?)[\s\-']*(\d{4}|\d{2})\b", re.I)
_FY = [re.compile(r"\bfy\s*'?(\d{4}|\d{2})\b", re.I),
       re.compile(r"\b20\d{2}\s*[-–/]\s*(\d{2})\b"),
       re.compile(r"\bfiscal\s+(?:year\s+)?(20\d{2})\b", re.I)]
_LAST_N = re.compile(r"\blast\s+(\d+)\s+quarters?\b", re.I)
_LAST_ONE = re.compile(r"\b(?:latest|last|most recent)\s+quarter\b", re.I)


@dataclass
class PeriodSpec:
    period_type: str                   # "Q" or "FY"
    ends: list[date] | None = None     # None: all periods of this type (or last_n)
    last_n: int | None = None


def _year(s: str) -> int:
    return int(s) if len(s) == 4 else 2000 + int(s)


def _mask(text: str, m: re.Match) -> str:
    return text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]


def parse_periods(question: str, years: list[str]) -> PeriodSpec:
    found: list[tuple[int, str, date]] = []        # (position, type, period end)
    text = question
    for m in list(_Q_FY.finditer(text)):
        q, fy = int(m.group(1)), _year(m.group(2))
        mo, d = _QEND[q]
        found.append((m.start(), "Q", date(fy if q == 4 else fy - 1, mo, d)))
        text = _mask(text, m)
    for m in list(_MONTH.finditer(text)):
        mo, d = _MONTH_END[m.group(1)[:3].lower()]
        found.append((m.start(), "Q", date(_year(m.group(2)), mo, d)))
        text = _mask(text, m)
    for rx in _FY:
        for m in list(rx.finditer(text)):
            found.append((m.start(), "FY", date(_year(m.group(1)), 3, 31)))
            text = _mask(text, m)
    if found:
        ptype = min(found)[1]
        return PeriodSpec(ptype, sorted({e for _, t, e in found if t == ptype}))
    if m := _LAST_N.search(question):
        return PeriodSpec("Q", last_n=int(m.group(1)))
    if _LAST_ONE.search(question):
        return PeriodSpec("Q", last_n=1)
    if years:
        return PeriodSpec("FY", sorted({date(int(y), 3, 31) for y in years}))
    return PeriodSpec("Q")
