from datetime import date

import fitz

from financials.pdf_rules import extract_rules, find_statement_pages
from financials.sources import Source

# Column x positions: label at 50, numbers right-ish under each header.
X = [50, 260, 340, 420, 500]


def _page(doc, lines):
    """lines: list of rows; each row a list of (col, text); col indexes X (or an x float)."""
    pg = doc.new_page(width=595, height=842)
    y = 60
    for row in lines:
        for col, text in row:
            x = X[col] if isinstance(col, int) else col
            pg.insert_text((x, y), text, fontsize=8, fontname="helv")
        y += 14


def _pdf(tmp_path, pages, name="r.pdf"):
    doc = fitz.open()
    for lines in pages:
        _page(doc, lines)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return Source("TCS", END, "PDF", None, p, "https://bse/x.pdf", "0")


END = date(2025, 6, 30)


def _head(basis="Consolidated", unit="(Rs. in crore, except per share data)",
          cols=("Quarter ended", "Quarter ended", "Quarter ended", "Year ended"),
          dates=("30.06.2025", "31.03.2025", "30.06.2024", "31.03.2025")):
    rows = [[(0, f"Statement of Unaudited {basis} Financial Results for the quarter ended 30th June 2025")]]
    if unit:
        rows.append([(4, unit)])
    rows.append([(0, "Particulars")] + [(i + 1, c) for i, c in enumerate(cols)])
    rows.append([(i + 1, d) for i, d in enumerate(dates)])
    rows.append([(i + 1, "Unaudited") for i in range(len(dates))])
    return rows


BODY = [
    [(0, "1 Revenue from operations"), (1, "1,234.50"), (2, "1,100.00"), (3, "1,000.00"), (4, "4,400.00")],
    [(0, "2 Other income"), (1, "10.50"), (2, "9.00"), (3, "8.00"), (4, "36.00")],
    [(0, "3 Total income"), (1, "1,245.00"), (2, "1,109.00"), (3, "1,008.00"), (4, "4,436.00")],
    [(0, "Profit / (Loss) before tax"), (1, "200.00"), (2, "180.00"), (3, "150.00"), (4, "700.00")],
    [(0, "Total tax expense"), (1, "50.00"), (2, "45.00"), (3, "40.00"), (4, "175.00")],
    [(0, "Net Profit / (Loss) for the period"), (1, "150.00"), (2, "135.00"), (3, "110.00"), (4, "525.00")],
    [(0, "(a) Basic (Rs.)"), (1, "12.34"), (2, "11.00"), (3, "9.00"), (4, "43.00")],
    [(0, "(b) Diluted (Rs.)"), (1, "12.30"), (2, "10.90"), (3, "8.90"), (4, "42.80")],
]


def _vals(cands, basis="consolidated", ptype="Q"):
    return {c.metric: c for c in cands if c.basis == basis and c.period_type == ptype}


def test_basic_crore_statement(tmp_path):
    src = _pdf(tmp_path, [_head() + BODY])
    cands, pages = extract_rules(src)
    v = _vals(cands)
    assert v["revenue_from_operations"].value == 1234.5e7
    assert v["revenue_from_operations"].printed == "1,234.50"
    assert v["revenue_from_operations"].page == 1 and v["net_profit"].value == 150e7
    assert {c.method for c in cands} == {"rule"} and {c.source_kind for c in cands} == {"bse_pdf"}
    assert 1 in pages and "1,234.50" in pages[1]
    assert not [c for c in cands if c.period_type == "FY"]  # June quarter: no FY row


def test_lakh_unit(tmp_path):
    src = _pdf(tmp_path, [_head(unit="(Rs. in Lakhs)") + BODY])
    assert _vals(extract_rules(src)[0])["revenue_from_operations"].value == 1234.5e5


def test_no_unit_header_yields_nothing(tmp_path):
    src = _pdf(tmp_path, [_head(unit=None) + BODY])
    assert extract_rules(src)[0] == []


def test_two_bases_in_one_pdf(tmp_path):
    cons = [[(c, t.replace("1,234.50", "2,000.00")) for c, t in r] for r in BODY]
    src = _pdf(tmp_path, [_head("Standalone") + BODY, _head("Consolidated") + cons])
    cands, _ = extract_rules(src)
    assert _vals(cands, "standalone")["revenue_from_operations"].value == 1234.5e7
    assert _vals(cands, "consolidated")["revenue_from_operations"].value == 2000e7
    assert [p for p, b in find_statement_pages(fitz.open(str(src.path)), END)] == [1, 2]


def test_column_by_header_not_position(tmp_path):
    head = _head(dates=("31.03.2025", "30.06.2025", "30.06.2024", "31.03.2025"))
    src = _pdf(tmp_path, [head + BODY])
    assert _vals(extract_rules(src)[0])["revenue_from_operations"].value == 1100e7


def test_q4_quarter_vs_year_columns(tmp_path):
    head = _head(dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    src = _pdf(tmp_path, [head + BODY])
    src.period_end = date(2026, 3, 31)
    cands, _ = extract_rules(src)
    q, fy = _vals(cands), _vals(cands, ptype="FY")
    assert q["revenue_from_operations"].value == 1234.5e7
    assert fy["revenue_from_operations"].value == 4400e7
    assert fy["revenue_from_operations"].period_start == date(2025, 4, 1)
    assert q["net_profit"].period_start == date(2026, 1, 1)


def test_merged_phrase_header(tmp_path):
    """One centred 'Quarter ended' over three date columns, one 'Year ended' over the last."""
    head = _head(cols=(), dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    head[2] = [(0, "Particulars"), (float(X[2]), "Quarter ended"), (float(X[4]) + 10, "Year ended")]
    src = _pdf(tmp_path, [head + BODY])
    src.period_end = date(2026, 3, 31)
    cands, _ = extract_rules(src)
    assert _vals(cands)["revenue_from_operations"].value == 1234.5e7
    assert _vals(cands, ptype="FY")["revenue_from_operations"].value == 4400e7


def test_continued_page_keeps_column_and_unit(tmp_path):
    page1 = _head() + BODY[:6]
    page2 = [[(0, "Earnings per share")]] + BODY[6:]
    src = _pdf(tmp_path, [page1, page2])
    v = _vals(extract_rules(src)[0])
    assert v["eps_basic"].value == 12.34 and v["eps_basic"].page == 2
    assert v["eps_diluted"].value == 12.30


def test_eps_unscaled_in_pdf(tmp_path):
    src = _pdf(tmp_path, [_head() + BODY])
    v = _vals(extract_rules(src)[0])
    assert v["eps_basic"].value == 12.34 and v["eps_basic"].unit == "INR_per_share"


def test_parenthesised_loss(tmp_path):
    body = BODY[:5] + [[(0, "Net Profit / (Loss) for the period"), (1, "(625.30)"), (2, "135.00"),
                        (3, "110.00"), (4, "525.00")]]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["net_profit"].value == -625.30e7 and v["net_profit"].printed == "(625.30)"
