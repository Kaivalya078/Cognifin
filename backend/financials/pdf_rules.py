"""Rule-based extraction of results statements from BSE PDFs.

A statement page is found by its header, not its title: a short header cell holding the
period-end date whose governing phrase is "quarter / three months ended". Each dated header
cell is a column; the phrase and basis of a column come from the nearest-centre header cell
on the closest row above (so one centred "Quarter ended" over three dates works). A page
with no dated header right after a statement page continues it, keeping its columns, unit
and basis. Numbers are read only from cells near a column centre.
"""
import re
import sys
from datetime import date
from pathlib import Path

import fitz

from core.pdf_chunker import page_rows
from financials.ocr import read_pages
from financials.metrics import METRICS
from financials.numbers import parse_number, to_value, unit_multiplier
from financials.sources import Source
from financials.store import Candidate

LABELS: dict[str, list[str]] = {
    "revenue_from_operations": ["revenue from operations", "total revenue from operations",
                                "income from operations", "total income from operations"],
    "other_income": ["other income"],
    "total_income": ["total income", "total revenue"],
    "total_expenses": ["total expenses", "total expenditure"],
    "profit_before_tax": ["profit before tax", "total profit before tax", "profit before taxation",
                          "profit before income tax", "profit from ordinary activities before tax"],
    "tax_expense": ["tax expense", "tax expenses", "total tax expense", "total tax expenses",
                    "income tax expense", "total income tax expense", "provision for tax",
                    "provision for taxation", "provisions for tax"],
    "net_profit": ["net profit for the period", "profit for the period", "net profit after tax",
                   "profit after tax", "net profit for the quarter", "profit for the quarter",
                   "net profit from ordinary activities after tax"],
    "net_profit_owners": ["owners of the company", "owners of the parent", "owners of parent",
                          "equity holders of the parent", "equity holders of the company",
                          "shareholders of the company", "owners of the holding company",
                          "net profit after minority interest",
                          "net profit after taxes minority interest"],
    "eps_basic": ["basic", "basic eps", "basic earnings per share", "earnings per share basic",
                  "eps basic"],
    "eps_diluted": ["diluted", "diluted eps", "diluted earnings per share",
                    "earnings per share diluted", "eps diluted"],
    "interest_earned": ["interest earned", "total interest earned"],
    "gross_npa_pct": ["% of gross npa", "gross npa (%)", "gross npa ratio", "percentage of gross npa"],
    "net_npa_pct": ["% of net npa", "net npa (%)", "net npa ratio", "percentage of net npa"],
    "capital_adequacy_pct": ["capital adequacy ratio"],
    "cet1_pct": ["cet 1 ratio", "cet1 ratio", "cet 1", "cet1", "common equity tier 1"],
    "return_on_assets_pct": ["return on assets", "return on average assets"],
    "first_year_premium": ["first year premium"],
    "renewal_premium": ["renewal premium"],
    "single_premium": ["single premium"],
    "gross_premium": ["gross premium income", "premium income (gross)", "gross premium",
                      "total gross premium"],
    "net_premium": ["net premium income", "net premium"],
    "solvency_ratio": ["solvency ratio"],
}
BOTH_EPS = ["basic and diluted", "basic & diluted", "basic/diluted", "basic and diluted eps"]
# A label holding one of these words is never the metric (e.g. "profit for the period from
# continuing operations" is not net profit when discontinued operations exist).
EXCLUDE = {"net_profit": ("continuing", "attributable", "before", "comprehensive"),
           "net_profit_owners": ("comprehensive", "non-controlling", "non controlling")}

_SYN = sorted([(s, (m,)) for m, ss in LABELS.items() for s in ss]
              + [(s, ("eps_basic", "eps_diluted")) for s in BOTH_EPS], key=lambda t: -len(t[0]))

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_D_NUM = re.compile(r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4}|\d{2})(?!\d)")
_D_DMY = re.compile(r"(?<!\d)(\d{1,2})\s?(?:st|nd|rd|th)?[\s-]*([a-z]{3,9})[\s,.'’-]*(\d{4}|\d{2})(?!\d)")
_D_MDY = re.compile(r"\b([a-z]{3,9})\s*(\d{1,2})(?:st|nd|rd|th)?[\s,]+(\d{4})(?!\d)")
_SHORT = 45
_DATEISH = re.compile(r"(?i)^(?=.*\d)(?=.*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))|"
                      r"\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]|^\s*(19|20)\d\d\*?\s*$")


