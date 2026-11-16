"""
Structure-aware PDF chunker (Phase 2).

Per page: tables are rebuilt from text geometry — text segments are grouped
into visual rows by y-position, and runs of rows with several cells and
numbers become a Markdown table (header row repeated in every chunk of a
table, split only between rows). Prose is the remaining text, split on
paragraph then sentence boundaries with one sentence of overlap. Headings
are detected from font size/weight, carried across pages, and prefixed to
every chunk ("<heading>\n<body>"). A chunk never spans pages.

Why not page.find_tables(): on annual-report statements it boxes only the
ruled numeric columns (row labels end up in prose, so the table chunk is a
column of bare numbers), misses unruled tables, and costs ~0.5 s/page
(~7 h for the corpus) against ~0.005 s/page here.
"""

import re
import statistics
from typing import Dict, List, Tuple

import fitz

from config import settings
from core.retriever_pipeline import Chunk, normalize_text

HEADING_SIZE_RATIO = 1.25   # span size vs the page's median body size
HEADING_MAX_CHARS = 120
CELL_GAP = 1.5              # x-gap (in font sizes) that splits a line into cells
_SENT = re.compile(r"(?<=[.!?])\s+")
_MD_SEP = re.compile(r"^\|[\s:|-]+\|$")
_LEADER = re.compile(r"\s*(?:\.\s?){4,}\s*")   # dot leaders "Total ........ 12"
MARGIN = 0.06               # top/bottom page fraction holding running headers/footers
_NUM = re.compile(r"^[(\-–]?\s*[₹`$]?\s*\d[\d,]*(\.\d+)?\s*\)?\s*%?$")


# -----------------------------------------------------------------------------
# Page → ordered elements
# -----------------------------------------------------------------------------

def _is_headingish(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return 3 <= letters and letters / max(len(text), 1) > 0.5 and len(text) <= HEADING_MAX_CHARS


def _segments(blocks) -> List[Dict]:
    """Text segments: runs of spans on one line, split where the x-gap is wide."""
    segs = []
    for bi, b in enumerate(blocks):
        for li, line in enumerate(b["lines"]):
            cur = []
            for sp in line["spans"]:
                if not sp["text"].strip():
                    continue
                if cur and sp["bbox"][0] - cur[-1]["bbox"][2] > CELL_GAP * sp["size"]:
                    segs.append(_seg(cur, (bi, li)))
                    cur = []
                cur.append(sp)
            if cur:
                segs.append(_seg(cur, (bi, li)))
    return segs


def _seg(spans, key) -> Dict:
    text = " ".join(" ".join(s["text"].split()) for s in spans)
    return {"text": _LEADER.sub(" ", text).strip(),
            "x0": min(s["bbox"][0] for s in spans),
            "y0": min(s["bbox"][1] for s in spans), "y1": max(s["bbox"][3] for s in spans),
            "key": key}


def _rows(segs) -> List[List[Dict]]:
    """Group segments into visual rows (overlapping vertical centres), left to right."""
    rows: List[List[Dict]] = []
    for sg in sorted(segs, key=lambda g: (g["y0"] + g["y1"]) / 2):
        yc, h = (sg["y0"] + sg["y1"]) / 2, sg["y1"] - sg["y0"]
        if rows:
            last = rows[-1]
            lc = sum((g["y0"] + g["y1"]) / 2 for g in last) / len(last)
            if abs(yc - lc) <= 0.4 * max(h, 1):
                last.append(sg)
                continue
        rows.append([sg])
    return [sorted(r, key=lambda g: g["x0"]) for r in rows]


def _is_data(row) -> bool:
    nums = sum(bool(_NUM.match(g["text"])) for g in row)
    return len(row) >= 2 and nums >= 1 and (nums >= 2 or len(row) >= 3)


def _is_header(row) -> bool:
    return len(row) >= 2 and not any(_NUM.match(g["text"]) for g in row) \
        and all(len(g["text"]) <= 60 for g in row)


def _is_label(row) -> bool:
    return len(row) == 1 and len(row[0]["text"]) <= 60


def _tables(rows) -> List[Tuple[float, str, set]]:
    """[(y0, markdown, line keys used)] for each run of table rows."""
    out, i, n = [], 0, len(rows)
    while i < n:
        if not _is_data(rows[i]):
            i += 1
            continue
        start, j, data = i, i, 1
        while j + 1 < n and (_is_data(rows[j + 1]) or (
                _is_label(rows[j + 1]) and j + 2 < n and _is_data(rows[j + 2]))):
            j += 1
            data += _is_data(rows[j])
        head = start
        while head > 0 and start - head < 2 and _is_header(rows[head - 1]):
            head -= 1
        if data >= 2 or (data >= 1 and head < start):
            region = rows[head:j + 1]
            width = max(len(r) for r in region)
            lines = ["|" + "|".join(g["text"] for g in r) + "|" for r in region]
            lines.insert(max(start - head, 1), "|" + "|".join(["---"] * width) + "|")
            keys = {g["key"] for r in region for g in r}
            out.append((region[0][0]["y0"], "\n".join(lines), keys))
        i = j + 1
    return out


def _page_elements(page) -> List[Tuple[float, str, str]]:
    """[(y0, kind, text)] in reading order; kind is heading | prose | table."""
    blocks = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 0]
    h = page.rect.height
    body_segs = [g for g in _segments(blocks)
                 if g["y1"] > MARGIN * h and g["y0"] < (1 - MARGIN) * h and g["text"]]
    tables = _tables(_rows(body_segs))
    used = set().union(*(k for _, _, k in tables)) if tables else set()
    out = [(y, "table", md) for y, md, _ in tables]

    kept = []
    for bi, b in enumerate(blocks):
        lines = [ln for li, ln in enumerate(b["lines"]) if (bi, li) not in used]
        spans = [s for ln in lines for s in ln["spans"] if s["text"].strip()]
        if spans:
            kept.append((b, lines, spans))

    sizes = [s["size"] for _, _, spans in kept for s in spans for _ in range(len(s["text"]))]
    body = statistics.median(sizes) if sizes else 0

    for b, lines, spans in kept:
        text = normalize_text(_LEADER.sub(" ", " ".join(
            " ".join(s["text"] for s in ln["spans"]) for ln in lines)))
        if not text:
            continue
        big = max(s["size"] for s in spans) >= HEADING_SIZE_RATIO * body
        bold = len(lines) == 1 and all(s["flags"] & 16 for s in spans)
        kind = "heading" if (big or bold) and _is_headingish(text) else "prose"
        out.append((lines[0]["bbox"][1], kind, text))

    return sorted(out, key=lambda e: e[0])


