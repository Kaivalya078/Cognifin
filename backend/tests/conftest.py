import os

# auth.py refuses to import without a real secret; give the test process one.
os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "x" * 40)
# Never let tests reach a real database; MongoClient connects lazily anyway.
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")


import pytest  # noqa: E402


def fin_candidate(company, end, metric="net_profit", basis="consolidated", ptype="Q", value=1.0,
                  unit="INR", url="https://bse/x.pdf", page=2):
    from datetime import date
    from financials.store import Candidate
    start = date(end.year - 1, 4, 1) if ptype == "FY" else date(end.year, end.month - 2, 1)
    return Candidate(company, basis, ptype, start, end, metric, value, unit, "1.00", page, "rule",
                     "bse_pdf", f"{company}/x.pdf", url, None)


@pytest.fixture
def fin_db(tmp_path):
    """Small financials table shared by the router/present tests."""
    from datetime import date
    from financials.store import write_db
    c, d = fin_candidate, date
    p = str(tmp_path / "f.duckdb")
    write_db(p, [
        c("TCS", d(2025, 6, 30), value=1.0), c("TCS", d(2025, 9, 30), value=2.0),
        c("TCS", d(2025, 12, 31), value=3.0), c("TCS", d(2026, 3, 31), ptype="FY", value=9.0),
        c("ITC", d(2025, 6, 30), basis="standalone"),
        c("HDFCBANK", d(2025, 6, 30), metric="interest_earned", value=5e10),
        c("HDFCBANK", d(2025, 9, 30), metric="interest_earned", value=6e10),
        c("RELIANCE", d(2025, 6, 30), metric="revenue_from_operations", value=7e10),
        *[c("RELIANCE", e, metric="revenue_from_operations", basis="standalone", value=4e10)
          for e in (d(2025, 6, 30), d(2025, 9, 30), d(2025, 12, 31))],
    ], [], [])
    return p