def find_date(text: str) -> date | None:
    t = text.lower()
    for rx, order in ((_D_NUM, "dmy"), (_D_DMY, "dMy"), (_D_MDY, "Mdy")):
        for m in rx.finditer(t):
            a, b, y = m.groups()
            try:
                if order == "dmy":
                    d, mo = int(a), int(b)
                elif order == "dMy":
                    d, mo = int(a), _MONTHS.get(b[:3])
                else:
                    d, mo = int(b), _MONTHS.get(a[:3])
                yy = int(y) + (2000 if len(y) == 2 else 0)
                if mo:
                    return date(yy, mo, d)
            except ValueError:
                continue
    return None


def _phrase(text: str) -> str | None:
    t = re.sub(r"\s+", "", text.lower())   # OCR splits words: "Yea r ended", "S ix months"
    if re.search(r"quarter|threemonths|3months", t):
        # one merged cell naming two period lengths ("3 Months Twelve Months") is unreadable
        if re.search(r"half|sixmonths|6months|ninemonths|9months|twelvemonths|12months|"
                     r"yearended|yeartodate", t):
            return "?"
        return "Q"
    if re.search(r"half|sixmonths|6months|ninemonths|9months|period", t):
        return "YTD"
    if re.search(r"year|twelvemonths|12months", t):
        return "FY"
    return None


def _basis_word(text: str) -> str | None:
    t = text.lower()
    s, c = t.find("standalone"), t.find("consolidated")
    if s < 0 and c < 0:
        return None
    if s < 0 or (0 <= c < s):
        return "consolidated"
    return "standalone"


def _xc(c) -> float:
    return (c["x0"] + c["x1"]) / 2


def _clean(text: str) -> str:
    """Trailing footnote marks off; OCR spaces beside a separator closed ("35 .27")."""
    return re.sub(r"(?<=\d)\s*([.,])\s*(?=\d)", r"\1", re.sub(r"[%*#^]+$", "", text.strip()))


def _num(text: str) -> float | None:
    return parse_number(_clean(text))


def _norm_label(s: str) -> str:
    t = s.lower().replace("’", "'")
    t = re.sub(r"\s*/\s*\(\s*(loss|credit)\s*\)|\(\s*(loss|credit)\s*\)\s*/\s*", "", t)
    t = re.sub(r"[,:;\-–—•]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(3):
        t = re.sub(r"^(\(?(\d{1,2}|[ivx]{1,5}|[a-h])[).]?|less|add)\s+", "", t)
    return re.sub(r"^earnings per (equity )?share (?=basic|diluted)", "", t)


def match_metrics(label: str) -> tuple[str, ...]:
    t = _norm_label(label)
    if "discontinued" in t:   # never a headline figure
        return ()
    for syn, ms in _SYN:
        if t.startswith(syn):
            return tuple(m for m in ms if not any(w in t for w in EXCLUDE.get(m, ())))
    return ()


def _q_start(end: date) -> date:
    m = end.month - 2
    return date(end.year if m > 0 else end.year - 1, m if m > 0 else m + 12, 1)


def _overlap(a, b) -> float:
    return min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])


def _stacks(cells):
    """Date fragments in the header stacked top to bottom where they overlap horizontally,
    so a date split over rows ("June 30," above "2025") reads as one column header. Each
    fragment joins the stack it overlaps most; a stack holds at most one full date."""
    stacks = []
    frags = [c for c in cells if len(c["text"]) <= _SHORT and _DATEISH.search(c["text"])]
    for c in sorted(frags, key=lambda c: c["y0"]):
        h = c["y1"] - c["y0"]
        full = find_date(c["text"]) is not None
        near = [s for s in stacks if _overlap(s, c) > 0 and c["y0"] - s["y1"] < 3 * h
                and not (full and s["full"])]
        if near:
            s = max(near, key=lambda s: _overlap(s, c))
            s.update(text=s["text"] + " " + c["text"], y1=max(s["y1"], c["y1"]),
                     full=s["full"] or full)
        else:
            stacks.append(dict(c, full=full))
    return stacks


