"""Rebuild index_cache/financials.duckdb from data/quarterly/sources.csv.

    python -m financials.build [--no-llm]
"""
import re
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from financials.checks import check_arithmetic, check_plausible, check_ratio, check_verbatim
from financials.ixbrl import parse_ixbrl
from financials.metrics import metrics_for
from financials.numbers import parse_number
from financials.pdf_llm import extract_llm
from financials.pdf_rules import check_columns, extract_rules
from financials.sources import load_sources
from financials.store import Candidate, review_row, write_db

BACKEND = Path(__file__).resolve().parents[1]
# Insurers print these in both the policyholders' and shareholders' accounts; never stored.
LI_AMBIGUOUS = {"revenue_from_operations", "other_income", "total_income", "total_expenses"}


def wanted(kind: str) -> list[str]:
    ms = metrics_for(kind)
    return [m for m in ms if m not in LI_AMBIGUOUS] if kind == "LI" else ms


class _Counting:
    """Wraps an OpenAI-style client (built lazily) and counts real calls."""

    def __init__(self, client):
        self._client, self.calls = client, 0
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls += 1
        if self._client is None:
            from financials.pdf_llm import _client
            self._client = _client()
        return self._client.chat.completions.create(**kw)


def normalise(c: Candidate) -> Candidate:
    """Solvency is printed as a multiple (1.97), a percent (180.0) or, in one SBILIFE filing,
    a hundredth (0.0196); store it as a multiple. The regulatory floor is 1.5x, so a multiple
    above 10 is a percent and one below 0.1 a hundredth."""
    if c.metric == "solvency_ratio" and c.value > 10:
        return replace(c, value=round(c.value / 100, 4))
    if c.metric == "solvency_ratio" and 0 < c.value < 0.1:
        return replace(c, value=round(c.value * 100, 4))
    return c


def _rounding(group: list[Candidate]) -> float:
    """One unit of the last printed digit, in rupees (largest across the group's INR values)."""
    r = 0.0
    for c in group:
        p = parse_number(c.printed)
        if c.unit == "INR" and p:
            dec = len(c.printed.split(".")[1].rstrip(")")) if "." in c.printed else 0
            r = max(r, abs(c.value / p) * 10 ** -dec)
    return r


def _check_pdf(cands: list[Candidate], pages: dict[int, str],
               trusted: list[Candidate] = ()) -> tuple[list[Candidate], list[dict]]:
    """Verbatim + ratio per value, then arithmetic per basis/period. `trusted` values already
    passed alone: they take part in the arithmetic but are never rejected by it."""
    ok, bad = [], []
    for c in cands:
        if c.method == "llm" and check_verbatim(c, pages.get(c.page, "")):
            # the LLM cited the wrong page: take the one sent page that prints the value
            hits = [p for p, t in pages.items() if not check_verbatim(replace(c, page=p), t)]
            c = replace(c, page=hits[0]) if len(hits) == 1 else c
        reason = check_verbatim(c, pages.get(c.page, "")) or check_ratio(c)
        (bad.append(review_row(c, reason)) if reason else ok.append(c))
    groups = defaultdict(list)
    for c in [*trusted, *ok]:
        groups[c.basis, c.period_type].append(c)
    keep = []
    for g in groups.values():
        text = " ".join(pages.get(c.page, "") for c in g).lower()
        fails = check_arithmetic(g, _rounding(g),
                                 direct_pbt=not re.search(r"associate|joint venture|discontinued|regulatory deferral", text))
        for c in g:
            if any(c is t for t in trusted):
                continue
            (bad.append(review_row(c, fails[c.metric])) if c.metric in fails else keep.append(c))
    return keep, bad


def _status(cands: list[Candidate]) -> str:
    per_basis = defaultdict(set)
    for c in cands:
        if c.period_type == "Q":
            per_basis[c.basis].add(c.metric)
    n = max((len(v) for v in per_basis.values()), default=0)
    return "parsed" if n >= 6 else "partial" if n else "failed"


