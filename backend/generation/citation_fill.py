"""Add a citation where the model left one out, but only when every figure it states is matched.

A sentence (or table row) with no [chunk_N]/[fin_N] marker gets one when a number
it states appears in a context passage: whole numbers only, never substrings;
trailing decimal zeros ignored; a passage number may be rounded to the answer's
decimal places (never the reverse); no unit conversion. Pure, no I/O.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from core.citation_verifier import _REF, bare_chunk_id

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d+)?(?!\d)(\s*%)?")
_SEP_ROW = re.compile(r"\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MAX_PER_UNIT = 2


def _numbers(text: str, figures_only: bool) -> list[tuple[Decimal, int]]:
    out = []
    for m in _NUM.finditer(text):
        whole, frac, pct = m.group(1), m.group(2) or "", m.group(3)
        value = Decimal(whole.replace(",", "") + frac)
        places = len(frac) - 1 if frac else 0
        if figures_only:
            digits = (whole.replace(",", "") + frac[1:]).lstrip("0")
            is_year = not frac and not pct and "," not in whole and 1990 <= value <= 2039
            if is_year or not (len(digits) >= 3 or frac or pct):
                continue
        out.append((value, places))
    return out


def _matches(fig: tuple[Decimal, int], passage: list[tuple[Decimal, int]]) -> bool:
    value, places = fig
    for p, p_places in passage:
        if p == value:
            return True
        if p_places > places and p.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP) == value:
            return True
    return False


def _cite(unit: str, items: list[tuple[str, list]]) -> tuple[str, list[str]]:
    if _REF.search(unit):
        return unit, []
    hits = [next((cid for cid, nums in items if _matches(fig, nums)), None)
            for fig in _numbers(unit, figures_only=True)]
    # Every figure must be sourced: one invented number in the unit means no fill,
    # or the marker would vouch for it.
    if not hits or None in hits:
        return unit, []
    ids = list(dict.fromkeys(hits))[:_MAX_PER_UNIT]
    marks = "".join(f"[{i}]" for i in ids)
    body = unit.rstrip()
    tail = unit[len(body):]
    if body.endswith("|"):                     # table row: inside the last cell
        cell = body[:-1].rstrip()
        return f"{cell} {marks} |{tail}", ids
    if body and body[-1] in ".!?":
        return f"{body[:-1]} {marks}{body[-1]}{tail}", ids
    return f"{body} {marks}{tail}", ids


def fill_figure_citations(answer: str, context_items: list[tuple[str, str]]) -> tuple[str, list[str]]:
    items = [(bare_chunk_id(cid), _numbers(text, figures_only=False)) for cid, text in context_items]
    added: list[str] = []
    lines = []
    for line in answer.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or _SEP_ROW.fullmatch(line):
            lines.append(line)
            continue
        if stripped.startswith("|"):
            new, ids = _cite(line, items)
            added += ids
            lines.append(new)
            continue
        parts = _SENTENCE_END.split(line)
        seps = _SENTENCE_END.findall(line)
        out = []
        for i, part in enumerate(parts):
            new, ids = _cite(part, items)
            added += ids
            out.append(new + (seps[i] if i < len(seps) else ""))
        lines.append("".join(out))
    return "\n".join(lines), added
