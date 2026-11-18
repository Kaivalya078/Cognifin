from datetime import date

from financials.router import PeriodSpec, parse_periods


def test_quarter_fy_forms():
    for q in ["Q2 FY27", "q2fy27", "Q2 FY2027", "Q2 of FY27"]:
        assert parse_periods(f"TCS profit {q}", []) == PeriodSpec("Q", [date(2026, 9, 30)])
    assert parse_periods("Q4 FY26", []) == PeriodSpec("Q", [date(2026, 3, 31)])
    assert parse_periods("Q1 FY26", []) == PeriodSpec("Q", [date(2025, 6, 30)])


def test_month_forms():
    for m in ["Sep 2026", "September 2026", "Sept 2026", "quarter ended 30 Sep 2026", "Sep-2026", "Sep'26"]:
        assert parse_periods(f"profit {m}", ["2026"]) == PeriodSpec("Q", [date(2026, 9, 30)])
    assert parse_periods("profit Dec 2025 and Mar 2026", []) == PeriodSpec(
        "Q", [date(2025, 12, 31), date(2026, 3, 31)])
    assert parse_periods("profit Aug 2026", []).ends is None   # not a quarter end -> ignored


def test_fy_forms():
    for f in ["FY25", "FY2025", "FY 25", "2024-25", "fiscal 2025"]:
        assert parse_periods(f"revenue {f}", []) == PeriodSpec("FY", [date(2025, 3, 31)])


def test_last_n_and_trend_and_default():
    assert parse_periods("last 4 quarters revenue", []) == PeriodSpec("Q", last_n=4)
    assert parse_periods("latest quarter revenue", []) == PeriodSpec("Q", last_n=1)
    assert parse_periods("revenue trend", []) == PeriodSpec("Q")
    assert parse_periods("TCS revenue", []) == PeriodSpec("Q")


def test_specific_period_beats_bare_year():
    assert parse_periods("profit Q2 FY2026", ["2026"]) == PeriodSpec("Q", [date(2025, 9, 30)])
    assert parse_periods("profit in 2026", ["2026"]) == PeriodSpec("FY", [date(2026, 3, 31)])
    assert parse_periods("profit 2025 vs 2026", ["2025", "2026"]) == PeriodSpec(
        "FY", [date(2025, 3, 31), date(2026, 3, 31)])


def test_mixed_types_first_match_wins():
    assert parse_periods("FY26 and Q2 FY27", []).period_type == "FY"