def build(sources_dir: Path, out_db: Path, use_llm: bool = True, client=None,
          cache_dir: Path | None = None) -> dict:
    sources_dir = Path(sources_dir)
    cache_dir = Path(cache_dir) if cache_dir else BACKEND / "index_cache" / "financials_llm_cache"
    srcs = load_sources(sources_dir)
    kind_of = {}
    for s in sorted(srcs, key=lambda s: s.period_end):
        if s.kind != "PDF":
            kind_of[s.symbol] = s.kind
    llm = _Counting(client)
    llm_files = 0
    rows, filings, review = [], [], []

    for s in srcs:
        filing = {"file": s.rel, "url": s.url, "symbol": s.symbol, "kind": s.kind,
                  "basis": s.basis, "period_end": s.period_end, "status": "failed",
                  "reason": None, "rounding": None, "audited": None}
        try:
            if s.kind != "PDF":
                cands, filing = parse_ixbrl(s)
                cands = [normalise(c) for c in cands]
                for c in cands:
                    reason = check_ratio(c)
                    (review.append(review_row(c, reason)) if reason else rows.append(c))
                filings.append(filing)
                continue
            kind = kind_of.get(s.symbol, "INDAS")
            want_m = set(wanted(kind))
            cands, pages = extract_rules(s)
            cands = [normalise(c) for c in cands if c.metric in want_m]
            ok, bad = _check_pdf(cands, pages)
            review += bad
            if use_llm and pages:
                # bases the rules read, plus any a page title names (a page the rules could
                # not lay out may be the only consolidated one)
                titled = {b for b in ("consolidated", "standalone")
                          for t in pages.values() if b in t[:1500].lower()}
                bases = sorted({c.basis for c in cands} | titled) or ["consolidated", "standalone"]
                ptypes = ["Q", "FY"] if s.period_end.month == 3 else ["Q"]
                have = {(c.basis, c.period_type, c.metric) for c in ok}
                missing = [(b, p, m) for b in bases for p in ptypes for m in sorted(want_m)
                           if (b, p, m) not in have
                           and not (m == "net_profit_owners" and b != "consolidated")]
                if missing:
                    llm_files += 1
                    got = [normalise(c) for c in extract_llm(s, pages, missing, cache_dir, client=llm)]
                    got, col_bad = check_columns(s, got)
                    review += col_bad
                    got_ok, got_bad = _check_pdf(got, pages, trusted=ok)
                    ok, review = ok + got_ok, review + got_bad
            rows += ok
            filing["status"] = _status(ok)
            if filing["status"] != "parsed":
                filing["reason"] = "no statement pages" if not pages else f"{len(ok)} values"
        except Exception as e:   # one bad file never stops the build
            filing.update(status="failed", reason=f"{type(e).__name__}: {e}")
        filings.append(filing)

    # plausibility across periods of the same company/basis/metric
    series = defaultdict(list)
    for c in rows:
        series[c.company, c.basis, c.period_type, c.metric].append(c)
    final = []
    for c in rows:
        others = [o.value for o in series[c.company, c.basis, c.period_type, c.metric] if o is not c]
        reason = check_plausible(c, others)
        (review.append(review_row(c, reason)) if reason else final.append(c))

    out_db = Path(out_db)
    out_db.parent.mkdir(parents=True, exist_ok=True)
    write_db(str(out_db), final, filings, review)
    keys = {c.key() for c in final}
    st = [f["status"] for f in filings]
    return {"files": len(srcs), "parsed": st.count("parsed"), "partial": st.count("partial"),
            "failed": st.count("failed"), "rows": len(keys),
            "review": len(review) + len(final) - len(keys),
            "llm_calls": llm.calls, "llm_cached": llm_files - llm.calls}


if __name__ == "__main__":
    summary = build(BACKEND / "data" / "quarterly", BACKEND / "index_cache" / "financials.duckdb",
                    use_llm="--no-llm" not in sys.argv)
    for k, v in summary.items():
        print(f"{k} {v}")
