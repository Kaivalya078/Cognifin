"""Annual-report coverage for the NIFTY 100 snapshot, plus the R2 size budget.

    cd backend && python -m ingestion.check_reports

One line per symbol: the reports from FY2024 on, named by the year the fiscal year ends
(most companies end in March; ABB India in December, Siemens and Siemens Energy India in
September, so their latest two can be 2024 and 2025). "short" means fewer than two. Then totals. ar_bytes counts every
annual report under data/<SYM>/<YEAR>.pdf, the PDFs that go to R2. Exits 1 if a PDF
won't open or has fewer than MIN_PAGES pages.
"""
import csv
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

DATA = Path(__file__).resolve().parent.parent / "data"
YEARS = ("2024", "2025", "2026")
MIN_PAGES = 20
YEAR_PDF = re.compile(r"^\d{4}\.pdf$")


def check(path: Path) -> str | None:
    """None if the PDF opens with enough pages, else the reason."""
    try:
        with fitz.open(path) as doc:
            return None if doc.page_count >= MIN_PAGES else f"{doc.page_count} pages"
    except Exception as e:  # noqa: BLE001 - any open failure is a bad file
        return f"unreadable ({e.__class__.__name__})"


def main() -> int:
    with open(DATA / "nifty100.csv", encoding="utf-8") as f:
        symbols = [r["symbol"] for r in csv.DictReader(f)]

    bad, short = [], []
    for sym in symbols:
        have = []
        for y in YEARS:
            p = DATA / sym / f"{y}.pdf"
            if not p.exists():
                continue
            if (why := check(p)):
                bad.append(p)
                have.append(f"{y} BAD {why}")
            else:
                have.append(y)
        good = [h for h in have if " " not in h]
        if len(good) < 2:
            short.append(sym)
        print(f"{sym:<12} {' '.join(have) or '-'}{'  short' if len(good) < 2 else ''}")

    reports = [p for p in DATA.glob("*/*.pdf") if YEAR_PDF.match(p.name)]
    ar_bytes = sum(p.stat().st_size for p in reports)
    print(f"reports {len(reports)}, short {len(short)}, bad {len(bad)}, ar_bytes {ar_bytes / 1e9:.2f} GB")
    if short:
        print("short:", " ".join(short))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
