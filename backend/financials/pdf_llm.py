"""LLM fallback for metrics the PDF rules missed. Sees only the statement pages, returns
numbers exactly as printed; every answer is cached on disk so rebuilds are free and stable.
Its values go through the same checks as rule values (verbatim on the cited page)."""
import hashlib
import json
from datetime import date
from pathlib import Path

from financials.metrics import METRICS
from financials.numbers import parse_number, to_value, unit_multiplier, units_in
from financials.sources import Source
from financials.store import Candidate

PROMPT_VERSION = "1"
_PAGE_CHARS = 12000

_SYSTEM = """You read Indian listed-company quarterly results statements (text extracted from PDF).
Return JSON: {"items": [{"basis", "period_type", "metric", "printed", "column_header", "unit_header", "page"}]}.
Rules:
- Only the (basis, period_type, metric) triples asked for. Omit any you cannot find with certainty.
- basis: "standalone" or "consolidated", from the statement's heading.
- period_type "Q": the column for the quarter / three months ended on the period end date.
  "FY": the column for the year ended on the period end date (only when asked).
  Never use six/nine months, year-to-date or prior-period columns.
- printed: the number exactly as it appears on the page, e.g. "1,234.56" or "(625.30)".
- column_header: the header text of the column you used. unit_header: the unit text exactly
  as printed on that page (e.g. "(Rs. in crore except per share data)"); "" if none.
- page: the page number shown in the "=== PAGE n ===" marker.
Metric meanings: revenue_from_operations, other_income, total_income, total_expenses,
profit_before_tax, tax_expense (total), net_profit (profit for the period),
net_profit_owners (attributable to owners of the parent; consolidated only), eps_basic,
eps_diluted, interest_earned (banks), gross_npa_pct / net_npa_pct (% of gross / net NPA),
capital_adequacy_pct, cet1_pct, return_on_assets_pct, first_year_premium, renewal_premium,
single_premium, gross_premium, net_premium, solvency_ratio."""


def _client():
    from openai import OpenAI

    from config import settings
    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL or None)


def _model() -> str:
    from config import settings
    return settings.OPENAI_MODEL


def _q_start(end: date) -> date:
    m = end.month - 2
    return date(end.year if m > 0 else end.year - 1, m if m > 0 else m + 12, 1)


def extract_llm(src: Source, pages: dict[int, str], want: list[tuple[str, str, str]],
                cache_dir: Path, client=None) -> list[Candidate]:
    if not want or not pages:
        return []
    want = sorted(set(want))
    wkey = hashlib.sha256(json.dumps([want, sorted(pages)]).encode()).hexdigest()[:16]
    cache = Path(cache_dir) / f"{src.sha256}_{PROMPT_VERSION}_{wkey}.json"
    if cache.exists():
        items = json.loads(cache.read_text(encoding="utf-8"))["items"]
    else:
        body = "\n\n".join(f"=== PAGE {n} ===\n{t[:_PAGE_CHARS]}" for n, t in sorted(pages.items()))
        ask = "\n".join(f"- {b}, {p}, {m}" for b, p, m in want)
        user = (f"Company: {src.symbol}. Period end: {src.period_end.isoformat()}.\n"
                f"Find:\n{ask}\n\n{body}")
        resp = (client or _client()).chat.completions.create(
            model=_model(), temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}])
        items = json.loads(resp.choices[0].message.content or "{}").get("items", [])
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"items": items}, indent=1), encoding="utf-8")
    return _to_candidates(src, pages, set(want), items)


def _to_candidates(src, pages, want, items) -> list[Candidate]:
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        try:
            key = (it["basis"], it["period_type"], it["metric"])
            printed, page = str(it["printed"]).strip(), int(it["page"])
            mult = unit_multiplier(str(it.get("unit_header") or ""))
        except (KeyError, TypeError, ValueError):
            continue
        if key not in want or key in seen or page not in pages or key[2] not in METRICS:
            continue
        if parse_number(printed) is None or mult is None:   # no stated unit -> nothing stored
            continue
        if units_in(pages[page]) != {mult}:   # the claimed unit is the cited page's only one
            continue
        seen.add(key)
        start = _q_start(src.period_end) if key[1] == "Q" else date(src.period_end.year - 1, 4, 1)
        out.append(Candidate(src.symbol, key[0], key[1], start, src.period_end, key[2],
                             to_value(printed, key[2], mult), METRICS[key[2]][1], printed, page,
                             "llm", "bse_pdf", src.rel, src.url, None))
    return out
