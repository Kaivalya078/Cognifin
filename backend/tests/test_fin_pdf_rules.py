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


def test_two_columns_claiming_one_period_refused(tmp_path):
    """Header says 'Quarter ended' twice for 30.06.2025 (e.g. OCR lost 'Six months'): refuse."""
    head = _head(dates=("30.06.2025", "31.03.2025", "30.06.2025", "31.03.2025"))
    assert extract_rules(_pdf(tmp_path, [head + BODY]))[0] == []


def test_more_numbers_than_columns_refused(tmp_path):
    """Only two dated columns found but rows hold four numbers: never guess."""
    head = _head(cols=("Quarter ended", "Quarter ended"), dates=("30.06.2025", "31.03.2025"))
    assert extract_rules(_pdf(tmp_path, [head + BODY]))[0] == []


def test_spaced_phrase_letters(tmp_path):
    head = _head(cols=("Q uarter ended", "Q uarter ended", "Q uarter ended", "Yea r ended"),
                 dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    src = _pdf(tmp_path, [head + BODY])
    src.period_end = date(2026, 3, 31)
    cands, _ = extract_rules(src)
    assert _vals(cands)["revenue_from_operations"].value == 1234.5e7
    assert _vals(cands, ptype="FY")["revenue_from_operations"].value == 4400e7


def test_discontinued_row_is_not_net_profit(tmp_path):
    body = BODY[:5] + [[(0, "Profit for the period from discontinued operations"), (1, "(8.00)"),
                        (2, "1.00"), (3, "1.00"), (4, "1.00")]] + BODY[5:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["net_profit"].value == 150e7


def test_segment_page_skipped(tmp_path):
    seg = _head()
    seg[0] = [(0, "Consolidated Segment wise Revenue, Results and Capital Employed")]
    seg_body = [[(c, t.replace("1,234.50", "99.00")) for c, t in r] for r in BODY]
    v = _vals(extract_rules(_pdf(tmp_path, [seg + seg_body, _head() + BODY]))[0])
    assert v["revenue_from_operations"].value == 1234.5e7


def test_merged_mixed_phrase_cell_not_trusted(tmp_path):
    """'3 Months Twelve Months' in one cell over two columns: the year column must not be Q."""
    head = _head(cols=(), dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    head[2] = [(0, "Particulars"), (float(X[3]), "3 Months Twelve Months")]
    head[3] = [(1, "31.12.2025"), (2, "30.09.2025"), (3, "31.12.2024"), (4, "31.03.2026")]
    src = _pdf(tmp_path, [head + BODY])
    src.period_end = date(2026, 3, 31)
    assert [c for c in extract_rules(src)[0] if c.period_type == "Q"] == []


def test_conflicting_unit_words_yield_nothing(tmp_path):
    head = _head(unit="(Rs. in Lakhs)")
    head.insert(1, [(3, "£ Cr /")])
    assert extract_rules(_pdf(tmp_path, [head + BODY]))[0] == []


def test_numbers_in_one_wide_spaced_span(tmp_path):
    """SBILIFE prints a row's numbers as one span padded with spaces."""
    nums = ["1,234.50", "1,100.00", "1,000.00", "4,400.00"]
    text, x = "", float(X[1])
    for i, n in enumerate(nums):
        text += n
        if i + 1 < len(nums):
            while x + fitz.get_text_length(text, "helv", 8) < X[i + 2]:
                text += " "
    body = [[(0, "1 Revenue from operations"), (float(X[1]), text)]] + BODY[1:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["revenue_from_operations"].value == 1234.5e7


def test_refused_row_blocks_later_same_label(tmp_path):
    """BAJFINANCE: the profit-attributable 'Owners' row is unreadable; the later OCI 'Owners'
    row must not stand in for it."""
    body = BODY[:6] + [
        [(0, "Owners of the Company"), (1, "140.00"), (float(X[1]) + 30, "1.71"), (2, "130.00"),
         (3, "100.00"), (4, "500.00")],
        [(0, "Other comprehensive income attributable to")],
        [(0, "Owners of the Company"), (1, "(19.00)"), (2, "1.00"), (3, "1.00"), (4, "1.00")],
    ] + BODY[6:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert "net_profit_owners" not in v


def test_profit_after_associates_wins(tmp_path):
    """RELIANCE: 'Profit After Tax' is before the share of associates; the later row is the
    profit for the period."""
    body = BODY[:5] + [
        [(0, "Profit After Tax"), (1, "150.00"), (2, "135.00"), (3, "110.00"), (4, "525.00")],
        [(0, "Share of Profit/(Loss) of Associates"), (1, "2.00"), (2, "1.00"), (3, "1.00"), (4, "4.00")],
        [(0, "Profit After Tax and Share of Profit/(Loss) of Associates"), (1, "152.00"),
         (2, "136.00"), (3, "111.00"), (4, "529.00")],
    ] + BODY[6:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["net_profit"].value == 152e7


def test_llm_value_from_wrong_column_rejected(tmp_path):
    from financials.pdf_rules import check_columns
    from financials.store import Candidate
    src = _pdf(tmp_path, [_head() + BODY])

    def c(printed):
        return Candidate("TCS", "consolidated", "Q", date(2025, 4, 1), END, "revenue_from_operations",
                         1.0, "INR", printed, 1, "llm", "bse_pdf", "TCS/x.pdf", "u", None)
    ok, bad = check_columns(src, [c("1,234.50"), c("1,100.00")])
    assert [x.printed for x in ok] == ["1,234.50"]
    assert len(bad) == 1 and bad[0]["reason"].startswith("column")


def test_undated_column_explains_its_numbers(tmp_path):
    """TMPV: one header reads 'March 31,' with no year under it. Its numbers must not make
    every row look unexplained."""
    head = _head()
    head[3] = [(1, "30.06.2025"), (2, "31.03.2025"), (3, "June 30,"), (4, "31.03.2025")]
    v = _vals(extract_rules(_pdf(tmp_path, [head + BODY]))[0])
    assert v["revenue_from_operations"].value == 1234.5e7


def test_policyholders_tax_is_not_company_tax(tmp_path):
    """Insurers: the policyholders' account has its own 'Provision for taxes' row."""
    body = [[(0, "POLICYHOLDERS' A/C")],
            [(0, "Provision for taxes"), (1, "36.14"), (2, "1.00"), (3, "1.00"), (4, "1.00")],
            [(0, "SHAREHOLDERS' A/C")]] + BODY
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["tax_expense"].value == 50e7


def test_ocr_space_beside_separator_read():
    from financials.pdf_rules import _num
    assert _num("35 .27") == 35.27 and _num("16 ,637.82") == 16637.82
    assert _num("4,875 .3 6") is None


def test_eps_under_earnings_per_share_prefix():
    from financials.pdf_rules import match_metrics
    assert match_metrics("Earnings per equity share:- Basic and diluted (f)") == ("eps_basic", "eps_diluted")


def test_wrapped_label_joins_line_above(tmp_path):
    """RELIANCE: the numbers sit on the label's second line, 'and Joint Ventures'."""
    body = BODY[:5] + [
        [(0, "Profit After Tax"), (1, "150.00"), (2, "135.00"), (3, "110.00"), (4, "525.00")],
        [(0, "Profit After Tax and Share of Profit/ (Loss) of Associates")],
        [(0, "and Joint Ventures"), (1, "152.00"), (2, "136.00"), (3, "111.00"), (4, "529.00")],
    ] + BODY[6:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["net_profit"].value == 152e7


def test_image_only_page_read_by_ocr(tmp_path):
    """SBIN-style scans: no text layer. OCR cells feed the same rules."""
    src = _pdf(tmp_path, [_head() + BODY], "text.pdf")
    with fitz.open(str(src.path)) as d:
        pix = d[0].get_pixmap(dpi=200)
    scan = fitz.open()
    scan.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
    scan.save(str(tmp_path / "scan.pdf"))
    src.path, src.sha256 = tmp_path / "scan.pdf", "scan"
    v = _vals(extract_rules(src, ocr_cache=tmp_path / "ocr")[0])
    assert v["revenue_from_operations"].value == 1234.5e7 and v["eps_basic"].value == 12.34
    assert list((tmp_path / "ocr").glob("scan_*.json"))   # cached for the next build


def test_item_marker_is_not_a_wrapped_label(tmp_path):
    """JSWSTEEL: 'Tax expense/ (credit)' heading, then 'a) Current tax' is not the total."""
    body = BODY[:4] + [[(0, "Tax expense/ (credit)")],
                       [(0, "a) Current tax"), (1, "41.00"), (2, "1.00"), (3, "1.00"), (4, "1.00")]] + BODY[4:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["tax_expense"].value == 50e7


def test_owners_after_discontinued_block_wins(tmp_path):
    """TMPV: owners' share of continuing profit comes first; the total after the discontinued
    block is the figure."""
    own = lambda v: [(0, "Shareholders of the Company"), (1, v), (2, "1.00"), (3, "1.00"), (4, "1.00")]
    body = BODY[:6] + [own("120.00"),
                       [(0, "Profit before tax from discontinued operation"), (1, "30.00"), (2, "1.00"),
                        (3, "1.00"), (4, "1.00")], own("140.00")] + BODY[6:]
    v = _vals(extract_rules(_pdf(tmp_path, [_head() + body]))[0])
    assert v["net_profit_owners"].value == 140e7


def test_skewed_scan_rows_stay_aligned(tmp_path):
    """SBILIFE p.3: a scan tilted ~1.5 deg. Without deskew, labels pair with the next row."""
    import cv2
    import numpy as np
    src = _pdf(tmp_path, [_head() + BODY], "text.pdf")
    with fitz.open(str(src.path)) as d:
        pix = d[0].get_pixmap(dpi=200)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
    m = cv2.getRotationMatrix2D((pix.w / 2, pix.h / 2), -1.5, 1.0)
    img = cv2.warpAffine(img, m, (pix.w, pix.h), borderValue=(255, 255, 255))
    ok, png = cv2.imencode(".png", img)
    scan = fitz.open()
    scan.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=png.tobytes())
    scan.save(str(tmp_path / "scan.pdf"))
    src.path, src.sha256 = tmp_path / "scan.pdf", "skew"
    v = _vals(extract_rules(src, ocr_cache=tmp_path / "ocr")[0])
    assert v["other_income"].value == 10.5e7 and v["total_income"].value == 1245e7
