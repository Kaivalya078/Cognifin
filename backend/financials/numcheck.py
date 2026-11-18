"""Post-check: numbers in answer segments that cite [fin_N] must match a verified row.
ponytail: regex heuristic over sentences/table rows; swap in an LLM claim extractor
if the Phase 4 eval shows false flags."""
import re

_SCALE = {"crore": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "billion": 1e9, "bn": 1e9,
          "million": 1e6, "mn": 1e6}
_FIN = re.compile(r"\bfin_\d+\b")
# Things that look like numbers but aren't figures: citations, quarter/FY names, dates, years.
_NOISE = re.compile(
    r"\b(?:chunk|fin)_\d+\b|\bQ[1-4]\b|\bFY\s*'?\d{2,4}\b|\b20\d{2}\s*[-–/]\s*\d{2}\b"
    r"|\b(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-']*\d{2,4}\b"
    r"|\b(?:19|20)\d{2}\b", re.I)
_NUM = re.compile(r"(₹\s?)?(-?\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|billion|bn|million|mn|%|×|x\b)?", re.I)


def _segments(answer: str) -> list[str]:
    out = []
    for line in answer.splitlines():
        out.extend([line] if line.lstrip().startswith("|") else re.split(r"(?<=[.!?])\s+", line))
    return out


def _close(a: float, b: float, unit: str) -> bool:
    return abs(a - b) <= 0.005 * abs(b) if unit == "INR" else abs(a - b) <= 0.05


def check_numbers(answer: str, ids: dict) -> dict:
    rows = [r for _, r in ids.values()]
    if not rows:
        return {"checked": 0, "unmatched": []}
    has_pct = any(r.unit == "pct" for r in rows)
    checked, unmatched = 0, []
    for seg in _segments(answer):
        if not _FIN.search(seg):
            continue
        text = _NOISE.sub(lambda m: " " * len(m.group()), seg)
        for m in _NUM.finditer(text):
            rupee, raw, unit = m.group(1), m.group(2), (m.group(3) or "").lower().rstrip("s") or None
            v = float(raw.replace(",", ""))
            if unit == "%":
                if not has_pct:
                    continue      # a growth % next to a rupee figure, not a table value
                cands = [(v, r) for r in rows if r.unit == "pct"]
            elif unit in ("×", "x"):
                cands = [(v, r) for r in rows if r.unit == "ratio"]
            elif unit in _SCALE:
                cands = [(v * _SCALE[unit], r) for r in rows if r.unit == "INR"]
            else:
                if not rupee and v.is_integer() and abs(v) < 10:
                    continue      # counts like "3 quarters"
                cands = [(v * 1e7 if r.unit == "INR" else v, r) for r in rows]
            checked += 1
            if not any(_close(x, r.value, r.unit) for x, r in cands):
                unmatched.append(m.group(0).strip())
    return {"checked": checked, "unmatched": unmatched}
