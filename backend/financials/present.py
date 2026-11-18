"""Turn a router Lookup into what answer_question needs: a cited context block,
evidence items, chart data and the post-answer metadata."""
from dataclasses import dataclass

from financials.numcheck import check_numbers
from financials.query import DEFAULT_DB, Row
from financials.router import Lookup, Series, route

_HEADER = ("VERIFIED FIGURES (from company filings; these are authoritative — use these numbers exactly, "
           "prefer them over chunk text for the same metric and period. Every sentence or table row that "
           "uses one of these figures MUST cite it, e.g. [fin_3]):")
_DISPLAY = {"INR": ("₹ crore", 1e7), "pct": ("%", 1), "ratio": ("×", 1), "INR_per_share": ("₹ per share", 1)}


def fmt_value(value: float, unit: str) -> str:
    if unit == "INR":
        return f"₹{value / 1e7:,.1f} crore"
    if unit == "pct":
        return f"{value:.2f}%"
    if unit == "ratio":
        return f"{value:.2f}×"
    return f"₹{value:.2f}"


def period_label(row: Row) -> str:
    fy = f"FY{row.fiscal_year % 100:02d}"
    return fy if row.period_type == "FY" else f"Q{row.fiscal_quarter} {fy}"


def _source(row: Row) -> str:
    if row.source_url.lower().endswith((".html", ".htm")):
        return "NSE iXBRL filing"
    return f"BSE results filing p.{row.page}" if row.page else "BSE results filing"


def _words(metric: str) -> str:
    return metric.removesuffix("_pct").replace("_", " ")


_ACRONYMS = {"npa": "NPA", "eps": "EPS", "cet1": "CET1"}


def metric_label(metric: str) -> str:
    words = _words(metric).capitalize().split()
    return " ".join(_ACRONYMS.get(w.lower(), w) for w in words)


@dataclass
class Prepared:
    lookup: Lookup
    ids: dict[str, tuple[Series, Row]]
    block: str
    evidence: list[dict]


def prepare(question: str, companies: list[str], years: list[str], db: str = DEFAULT_DB) -> "Prepared | None":
    lookup = route(question, companies, years, db=db)
    if lookup is None:
        return None
    ids: dict[str, tuple[Series, Row]] = {}
    for s in lookup.series:
        for r in s.rows:
            ids[f"fin_{len(ids) + 1}"] = (s, r)
    lines = {fid: f"[{fid}] {s.company} | {r.metric} | {period_label(r)} | {s.basis} | "
                  f"{fmt_value(r.value, r.unit)} | {_source(r)}" for fid, (s, r) in ids.items()}
    notes = [f"not in verified table: {c}" for c in lookup.missing]
    if _mixed_basis(lookup.series):
        bases = ", ".join(f"{s.company} {s.basis}" for s in lookup.series if s.requested == lookup.metrics[0])
        notes.append(f"Note: bases differ between companies ({bases}); say so when comparing them.")
    block = "\n".join([_HEADER, *lines.values(), *notes])
    evidence = [{"chunk_id": fid, "snippet": lines[fid], "page_number": r.page or 0,
                 "document_label": f"{s.company} results {period_label(r)}", "pdf_url": r.source_url}
                for fid, (s, r) in ids.items()]
    return Prepared(lookup, ids, block, evidence)


def _mixed_basis(series: list[Series]) -> bool:
    """Do the charted (first requested metric) series use more than one basis?"""
    first = series[0].requested if series else None
    return len({s.basis for s in series if s.requested == first}) > 1


def _series_name(s: Series, mixed: bool) -> str:
    parts = ([_words(s.metric)] if s.metric != s.requested else []) \
        + ([s.basis] if mixed or s.basis == "standalone" else [])
    return s.company + (f" ({', '.join(parts)})" if parts else "")


def build_chart(prep: Prepared) -> "dict | None":
    first = prep.lookup.metrics[0]
    picked = [(fid, s, r) for fid, (s, r) in prep.ids.items() if s.requested == first]
    if len(picked) < 2:
        return None
    unit = picked[0][2].unit
    display, div = _DISPLAY[unit]
    mixed = _mixed_basis(prep.lookup.series)
    series: dict[int, dict] = {}
    for fid, s, r in picked:
        name = _series_name(s, mixed)
        entry = series.setdefault(id(s), {"company": s.company, "name": name, "metric": s.metric,
                                          "requested": s.requested, "label": metric_label(s.metric),
                                          "basis": s.basis, "points": []})
        entry["points"].append({"period_end": r.period_end.isoformat(), "label": period_label(r),
                                "value": r.value / div, "source_url": r.source_url, "page": r.page,
                                "fin_id": fid, "method": r.method})
    return {"unit": unit, "display_unit": display, "period_type": prep.lookup.period.period_type,
            "title": metric_label(first), "mixed_basis": mixed, "series": list(series.values())}


def finish(prep: "Prepared | None", answer: str) -> dict:
    if prep is None:
        return {"router": {"hit": False}, "chart": None, "numbers_check": None}
    return {"router": {"hit": True, "metrics": prep.lookup.metrics, "rows": len(prep.ids),
                       "missing": prep.lookup.missing},
            "chart": build_chart(prep), "numbers_check": check_numbers(answer, prep.ids)}


def assistant_metadata(payload: dict) -> dict:
    """What persist_exchange saves; `pipeline` mirrors where the frontend reads live metadata."""
    meta = payload.get("metadata", {})
    return {"citations": payload["citations"], "evidence": payload["evidence"],
            "pipeline": {"chart": meta.get("chart"), "numbers_check": meta.get("numbers_check")}}