def _layout(rows, period_end: date, prev):
    """Columns, unit and data-row start for one page, or the inherited layout of `prev`."""
    first = next((i for i, r in enumerate(rows)
                  if any(_num(c["text"]) is not None for c in r[1:]) and match_metrics(
                      " ".join(c["text"] for c in r if _num(c["text"]) is None))), None)
    if first is None:
        return None
    head = rows[:first]
    cells = [c for r in head for c in r]
    if any(re.search(r"(?i)segment|cash\s*flow|operating activities|^notes\b|regulation 52",
                     c["text"]) for c in cells):
        # segment, cash-flow and notes tables repeat headline labels: BAJAJFINSV's PBT from
        # its cash flow; TMPV's Reg 52(4) notes table, no basis named, read as standalone EPS
        return None
    stacks = _stacks(cells)
    dated = [s for s in stacks if find_date(s["text"])]
    # a header that reads only "March 31," still marks a column: it explains the numbers
    # under it, but having no date it is never a target
    undated = [s for s in stacks if not find_date(s["text"])]
    if not dated:
        return dict(prev, start=0) if prev else None
    units = {m for m in (unit_multiplier(c["text"]) for c in cells) if m}
    unit = units.pop() if len(units) == 1 else None   # "in Lakhs" + a stray "Cr": unknown
    short = [r for r in head if all(len(c["text"]) <= _SHORT for c in r)]
    phrases = [c for c in cells if len(c["text"]) <= _SHORT and _phrase(c["text"])]
    bcells = [c for c in cells if len(c["text"]) <= _SHORT and _basis_word(c["text"])]
    page_basis = _basis_word(" ".join(c["text"] for c in cells)) or "standalone"
    multi_basis = len({_basis_word(c["text"]) for c in bcells}) > 1

    def phrase_of(col):
        """Header rows above the column, closest first: text of the cells overlapping it,
        accumulated upwards until a phrase reads ("months ended" + "Preceding three")."""
        ph = _phrase(col["text"])
        acc = ""
        for r in reversed([r for r in short if r[0]["y1"] <= col["y0"] + 1]):
            if ph:
                break
            acc = " ".join(c["text"] for c in r if _overlap(c, col) > 0) + " " + acc
            ph = _phrase(acc)
        if not ph:
            p = nearest_above(phrases, col)
            ph = p and _phrase(p["text"])
        return None if ph == "?" else ph

    def nearest_above(cands, cell):
        above = [c for c in cands if c["y1"] <= cell["y0"] + 1]
        if not above:
            return None
        ymax = max(c["y0"] for c in above)
        row = [c for c in above if abs(c["y0"] - ymax) < 3]
        return min(row, key=lambda c: abs(_xc(c) - _xc(cell)))

    cols = []
    for c in dated:
        b = page_basis
        if multi_basis:
            bc = nearest_above(bcells, c)
            b = _basis_word(bc["text"]) if bc else page_basis
        cols.append({"x": _xc(c), "date": find_date(c["text"]), "phrase": phrase_of(c), "basis": b})
    cols += [{"x": _xc(c), "date": None, "phrase": None, "basis": page_basis} for c in undated]
    xs = sorted(c["x"] for c in cols)
    gap = min([b - a for a, b in zip(xs, xs[1:]) if b - a > 5] or [80])
    return {"cols": cols, "unit": unit, "start": first, "tol": max(25.0, 0.6 * gap)}


def _targets(layout, period_end: date):
    """[(col, period_type)] for the columns that hold this filing's quarter / FY."""
    out = []
    for c in layout["cols"]:
        if c["date"] != period_end:
            continue
        if c["phrase"] == "Q":
            out.append((c, "Q"))
        elif c["phrase"] == "FY" and period_end.month == 3:
            out.append((c, "FY"))
    # two columns claiming the same basis and period means the header was misread: use neither
    claims = [(c["basis"], p) for c, p in out]
    return [(c, p) for c, p in out if claims.count((c["basis"], p)) == 1]


def find_statement_pages(doc, period_end: date) -> list[tuple[int, str]]:
    return [(p, b) for p, b, _ in _statement_layouts(read_pages(doc), period_end)]


def _statement_layouts(pages_rt, period_end: date):
    out, prev = [], None
    for i, (rows, *_) in enumerate(pages_rt):
        lay = _layout(rows, period_end, prev)
        if lay and lay["unit"] and _targets(lay, period_end):
            bases = sorted({c["basis"] for c, _ in _targets(lay, period_end)})
            out.append((i + 1, bases[0], (lay, rows)))
            prev = lay
        else:
            prev = None
    return out


