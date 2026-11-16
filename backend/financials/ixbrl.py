"""NSE integrated-filing iXBRL web pages -> Candidates.

Rows are [serial?, label, quarter value, year-to-date value]. The first row (in document
order) whose label starts with a mapped prefix (or equals it, for a prefix ending in "$")
and has a number wins; later tables
(segments, policyholder/shareholder repeats) never override it.
"""
import re
from datetime import date
from html.parser import HTMLParser

from financials.metrics import metrics_for
from financials.numbers import parse_date, parse_number, unit_multiplier
from financials.sources import Source
from financials.store import Candidate

_COMMON = [
    ("revenue from operations", "revenue_from_operations"),
    ("total revenue from operations", "revenue_from_operations"),
    ("other income", "other_income"),
    ("total other income", "other_income"),
    ("total income", "total_income"),
    ("total expenses", "total_expenses"),
    ("total profit before tax", "profit_before_tax"),
    ("total tax expenses", "tax_expense"),
    ("total profit (loss) for period", "net_profit"),
    ("profit or loss, attributable to owners of parent", "net_profit_owners"),
    ("basic earnings (loss) per share from continuing and discontinued operations", "eps_basic"),
    ("diluted earnings (loss) per share from continuing and discontinued operations", "eps_diluted"),
    ("basic earnings per share$", "eps_basic"),      # NBFC format; "$" = exact label
    ("diluted earnings per share$", "eps_diluted"),
]

LABELS: dict[str, list[tuple[str, str]]] = {
    "INDAS": _COMMON,
    "NBFC_INDAS": _COMMON,
    "BANKING": [
        ("total interest earned", "interest_earned"),
        ("other income", "other_income"),
        ("total income", "total_income"),
        ("total expenditure excluding provisions and contingencies", "total_expenses"),
        ("total profit (loss) from ordinary activities before tax", "profit_before_tax"),
        ("provision for tax", "tax_expense"),
        ("net profit (loss) for the period", "net_profit"),
        ("net profit (loss) after taxes minority interest and share of profit (loss) of associates",
         "net_profit_owners"),
        ("basic earnings per share after extraordinary items", "eps_basic"),
        ("diluted earnings per share after extraordinary items", "eps_diluted"),
        ("% of gross npas", "gross_npa_pct"),
        ("% of net npas", "net_npa_pct"),
        ("capital adequacy ratio", "capital_adequacy_pct"),
        ("cet 1 ratio", "cet1_pct"),
        ("return on assets", "return_on_assets_pct"),
    ],
    # Policyholders' and shareholders' accounts both have "Total Income"/"Other income";
    # those are ambiguous for an insurer and deliberately unmapped.
    "LI": [
        ("first year premium", "first_year_premium"),
        ("renewal premium", "renewal_premium"),
        ("single premium", "single_premium"),
        ("gross premium income", "gross_premium"),
        ("net premium income", "net_premium"),
        ("profit/ (loss) before tax", "profit_before_tax"),
        ("provisions for tax", "tax_expense"),
        ("profit/ (loss) after tax and extraordinary items", "net_profit"),
        ("basic and diluted eps after extraordinary items", "eps_basic"),
        ("basic and diluted eps after extraordinary items", "eps_diluted"),
        ("solvency ratio", "solvency_ratio"),
    ],
}


class _Rows(HTMLParser):
    """Table rows as lists of cell text. Tolerates cells outside <tr> (NSE pages do that)."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row = self._cell = None

    def _end_cell(self):
        if self._row is None:
            self._row = []
        self._row.append(" ".join("".join(self._cell).split()))
        self._cell = None

    def _flush(self):
        if self._cell is not None:
            self._end_cell()
        if self._row:
            self.rows.append(self._row)
        self._row = None

    def handle_starttag(self, tag, attrs):
        if tag in ("table", "tr"):
            self._flush()
            self._row = [] if tag == "tr" else None
        elif tag in ("td", "th"):
            if self._cell is not None:
                self._end_cell()
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._end_cell()
        elif tag in ("tr", "table"):
            self._flush()

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _q_start(end: date) -> date:
    m = end.month - 2
    return date(end.year if m > 0 else end.year - 1, m if m > 0 else m + 12, 1)


def _header(rows, prefix: str) -> str | None:
    for r in rows:
        if len(r) == 2 and _norm(r[0]).startswith(prefix):
            return r[1]
    return None


def _audited(s: str | None) -> bool | None:
    s = _norm(s or "")
    return True if s == "audited" else False if s == "unaudited" else None


def parse_ixbrl(src: Source) -> tuple[list[Candidate], dict]:
    p = _Rows()
    p.feed(src.path.read_text(encoding="utf-8", errors="replace"))
    p._flush()
    rows = p.rows
    rounding = _header(rows, "level of rounding")
    mult = unit_multiplier(rounding or "") or unit_multiplier(_header(rows, "description of presentation currency") or "")
    filing = {"file": src.rel, "url": src.url, "symbol": src.symbol, "kind": src.kind,
              "basis": src.basis, "period_end": src.period_end, "rounding": rounding,
              "audited": _audited(_header(rows, "whether results are audited or unaudited")),
              "status": "failed", "reason": None}
    if mult is None:
        filing["reason"] = "no unit header"
        return [], filing

    ends = [r for r in rows if len(r) >= 3 and _norm(r[-3]) == "date of end of reporting period"]
    if not ends or parse_date(ends[0][-2]) != src.period_end:
        filing["reason"] = f"reporting period end != {src.period_end}"
        return [], filing
    q4 = src.period_end.month == 3
    fy_ok = q4 and ends[0][-1] and parse_date(ends[0][-1]) == src.period_end
    ytd_audited = _audited(_header(rows, "whether results are audited or unaudited for the year to date"))

    wanted = set(metrics_for(src.kind))
    labels = [(k, m) for k, m in LABELS[src.kind] if m in wanted]
    found: dict[tuple[str, str], Candidate] = {}
    for r in rows:
        if len(r) < 3:
            continue
        label = _norm(r[-3])
        for prefix, metric in labels:
            if not (label == prefix[:-1] if prefix.endswith("$") else label.startswith(prefix)):
                continue
            cols = [("Q", r[-2], _q_start(src.period_end), filing["audited"])]
            if fy_ok:
                cols.append(("FY", r[-1], date(src.period_end.year - 1, 4, 1), ytd_audited))
            for ptype, cell, start, aud in cols:
                v = parse_number(cell)
                if v is None or (ptype, metric) in found:
                    continue
                if metric == "net_profit_owners" and src.basis != "consolidated":
                    continue
                found[ptype, metric] = Candidate(
                    src.symbol, src.basis, ptype, start, src.period_end, metric,
                    v * mult if _unit(metric) == "INR" else v, _unit(metric), cell, None,
                    "xbrl", "nse_ixbrl", src.rel, src.url, aud)
    cands = list(found.values())
    n = len({m for (t, m) in found if t == "Q"})
    filing["status"] = "parsed" if n >= 6 else "partial" if n else "failed"
    if filing["status"] != "parsed":
        filing["reason"] = f"{n} metrics"
    return cands, filing


def _unit(metric: str) -> str:
    from financials.metrics import METRICS
    return METRICS[metric][1]
