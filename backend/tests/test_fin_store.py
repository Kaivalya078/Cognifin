from datetime import date

import duckdb

from financials.metrics import METRICS, metrics_for
from financials.store import Candidate, fiscal_labels, write_db


def _cand(**kw):
    base = dict(company="TCS", basis="consolidated", period_type="Q",
                period_start=date(2025, 4, 1), period_end=date(2025, 6, 30),
                metric="net_profit", value=1.0e10, unit="INR", printed="1,000.00",
                page=3, method="rule", source_kind="bse_pdf",
                source_file="TCS/2025-06.pdf", source_url="https://x/y.pdf", audited=None)
    base.update(kw)
    return Candidate(**base)


def test_metrics_for_kinds():
    assert "gross_npa_pct" in metrics_for("BANKING") and "revenue_from_operations" not in metrics_for("BANKING")
    assert "solvency_ratio" in metrics_for("LI") and "gross_npa_pct" not in metrics_for("NBFC_INDAS")
    assert METRICS["eps_basic"][1] == "INR_per_share" and METRICS["gross_npa_pct"][1] == "pct"


def test_fiscal_labels():
    assert fiscal_labels(date(2025, 6, 30), "Q") == (2026, 1)
    assert fiscal_labels(date(2026, 3, 31), "Q") == (2026, 4)
    assert fiscal_labels(date(2026, 3, 31), "FY") == (2026, None)


def test_write_and_read_back(tmp_path):
    db = tmp_path / "f.duckdb"
    write_db(str(db), [_cand(), _cand(metric="eps_basic", value=12.3, unit="INR_per_share")], [], [])
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM financials").fetchone()[0] == 2
    assert con.execute("SELECT DISTINCT fiscal_year, fiscal_quarter FROM financials").fetchall() == [(2026, 1)]


def test_conflict_xbrl_wins(tmp_path):
    db = tmp_path / "f.duckdb"
    pdf = _cand(value=2.0)
    xb = _cand(value=1.0, method="xbrl", source_kind="nse_ixbrl", page=None)
    write_db(str(db), [pdf, xb], [], [])
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT method, value FROM financials").fetchall() == [("xbrl", 1.0)]
    assert con.execute("SELECT reason, value FROM review").fetchall() == [("conflict", 2.0)]


def test_atomic_replace(tmp_path):
    db = tmp_path / "f.duckdb"
    write_db(str(db), [_cand()], [], [])
    write_db(str(db), [_cand(), _cand(metric="tax_expense")], [], [])
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM financials").fetchone()[0] == 2
    con.close()
    assert not list(tmp_path.glob("*.tmp*"))
