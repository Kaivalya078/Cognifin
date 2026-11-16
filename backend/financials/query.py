"""Read API over financials.duckdb for Phase 4. Opens the database read-only per call.
No basis is ever substituted: ask for consolidated, get consolidated rows or nothing."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "index_cache" / "financials.duckdb")
_COLS = ["company", "basis", "period_type", "period_end", "fiscal_year", "fiscal_quarter",
         "metric", "value", "unit", "source_url", "source_file", "page", "method"]


@dataclass
class Row:
    company: str
    basis: str
    period_type: str
    period_end: date
    fiscal_year: int
    fiscal_quarter: int | None
    metric: str
    value: float
    unit: str
    source_url: str
    source_file: str
    page: int | None
    method: str


def get_metric(company: str, metric: str, basis: str = "consolidated", period_type: str = "Q",
               start: date | None = None, end: date | None = None, db: str = DEFAULT_DB) -> list[Row]:
    sql = (f"SELECT {', '.join(_COLS)} FROM financials WHERE company = ? AND metric = ? "
           "AND basis = ? AND period_type = ?")
    args = [company, metric, basis, period_type]
    if start:
        sql, args = sql + " AND period_end >= ?", args + [start]
    if end:
        sql, args = sql + " AND period_end <= ?", args + [end]
    with duckdb.connect(db, read_only=True) as con:
        return [Row(*r) for r in con.execute(sql + " ORDER BY period_end", args).fetchall()]


def available(company: str, db: str = DEFAULT_DB) -> dict[str, list[str]]:
    """Metric -> sorted ISO period ends present for the company (any basis, Q or FY)."""
    with duckdb.connect(db, read_only=True) as con:
        rows = con.execute("SELECT metric, list(DISTINCT period_end ORDER BY period_end) "
                           "FROM financials WHERE company = ? GROUP BY metric ORDER BY metric",
                           [company]).fetchall()
    return {m: [d.isoformat() for d in ds] for m, ds in rows}
