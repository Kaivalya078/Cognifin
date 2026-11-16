from datetime import date

import pytest

from financials.query import available, get_metric
from financials.store import Candidate, write_db


def _c(company, end, metric="net_profit", basis="consolidated", ptype="Q", value=1.0):
    start = date(end.year - 1, 4, 1) if ptype == "FY" else date(end.year, end.month - 2, 1)
    return Candidate(company, basis, ptype, start, end, metric, value, "INR", "1.00", 2, "rule",
                     "bse_pdf", f"{company}/x.pdf", "https://bse/x.pdf", None)


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "f.duckdb")
    write_db(p, [
        _c("TCS", date(2025, 12, 31), value=3.0), _c("TCS", date(2025, 6, 30), value=1.0),
        _c("TCS", date(2025, 9, 30), value=2.0), _c("TCS", date(2026, 3, 31), ptype="FY", value=9.0),
        _c("TCS", date(2025, 9, 30), metric="eps_basic"),
        _c("ITC", date(2025, 6, 30), basis="standalone"),
    ], [], [])
    return p


def test_ordered_by_period(db):
    rows = get_metric("TCS", "net_profit", db=db)
    assert [r.value for r in rows] == [1.0, 2.0, 3.0]
    assert rows[0].fiscal_year == 2026 and rows[0].fiscal_quarter == 1
    assert rows[0].source_url == "https://bse/x.pdf" and rows[0].page == 2
    assert [r.value for r in get_metric("TCS", "net_profit", start=date(2025, 9, 1),
                                        end=date(2025, 9, 30), db=db)] == [2.0]


def test_no_standalone_substitution(db):
    assert get_metric("ITC", "net_profit", db=db) == []
    assert [r.basis for r in get_metric("ITC", "net_profit", basis="standalone", db=db)] == ["standalone"]


def test_fy_filter(db):
    rows = get_metric("TCS", "net_profit", period_type="FY", db=db)
    assert [(r.value, r.fiscal_year, r.fiscal_quarter) for r in rows] == [(9.0, 2026, None)]


def test_available(db):
    assert available("TCS", db=db) == {
        "eps_basic": ["2025-09-30"],
        "net_profit": ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"],
    }