def _section(row, policyholders: bool) -> bool:
    """Insurer statements: a "POLICYHOLDERS' A/C" / "SHAREHOLDERS' A/C" heading row."""
    txt = " ".join(c["text"] for c in row)
    if len(txt) < 40 and re.search(r"(?i)holders\W*(a/c|account)", txt):
        return "policy" in txt.lower()
    return policyholders


_SHAREHOLDERS_ONLY = {"profit_before_tax", "tax_expense", "net_profit"}
_KEY = re.compile(r"revenue from operations|total income|profit before tax|interest earned|premium")


def _eps_block(text: str, cur: str | None) -> str | None:
    """Which EPS block a heading opens: 'cont', 'disc' or 'total' (continuing and
    discontinued). Text that is no EPS heading keeps the current block."""
    t = text.lower()
    if "per share" not in t and "eps" not in t:
        return cur
    c, d = "continuing" in t, "discontinued" in t
    return "total" if c and d else "disc" if d else "cont" if c else cur


_EPS = {"eps_basic", "eps_diluted"}


def _withdraw_eps(unread, eps_block, found, late_keys, blocked) -> None:
    """An all-operations EPS row that can't be read (TMPV's OCR'd "78,80") leaves the
    continuing-only figure standing; that one is not the company's EPS either."""
    if eps_block == "total":
        for k in unread:
            if k[2] in _EPS and k not in late_keys:
                found.pop(k, None)
                blocked.add(k)


_OCR_CACHE = Path(__file__).resolve().parents[1] / "index_cache" / "financials_ocr_cache"


def extract_rules(src: Source, ocr_cache: Path = _OCR_CACHE) -> tuple[list[Candidate], dict[int, str]]:
    found: dict[tuple, Candidate] = {}
    blocked: set[tuple] = set()
    late_keys: set[tuple] = set()
    policyholders = False
    above = ""
    discontinued = False
    pages: dict[int, str] = {}
    with fitz.open(str(src.path)) as doc:
        rt = read_pages(doc, src.sha256, ocr_cache)
    # text-layer pages first: a scanned copy of a statement only fills what they miss
    layouts = sorted(_statement_layouts(rt, src.period_end), key=lambda t: rt[t[0] - 1][2])
    for pno, _, (lay, rows) in layouts:
        pages[pno] = rt[pno - 1][1]
        targets = _targets(lay, src.period_end)
        above = ""   # a numberless row on the previous page labels nothing here
        eps_block = None
        discontinued = False   # per page: the standalone page's block says nothing of the next
        for r in rows[:lay["start"]]:
            policyholders = _section(r, policyholders)
        for r in rows[lay["start"]:]:
            left = min(k["x"] for k in lay["cols"]) - 1.5 * lay["tol"]
            area = [c for c in r if _num(c["text"]) is not None and _xc(c) >= left]
            nums = [c for c in area
                    if min(abs(_xc(c) - k["x"]) for k in lay["cols"]) <= lay["tol"]]
            if not nums:
                policyholders = _section(r, policyholders)
                above = " ".join(c["text"] for c in r)
                # "...continuing and discontinued" / "operations": the wrap keeps the block
                eps_block = _eps_block(above, eps_block)
                continue
            label = " ".join(c["text"] for c in r if c["x1"] <= min(n["x0"] for n in nums) + 1
                             and _num(c["text"]) is None)
            # "and Joint Ventures": a wrapped label ("a) Current tax" is an item, not a wrap)
            if label[:1].islower() and above and not re.match(r"([ivx]{1,5}|[a-z])[).]?\s", label):
                label = above + " " + label
            above = ""
            metrics = match_metrics(label)
            eps_block = _eps_block(label, eps_block)
            if eps_block == "disc":   # discontinued-only EPS never stands in for the company's
                metrics = tuple(m for m in metrics if m not in _EPS)
            discontinued = discontinued or "discontinued" in label.lower()
            if policyholders:   # insurers: the company's PBT/tax/profit are shareholders'
                metrics = tuple(m for m in metrics if m not in _SHAREHOLDERS_ONLY)
            # The first row carrying a label settles it: when that row cannot be read, a
            # later row with the same label (e.g. the OCI "Owners of the Company") must
            # not stand in for it.
            unread = {(col["basis"], p, m) for col, p in targets for m in metrics}
            owners = [id(min(lay["cols"], key=lambda k: abs(_xc(n) - k["x"]))) for n in nums]
            if len(nums) < len(area) or len(set(owners)) < len(owners):
                blocked |= unread   # a stray number, or two under one column: misfit row
                _withdraw_eps(unread, eps_block, found, late_keys, blocked)
                continue
            for col, ptype in targets:
                cell = min(nums, key=lambda c: abs(_xc(c) - col["x"]))
                if owners[nums.index(cell)] != id(col):
                    continue
                for m in metrics:
                    if m == "net_profit_owners" and col["basis"] != "consolidated":
                        continue
                    key = (col["basis"], ptype, m)
                    unread.discard(key)
                    # profit after the share of associates replaces a plain PAT row; owners'
                    # share after a discontinued block replaces their continuing-only share
                    late = (m == "net_profit" and re.search(r"associate|joint venture", label, re.I)
                            or m == "net_profit_owners" and discontinued
                            or m in _EPS and eps_block == "total")
                    if key in blocked or (key in found and not (late and key not in late_keys)):
                        continue
                    if late:
                        late_keys.add(key)
                    start = _q_start(src.period_end) if ptype == "Q" else date(src.period_end.year - 1, 4, 1)
                    found[key] = Candidate(
                        src.symbol, col["basis"], ptype, start, src.period_end, m,
                        to_value(_clean(cell["text"]), m, lay["unit"]),
                        METRICS[m][1], cell["text"].strip(), pno, "rule", "bse_pdf", src.rel,
                        src.url, None)
            blocked |= unread - set(found)
            _withdraw_eps(unread, eps_block, found, late_keys, blocked)
    # pages the rules could not lay out, for the LLM fallback
    for i, (_, text, _) in enumerate(rt):
        if len(pages) >= 6:
            break
        t = re.sub(r"\s+", " ", text.lower())
        if i + 1 not in pages and len(set(_KEY.findall(t))) >= 2 and find_date(t):
            pages[i + 1] = text
    return list(found.values()), dict(sorted(pages.items()))


