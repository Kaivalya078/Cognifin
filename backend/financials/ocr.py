"""Page rows + text for the PDF rules, with OCR for pages that have no text layer (scans).

OCR (rapidocr, onnxruntime on CPU, ~10 s a page) runs only on image-only pages and is cached
on disk per file hash and page, so a rebuild never OCRs the same page twice.
"""
import json
import logging
import math
from functools import lru_cache
from pathlib import Path

from core.pdf_chunker import _rows, page_rows

DPI = 200
# ponytail: results sit in the first pages of a filing; raise if a scan hides them deeper
MAX_OCR_PAGES = 12


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR
    eng = RapidOCR()
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    return eng


def _ocr_boxes(page) -> list[dict]:
    """Raw OCR: text and its 4 corner points, in PDF points."""
    res = _engine()(page.get_pixmap(dpi=DPI).tobytes("png"))
    k = 72 / DPI
    return [{"text": t.strip(), "box": [[float(x) * k, float(y) * k] for x, y in box]}
            for box, t in zip(res.boxes if res.boxes is not None else [], res.txts or [])
            if t.strip()]


def _cells(boxes: list[dict]) -> list[dict]:
    """Deskewed cells. A scan tilted ~1.5 deg drifts a row's right end into the next row,
    so every point is rotated back by the median slope of the boxes' top edges."""
    slopes = sorted((b["box"][1][1] - b["box"][0][1]) / (b["box"][1][0] - b["box"][0][0])
                    for b in boxes if b["box"][1][0] - b["box"][0][0] > 20)
    a = -math.atan(slopes[len(slopes) // 2]) if slopes else 0.0
    cos, sin = math.cos(a), math.sin(a)
    cells = []
    for b in boxes:
        xs = [x * cos - y * sin for x, y in b["box"]]
        ys = [x * sin + y * cos for x, y in b["box"]]
        cells.append({"text": b["text"], "x0": min(xs), "x1": max(xs),
                      "y0": min(ys), "y1": max(ys), "key": None})
    return cells


def _as_text(rows) -> str:
    return "\n".join(" ".join(c["text"] for c in r) for r in rows)


def read_pages(doc, sha: str | None = None, cache_dir: Path | None = None) -> list[tuple[list, str, bool]]:
    """[(rows, text, ocr)] per page. OCR only with a cache_dir and a file hash."""
    out, ocred = [], 0
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip() or not (sha and cache_dir) or not page.get_images() or ocred >= MAX_OCR_PAGES:
            out.append((page_rows(page), text, False))
            continue
        ocred += 1
        f = Path(cache_dir) / f"{sha}_{i + 1}.boxes.json"
        if f.exists():
            boxes = json.loads(f.read_text(encoding="utf-8"))
        else:
            boxes = _ocr_boxes(page)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(boxes), encoding="utf-8")
        rows = _rows(_cells(boxes))
        out.append((rows, _as_text(rows), True))
    return out
