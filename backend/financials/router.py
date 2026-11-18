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


# ---------------------------------------------------------------- metrics
_ALIASES = {
    "revenue_from_operations": ["revenue from operations", "revenue", "revenues", "sales", "topline",
                                "top line", "turnover"],
    "total_income": ["total income"],
    "other_income": ["other income"],
    "total_expenses": ["total expenses", "total expenditure", "expenses"],
    "profit_before_tax": ["profit before tax", "pbt"],
    "tax_expense": ["tax expense", "tax expenses", "tax"],
    "net_profit": ["net profit", "profit after tax", "pat", "net income", "profit", "profits", "earnings"],
    "net_profit_owners": ["profit attributable to owners", "profit attributable to shareholders",
                          "profit attributable to equity holders"],
    "eps_basic": ["basic eps", "eps", "earnings per share", "basic earnings per share"],
    "eps_diluted": ["diluted eps", "diluted earnings per share"],
    "interest_earned": ["interest earned", "interest income"],
    "gross_npa_pct": ["gross npa", "gnpa", "npa"],
    "net_npa_pct": ["net npa", "nnpa"],
    "capital_adequacy_pct": ["capital adequacy", "capital adequacy ratio", "crar"],
    "cet1_pct": ["cet1", "cet 1", "cet-1"],
    "return_on_assets_pct": ["return on assets", "roa"],
    "gross_premium": ["gross premium", "gross written premium", "gwp"],
    "net_premium": ["net premium"],
    "first_year_premium": ["first year premium", "first-year premium", "fyp"],
    "renewal_premium": ["renewal premium"],
    "single_premium": ["single premium"],
    "solvency_ratio": ["solvency ratio", "solvency"],
}
_PHRASES = sorted(((p, m) for m, ps in _ALIASES.items() for p in ps), key=lambda pm: -len(pm[0]))
# Terms we can't answer from the table: mask them and up to two words before them,
# so "net profit margin" or "operating profit" doesn't fire net_profit.
_AMBIGUOUS = re.compile(r"(?:\b[\w']+\s+){0,2}\b(?:margins?|nim|roe|roce|growth|ebitda|ebit|"
                        r"operating\s+profit|gross\s+profit)\b", re.I)


def detect_metrics(question: str) -> list[str]:
    text = _AMBIGUOUS.sub(lambda m: " " * len(m.group()), question.lower())
    hits: list[tuple[int, str]] = []
    for phrase, metric in _PHRASES:
        for m in re.finditer(rf"\b{re.escape(phrase)}\b", text):
            hits.append((m.start(), metric))
            text = _mask(text, m)
    out: list[str] = []
    for _, metric in sorted(hits):
        if metric not in out:
            out.append(metric)
    return out[:3]


# ---------------------------------------------------------------- routing
from financials.query import DEFAULT_DB, Row, available, get_metric  # noqa: E402


@dataclass
class Series:
    company: str
    metric: str          # metric actually fetched
    requested: str       # metric asked for (differs for a bank asked for revenue)
    basis: str
    rows: list[Row]


@dataclass
class Lookup:
    metrics: list[str]
    period: PeriodSpec
    series: list[Series]
    missing: list[str]   # companies with no rows: the LLM answers them from RAG


def _select(rows: list[Row], spec: PeriodSpec) -> list[Row]:
    if spec.ends is not None:
        return [r for r in rows if r.period_end in spec.ends]
    return rows[-spec.last_n:] if spec.last_n else rows


def route(question: str, companies: list[str], years: list[str], db: str = DEFAULT_DB) -> "Lookup | None":
    metrics = detect_metrics(question)
    if not metrics or not companies:
        return None
    spec = parse_periods(question, years)
    q = question.lower()
    bases = (["standalone"] if "standalone" in q else ["consolidated"] if "consolidated" in q
             else ["consolidated", "standalone"])
    series, missing = [], []
    for company in companies:
        have = available(company, db=db)
        found = False
        for requested in metrics:
            metric = ("interest_earned" if requested == "revenue_from_operations" and "interest_earned" in have
                      else requested)
            if metric not in have:
                continue
            picks = [(b, _select(get_metric(company, metric, b, spec.period_type, db=db), spec)) for b in bases]
            basis, rows = max(picks, key=lambda p: len(p[1]))   # tie -> first, i.e. consolidated
            if rows:
                series.append(Series(company, metric, requested, basis, rows))
                found = True
        if not found:
            missing.append(company)
    return Lookup(metrics, spec, series, missing) if series else None