# -----------------------------------------------------------------------------
# Splitting
# -----------------------------------------------------------------------------

def _sentences(paragraph: str, limit: int) -> List[str]:
    """Sentences of a paragraph; any longer than limit are cut between words."""
    out = []
    for sent in _SENT.split(paragraph):
        while len(sent) > limit:
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            out.append(sent[:cut])
            sent = sent[cut:].lstrip()
        if sent:
            out.append(sent)
    return out


def _table_chunks(markdown: str, budget: int) -> List[str]:
    lines = [l for l in markdown.splitlines() if l.strip()]
    if not lines:
        return []
    n_head = 2 if len(lines) > 1 and _MD_SEP.match(lines[1]) else 1
    head, rows = lines[:n_head], lines[n_head:]
    if not rows:
        return ["\n".join(head)]
    chunks, cur = [], list(head)
    for row in rows:
        # ponytail: a single row longer than the hard max is emitted as-is
        if len(cur) > n_head and len("\n".join(cur + [row])) > budget:
            chunks.append("\n".join(cur))
            cur = list(head)
        cur.append(row)
    chunks.append("\n".join(cur))
    return chunks


class _Packer:
    """Accumulates one page's prose into chunks of ~target chars."""

    def __init__(self, target: int, hard_max: int):
        self.target, self.hard_max = target, hard_max
        self.parts: List[Tuple[int, str]] = []   # (paragraph index, sentence)
        self.overlap_only = False
        self.para = 0

    def text(self, parts=None) -> str:
        parts = self.parts if parts is None else parts
        out = ""
        for i, (p, s) in enumerate(parts):
            out += ("" if i == 0 else (" " if parts[i - 1][0] == p else "\n")) + s
        return out

    def add_paragraph(self, paragraph: str, budget: int, emit) -> None:
        """budget = hard max for this chunk's body (hard_max minus heading)."""
        self.para += 1
        soft = min(self.target, budget)
        for sent in _sentences(paragraph, soft):
            nxt = self.parts + [(self.para, sent)]
            if self.parts and len(self.text(nxt)) > soft:
                if self.overlap_only:
                    if len(self.text(nxt)) > budget:  # overlap would break hard max
                        self.parts = []
                else:
                    emit(self.text())
                    self.parts = [self.parts[-1]]
                    self.overlap_only = True
                    if len(self.text(self.parts + [(self.para, sent)])) > budget:
                        self.parts = []
            self.parts.append((self.para, sent))
            self.overlap_only = False

    def flush(self, emit) -> None:
        if self.parts and not self.overlap_only:
            emit(self.text())
        self.parts, self.overlap_only = [], False



# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def chunk_pdf(pdf_path: str, target: int = None, hard_max: int = 1500) -> List[Chunk]:
    target = target or settings.CHUNK_SIZE
    out: List[Chunk] = []
    heading = ""

    with fitz.open(pdf_path) as doc:
        for page_no, page in enumerate(doc, 1):
            heading_unused = False

            def emit(body: str, form: str = "narrative"):
                nonlocal heading_unused
                text = f"{heading}\n{body}" if heading and body else (body or heading)
                out.append(Chunk(chunk_id="", text=text, start_char=0, end_char=len(text),
                                 page_number=page_no, heading=heading, content_form=form))
                heading_unused = False

            packer = _Packer(target, hard_max)
            for _, kind, text in _page_elements(page):
                prefix = len(heading) + 1 if heading else 0
                if kind == "heading":
                    packer.flush(emit)
                    if heading_unused and text in heading.split(" · "):
                        continue  # same title repeated (e.g. a name on a profile page)
                    if heading_unused and len(f"{heading} · {text}") <= HEADING_MAX_CHARS:
                        heading = f"{heading} · {text}"   # e.g. stacked title lines
                        continue
                    if heading_unused:  # keep a heading nothing followed
                        packer.add_paragraph(heading, hard_max, emit)
                    heading, heading_unused = text, True
                elif kind == "table":
                    packer.flush(emit)
                    for body in _table_chunks(text, min(target, hard_max - prefix)):
                        emit(body, "tabular")
                else:
                    packer.add_paragraph(text, hard_max - prefix, emit)
            packer.flush(emit)
            if heading_unused:  # a page ending in a heading keeps it on this page
                emit("")

    for i, c in enumerate(out):
        c.chunk_id = f"chunk_{i}"
    return out
