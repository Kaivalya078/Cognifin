"""Checks every candidate passes before it is stored. Each returns None on pass, else a reason."""
from collections import defaultdict
import re
import statistics

from financials.store import Candidate


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def check_verbatim(c: Candidate, page_text: str) -> str | None:
    """The printed string occurs on the page as a whole token (not inside a longer number)."""
    if c.method == "xbrl":
        return None
    # OCR spacing: a space beside a separator, or a space in place of a comma ("13 575.93")
    sep = {",": r"(?:\s*,\s*|\s)", ".": r"\s*\.\s*", " ": r"\s*"}
    p = "".join(sep.get(ch, re.escape(ch)) for ch in _norm(c.printed))
    if re.search(rf"(?<![\d.,]){p}(?![\d]|[.,]\d)", _norm(page_text)):
        return None
    return f"verbatim: {c.printed!r} not on page {c.page}"


def check_arithmetic(group: list[Candidate], rounding: float,
                     direct_pbt: bool = True) -> dict[str, str]:
    """One company/basis/period. Rule 1: revenue + other income = total income.
    Rule 2 (only when no exceptional/discontinued/associate line sits between them):
    PBT - tax = net profit. Tolerance: 2 rounding units."""
    v = {c.metric: c.value for c in group}
    tol = 2 * rounding
    rules = [(("revenue_from_operations", "other_income"), "total_income", 1)]
    if direct_pbt:
        rules.append((("profit_before_tax", "tax_expense"), "net_profit", -1))
    out = {}
    for (a, b), total, sign in rules:
        if a in v and b in v and total in v:
            got = v[a] + sign * v[b]
            if abs(got - v[total]) > tol:
                reason = f"arithmetic: {a} {'+-'[sign < 0]} {b} = {got:.0f} != {total} {v[total]:.0f}"
                out.update({m: reason for m in (a, b, total)})
    b, d = v.get("eps_basic"), v.get("eps_diluted")
    if b is not None and d is not None and abs(d) > abs(b) + 0.011:
        out.update(dict.fromkeys(("eps_basic", "eps_diluted"),
                                 f"arithmetic: diluted EPS {d} above basic {b}"))
    return out


def check_ratio(c: Candidate) -> str | None:
    if c.unit == "pct" and not 0 <= c.value <= 100:
        return f"ratio: {c.value} outside 0-100"
    if c.metric == "solvency_ratio" and not 0.5 <= c.value <= 10:
        return f"ratio: solvency {c.value}x outside 0.5-10"
    return None


def check_plausible(c: Candidate, same_metric_other_periods: list[float]) -> str | None:
    """Reject a value >100x off the median magnitude of the same metric in other periods."""
    others = [abs(x) for x in same_metric_other_periods if x]
    if len(others) < 3 or not c.value:   # two points can't say which one is off
        return None
    med = statistics.median(others)
    r = abs(c.value) / med
    if r > 100 or r < 0.01:
        return f"plausible: {c.value:.4g} is {r:.3g}x the median {med:.4g}"
    return None


# pairs that may print the same figure, and the value that has to be 0 for it (None: always)
_SAME_OK = {frozenset({"eps_basic", "eps_diluted"}): None,
            frozenset({"net_profit", "net_profit_owners"}): None,   # no minority interest
            frozenset({"revenue_from_operations", "total_income"}): "other_income",
            frozenset({"profit_before_tax", "net_profit"}): "tax_expense",
            frozenset({"profit_before_tax", "net_profit_owners"}): "tax_expense"}


def check_duplicates(group: list[Candidate]) -> set[int]:
    """One filing/basis/period: a non-zero figure printed once and stored as two metrics is
    a label misread (TITAN's PBT as net profit), and which of the two is wrong is unknown.
    Returns id() of every candidate to send to review."""
    zero = {c.metric for c in group if c.value == 0}
    by_fig = defaultdict(list)
    for c in group:
        if c.value:
            by_fig[c.printed.strip(), c.unit].append(c)
    out = set()
    for same in by_fig.values():
        for i, a in enumerate(same):
            for b in same[i + 1:]:
                pair = frozenset({a.metric, b.metric})
                if pair in _SAME_OK and (_SAME_OK[pair] is None or _SAME_OK[pair] in zero):
                    continue
                out |= {id(a), id(b)}
    return out
