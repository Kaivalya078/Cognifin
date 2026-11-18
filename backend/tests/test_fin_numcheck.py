from datetime import date

from financials.numcheck import check_numbers
from financials.query import Row
from financials.router import Series


def _row(metric, value, unit):
    return Row("X", "consolidated", "Q", date(2026, 9, 30), 2027, 2, metric, value, unit,
               "https://bse/x.pdf", "X/x.pdf", 8, "rule")


_R1 = _row("net_profit", 12209900000.0, "INR")
_R2 = _row("gross_npa_pct", 1.23, "pct")
IDS = {"fin_1": (Series("X", "net_profit", "net_profit", "consolidated", [_R1]), _R1),
       "fin_2": (Series("X", "gross_npa_pct", "gross_npa_pct", "consolidated", [_R2]), _R2)}


def test_match_crore_lakh_and_plain_table_cell():
    assert check_numbers("Profit was ₹1,221.0 crore [fin_1].", IDS) == {"checked": 1, "unmatched": []}
    assert check_numbers("Profit was ₹1,22,099 lakh [fin_1].", IDS)["unmatched"] == []
    assert check_numbers("| Q2 FY27 | 1,221 | [fin_1] |", IDS)["unmatched"] == []


def test_mismatch_flagged():
    assert check_numbers("Profit was ₹1,500 crore [fin_1].", IDS)["unmatched"] == ["₹1,500 crore"]


def test_pct_tolerance():
    assert check_numbers("GNPA was 1.2% [fin_2].", IDS)["unmatched"] == []
    assert check_numbers("GNPA was 1.4% [fin_2].", IDS)["unmatched"] == ["1.4%"]


def test_ignores_years_quarters_and_growth_pct():
    ids_inr_only = {"fin_1": IDS["fin_1"]}
    r = check_numbers("In Q2 FY27 (Sep 2026) profit rose 12% to ₹1,221 crore [fin_1].", ids_inr_only)
    assert r == {"checked": 1, "unmatched": []}


def test_uncited_sentences_ignored():
    assert check_numbers("Capex was ₹9,999 crore [chunk_4]. Profit ₹1,221 crore [fin_1].", IDS)["checked"] == 1


def test_no_fin_ids_nothing_checked():
    assert check_numbers("Profit ₹1,221 crore [fin_1].", {}) == {"checked": 0, "unmatched": []}
