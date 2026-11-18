"""Post-check: numbers in answer segments that cite [fin_N] must match a row cited there.
ponytail: regex heuristic over sentences/table rows; derived numbers (differences, ratios
between rows) still get flagged. Swap in an LLM claim extractor if that noise matters."""
import re

_SCALE = {"crore": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "billion": 1e9, "bn": 1e9,
          "million": 1e6, "mn": 1e6}
_FIN = re.compile(r"\bfin_\d+\b")
# Things that look like numbers but aren't figures: citations, quarter/FY names, dates, years.
_NOISE = re.compile(
    r"\b(?:chunk|fin)_\d+\b|\bQ[1-4]\b|\bFY\s*'?\d{2,4}\b|\b20\d{2}\s*[-–/]\s*\d{2}\b"
    r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
    r"|\b(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-']*\d{2,4}\b"
    r"|\b(?:19|20)\d{2}\b", re.I)
_NUM = re.compile(r"(₹\s?)?(-?\d[\d,]*(?:\.(\d+))?)\s*(crores?|cr|lakhs?|billion|bn|million|mn|%|×|x\b)?", re.I)
_CHANGE = re.compile(r"\b(?:rose|rise|rising|fell|fall|falling|up|down|grew|grow\w*|increase\w*|decrease\w*|"
                     r"declin\w*|jump\w*|drop\w*|surg\w*|higher|lower|improv\w*|yoy|qoq|y-o-y|q-o-q|"
                     r"year-on-year|quarter-on-quarter)\b", re.I)
_WORD_AFTER = re.compile(r"\s*[a-z]", re.I)   # _NUM may already have consumed the space


def _segments(answer: str) -> list[str]:
    out = []
    for line in answer.splitlines():
        out.extend([line] if line.lstrip().startswith("|") else re.split(r"(?<=[.!?])\s+", line))
    return out


def _close(x: float, row_value: float, unit: str, decimals: int) -> bool:
    if unit == "INR":
        return abs(x - row_value) <= 0.005 * abs(row_value)
    # pct/ratio/EPS: the number must be the row rounded to the decimals actually written
    return abs(x - row_value) <= 0.5 * 10 ** -decimals + 1e-9


def check_numbers(answer: str, ids: dict) -> dict:
    if not ids:
        return {"checked": 0, "unmatched": []}
    all_rows = [r for _, r in ids.values()]
    checked, unmatched = 0, []
    for seg in _segments(answer):
        cited = [ids[f][1] for f in _FIN.findall(seg) if f in ids]
        if not _FIN.search(seg):
            continue
        rows = cited or all_rows
        text = _NOISE.sub(lambda m: " " * len(m.group()), seg)
        for m in _NUM.finditer(text):
            rupee, raw, decimals = m.group(1), m.group(2), len(m.group(3) or "")
            unit = (m.group(4) or "").lower().rstrip("s") or None
            v = float(raw.replace(",", ""))
            if unit == "%":
                if _is_change(text, m) or not any(r.unit == "pct" for r in rows):
                    continue      # a growth %, not a table value
                cands = [(v, r) for r in rows if r.unit == "pct"]
            elif unit in ("×", "x"):
                cands = [(v, r) for r in rows if r.unit == "ratio"]
            elif unit in _SCALE:
                cands = [(v * _SCALE[unit], r) for r in rows if r.unit == "INR"]
            else:
                if not rupee and (_WORD_AFTER.match(text, m.end()) or (v.is_integer() and abs(v) < 10)):
                    continue      # counts like "12 months", "156 countries", "3 quarters"
                cands = [(v * 1e7 if r.unit == "INR" else v, r) for r in rows]
            checked += 1
            if not any(_close(x, r.value, r.unit, decimals) for x, r in cands):
                unmatched.append(m.group(0).strip())
    return {"checked": checked, "unmatched": unmatched}


def _is_change(text: str, m: re.Match) -> bool:
    """A % is a change ("fell 15%", "up by 3%", "3% YoY"), not a level ("fell to 1.2%")."""
    words = text[max(0, m.start() - 30):m.start()].split()[-2:]
    if words and words[-1].lower() in _LEVEL_WORDS:
        return False
    return bool(_CHANGE.search(" ".join(words)) or _CHANGE.match(text[m.end():m.end() + 15].strip()))


_LEVEL_WORDS = {"to", "at", "of", "was", "is", "were", "stood", "=", ":"}
