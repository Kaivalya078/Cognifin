"""Build small PDFs with headings, paragraphs and ruled tables for chunker tests."""

import fitz

LEFT, RIGHT, TOP, BOTTOM = 50, 545, 60, 800
BODY, HEAD = 10, 16
ROW_H, COL_W = 16, 150


def _para(page, y, text):
    lines = max(1, len(text) // 85 + 1)
    h = lines * BODY * 1.4 + 6
    page.insert_textbox(fitz.Rect(LEFT, y, RIGHT, y + h + 200), text, fontsize=BODY, fontname="helv")
    return y + h + 8


def _table(page, y, rows):
    ncol = len(rows[0])
    x1 = LEFT + ncol * COL_W
    for r, row in enumerate(rows):
        top = y + r * ROW_H
        for c, cell in enumerate(row):
            page.insert_text((LEFT + c * COL_W + 4, top + ROW_H - 4), str(cell), fontsize=BODY, fontname="helv")
    for r in range(len(rows) + 1):
        page.draw_line((LEFT, y + r * ROW_H), (x1, y + r * ROW_H))
    for c in range(ncol + 1):
        page.draw_line((LEFT + c * COL_W, y), (LEFT + c * COL_W, y + len(rows) * ROW_H))
    return y + len(rows) * ROW_H + 12


def make_pdf(path, pages):
    """pages: list of pages; each page a list of ("heading", text), ("para", text)
    or ("table", rows) items laid out top to bottom. An empty list is a blank page."""
    doc = fitz.open()
    for items in pages:
        page = doc.new_page(width=595, height=842)
        y = TOP
        for kind, value in items:
            if kind == "heading":
                page.insert_text((LEFT, y + HEAD), value, fontsize=HEAD, fontname="hebo")
                y += HEAD + 14
            elif kind == "para":
                y = _para(page, y, value)
            elif kind == "table":
                y = _table(page, y, value)
            else:
                raise ValueError(kind)
    doc.save(str(path))
    doc.close()
    return str(path)
