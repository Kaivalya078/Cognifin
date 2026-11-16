"""Checks every candidate passes before it is stored. Each returns None on pass, else a reason."""
import re
import statistics

from financials.store import Candidate


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def check_verbatim(c: Candidate, page_text: str) -> str | None:
    """The printed string occurs on the page as a whole token (not inside a longer number)."""
    if c.method == "xbrl":
        return None
    p = re.escape(_norm(c.printed)).replace(r"\ ", r"\s*")
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
    return out


def check_ratio(c: Candidate) -> str | None:
    if c.unit == "pct" and not 0 <= c.value <= 100:
        return f"ratio: {c.value} outside 0-100"
    return None


def check_plausible(c: Candidate, same_metric_other_periods: list[float]) -> str | None:
    """Reject a value >100x off the median magnitude of the same metric in other periods."""
    others = [abs(x) for x in same_metric_other_periods if x]
    if not others or not c.value:
        return None
    med = statistics.median(others)
    r = abs(c.value) / med
    if r > 100 or r < 0.01:
        return f"plausible: {c.value:.4g} is {r:.3g}x the median {med:.4g}"
    return None