def check_columns(src: Source, cands: list[Candidate],
                  ocr_cache: Path = _OCR_CACHE) -> tuple[list[Candidate], list[dict]]:
    """LLM values on a page the rules laid out must sit under a column of the claimed period.
    A value not found as a cell, or on a page without a layout, passes (verbatim judges it)."""
    from financials.store import review_row
    ok, bad = [], []
    with fitz.open(str(src.path)) as doc:
        rt = read_pages(doc, src.sha256, ocr_cache)
    lays = {pno: lay for pno, _, (lay, _) in _statement_layouts(rt, src.period_end)}
    rows = {pno: rt[pno - 1][0] for pno in lays}
    for c in cands:
        lay = lays.get(c.page)
        cells = [g for r in rows.get(c.page, []) for g in r
                 if g["text"].strip() == c.printed.strip()] if lay else []
        good = {(k["basis"], p) for k, p in _targets(lay, src.period_end)} if lay else set()
        hits = [min(lay["cols"], key=lambda k: abs(_xc(g) - k["x"])) for g in cells]
        if lay and lay["unit"] and METRICS[c.metric][1] == "INR" and                 abs(c.value - to_value(c.printed, c.metric, lay["unit"])) > 1e-6 * abs(c.value or 1):
            bad.append(review_row(c, f"unit: page {c.page} is in x{lay['unit']:g}, not "
                                     f"x{c.value / parse_number(c.printed):g}"))
        elif hits and not any((k["basis"], c.period_type) in good and k["date"] == src.period_end
                            and k["phrase"] == c.period_type for k in hits):
            bad.append(review_row(c, f"column: '{c.printed}' is not under a "
                                     f"{c.basis} {c.period_type} {src.period_end} column"))
        else:
            ok.append(c)
    return ok, bad


def _probe(root: Path) -> None:
    from financials.sources import load_sources
    tot_files = tot_found = tot_metrics = 0
    for s in load_sources(root):
        if s.kind != "PDF":
            continue
        tot_files += 1
        try:
            cands, _ = extract_rules(s)
            with fitz.open(str(s.path)) as d:
                sp = find_statement_pages(d, s.period_end)
        except Exception as e:  # probe only
            print(f"{s.rel}: ERROR {e}")
            continue
        q = {(c.basis, c.metric) for c in cands if c.period_type == "Q"}
        tot_found += bool(sp)
        tot_metrics += len(q)
        print(f"{s.rel}: pages {sp} metrics {len(q)}")
    print(f"TOTAL files {tot_files} with_statement_pages {tot_found} q_metrics {tot_metrics}")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        _probe(Path(__file__).resolve().parents[1] / "data" / "quarterly")
