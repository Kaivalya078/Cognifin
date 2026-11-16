"""Candidate rows and the DuckDB writer."""
import os
from dataclasses import asdict, dataclass
from datetime import date

import duckdb


@dataclass
class Candidate:
    company: str
    basis: str
    period_type: str          # "Q" | "FY"
    period_start: date
    period_end: date
    metric: str
    value: float
    unit: str
    printed: str
    page: int | None
    method: str               # "xbrl" | "rule" | "llm"
    source_kind: str          # "nse_ixbrl" | "bse_pdf"
    source_file: str
    source_url: str
    audited: bool | None

    def key(self):
        return (self.company, self.basis, self.period_type, self.period_end, self.metric)


def fiscal_labels(period_end: date, period_type: str) -> tuple[int, int | None]:
    """Indian FY (Apr–Mar): 2025-06-30 Q -> (2026, 1); FY ending 2026-03 -> (2026, None)."""
    fy = period_end.year + (1 if period_end.month > 3 else 0)
    if period_type == "FY":
        return fy, None
    return fy, ((period_end.month - 4) % 12) // 3 + 1


_SCHEMA = """
CREATE TABLE financials (
  company VARCHAR, basis VARCHAR, period_type VARCHAR, period_start DATE, period_end DATE,
  fiscal_year INTEGER, fiscal_quarter INTEGER, metric VARCHAR, value DOUBLE, unit VARCHAR,
  printed VARCHAR, source_kind VARCHAR, source_file VARCHAR, source_url VARCHAR,
  page INTEGER, method VARCHAR, audited BOOLEAN,
  PRIMARY KEY (company, basis, period_type, period_end, metric));
CREATE TABLE filings (
  file VARCHAR PRIMARY KEY, url VARCHAR, symbol VARCHAR, kind VARCHAR, basis VARCHAR,
  period_end DATE, status VARCHAR, reason VARCHAR, rounding VARCHAR, audited BOOLEAN);
CREATE TABLE review (
  company VARCHAR, basis VARCHAR, period_type VARCHAR, period_end DATE, metric VARCHAR,
  value DOUBLE, printed VARCHAR, method VARCHAR, reason VARCHAR, page INTEGER,
  source_file VARCHAR);
"""
_FIL_COLS = ["file", "url", "symbol", "kind", "basis", "period_end", "status", "reason", "rounding", "audited"]
_REV_COLS = ["company", "basis", "period_type", "period_end", "metric", "value", "printed",
             "method", "reason", "page", "source_file"]


def review_row(c: Candidate, reason: str) -> dict:
    return {**asdict(c), "reason": reason}


def write_db(path: str, rows: list[Candidate], filings: list[dict], review: list[dict]) -> None:
    """Write a fresh db at `path` atomically. Same key twice: xbrl wins, else first wins;
    the loser goes to review with reason 'conflict'."""
    kept: dict[tuple, Candidate] = {}
    review = list(review)
    for c in rows:
        old = kept.get(c.key())
        if old is None:
            kept[c.key()] = c
        elif c.method == "xbrl" and old.method != "xbrl":
            kept[c.key()] = c
            review.append(review_row(old, "conflict"))
        else:
            review.append(review_row(c, "conflict"))

    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = duckdb.connect(tmp)
    try:
        con.execute(_SCHEMA)
        con.executemany(
            "INSERT INTO financials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(c.company, c.basis, c.period_type, c.period_start, c.period_end,
              *fiscal_labels(c.period_end, c.period_type), c.metric, c.value, c.unit,
              c.printed, c.source_kind, c.source_file, c.source_url, c.page, c.method,
              c.audited) for c in kept.values()])
        if filings:
            con.executemany(f"INSERT INTO filings VALUES ({','.join('?' * len(_FIL_COLS))})",
                            [tuple(f.get(k) for k in _FIL_COLS) for f in filings])
        if review:
            con.executemany(f"INSERT INTO review VALUES ({','.join('?' * len(_REV_COLS))})",
                            [tuple(r.get(k) for k in _REV_COLS) for r in review])
    finally:
        con.close()
    os.replace(tmp, path)
