from datetime import date
from pathlib import Path

import pytest

from financials.ixbrl import parse_ixbrl
from financials.metrics import METRICS
from financials.sources import Source, load_sources

FIX = Path(__file__).parent / "fixtures" / "financials"
SOURCES = Path(__file__).parents[1] / "data" / "quarterly"


def _src(name, sym, kind, end):
    return Source(sym, end, kind, "consolidated", FIX / name, "https://x", "0")


def _by(cands):
    return {(c.period_type, c.metric): c for c in cands}


def test_indas_q1_values():
    cands, filing = parse_ixbrl(_src("indas_q1.html", "TATASTEEL", "INDAS", date(2025, 6, 30)))
    v = _by(cands)
    assert v["Q", "revenue_from_operations"].value == 531781200000
    assert v["Q", "net_profit"].value == 20073600000
    assert v["Q", "net_profit_owners"].value == 20776800000
    assert v["Q", "eps_basic"].value == 1.67
    assert v["Q", "net_profit"].period_start == date(2025, 4, 1)
    assert not [c for c in cands if c.period_type == "FY"]
    assert {c.basis for c in cands} == {"consolidated"}
    assert {c.method for c in cands} == {"xbrl"} and v["Q", "eps_basic"].audited is False
    assert filing["status"] == "parsed"


def test_banking_q4_has_fy_and_bank_metrics():
    cands, filing = parse_ixbrl(_src("banking_q4.html", "AXISBANK", "BANKING", date(2026, 3, 31)))
    v = _by(cands)
    # "Level of rounding: Lakhs" -> values x 1e5
    assert v["Q", "interest_earned"].value == pytest.approx(3417099 * 1e5)
    assert v["Q", "gross_npa_pct"].value == 1.23 and v["Q", "cet1_pct"].value == 14.45
    assert v["Q", "return_on_assets_pct"].value == 1.64
    assert v["Q", "tax_expense"].value == pytest.approx(-38453 * 1e5)
    assert v["Q", "net_profit"].value == pytest.approx(763172 * 1e5)
    assert v["FY", "net_profit"].value == pytest.approx(2649382 * 1e5)
    assert v["FY", "net_profit"].period_start == date(2025, 4, 1)
    assert v["FY", "net_profit"].period_end == date(2026, 3, 31)
    assert v["Q", "net_profit"].period_start == date(2026, 1, 1)
    assert ("Q", "revenue_from_operations") not in v
    assert filing["rounding"] == "Lakhs" and filing["audited"] is True


def test_li_premiums():
    cands, _ = parse_ixbrl(_src("li_q3.html", "HDFCLIFE", "LI", date(2025, 12, 31)))
    v = _by(cands)
    assert v["Q", "first_year_premium"].value == pytest.approx(334360 * 1e5)  # income, not commission
    assert v["Q", "gross_premium"].value == pytest.approx(1882832 * 1e5)
    assert v["Q", "net_premium"].value == pytest.approx(1835142 * 1e5)
    assert v["Q", "net_profit"].value == pytest.approx(41819 * 1e5)
    assert v["Q", "solvency_ratio"].value == 180.0
    assert v["Q", "eps_basic"].value == 1.94 == v["Q", "eps_diluted"].value


def test_ytd_only_in_q4():
    cands, _ = parse_ixbrl(_src("li_q3.html", "HDFCLIFE", "LI", date(2025, 12, 31)))
    assert cands and not [c for c in cands if c.period_type == "FY"]


@pytest.mark.skipif(not (SOURCES / "sources.csv").exists(), reason="no real sources")
def test_all_real_files():
    bad = []
    for s in load_sources(SOURCES):
        if s.kind == "PDF":
            continue
        cands, filing = parse_ixbrl(s)
        got = {c.metric for c in cands if c.period_type == "Q"}
        if filing["status"] != "parsed":
            bad.append((s.rel, filing.get("reason"), sorted(got)))
        assert all(c.metric in METRICS for c in cands)
    assert not bad, bad
