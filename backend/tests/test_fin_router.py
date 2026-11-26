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


from financials.router import detect_metrics, route  # noqa: E402


def test_aliases():
    assert detect_metrics("What was TCS's PAT?") == ["net_profit"]
    assert detect_metrics("sales and EPS") == ["revenue_from_operations", "eps_basic"]
    assert detect_metrics("diluted EPS") == ["eps_diluted"]
    assert detect_metrics("gross NPA and CET1") == ["gross_npa_pct", "cet1_pct"]
    assert detect_metrics("profit before tax") == ["profit_before_tax"]   # not net_profit too
    assert detect_metrics("net profit margin") == []   # margin is ambiguous -> nothing
    assert detect_metrics("NIM and ROE") == []


def test_route_basic(fin_db):
    lk = route("TCS net profit trend", ["TCS"], [], db=fin_db)
    assert [s.company for s in lk.series] == ["TCS"] and lk.series[0].basis == "consolidated"
    assert len(lk.series[0].rows) == 3 and lk.missing == []


def test_route_none_cases(fin_db):
    assert route("TCS strategy", ["TCS"], [], db=fin_db) is None
    assert route("net profit", [], [], db=fin_db) is None
    assert route("TCS net profit Q1 FY24", ["TCS"], [], db=fin_db) is None


def test_standalone_fallback_and_more_rows_wins(fin_db):
    assert route("ITC net profit", ["ITC"], [], db=fin_db).series[0].basis == "standalone"
    assert route("RELIANCE revenue", ["RELIANCE"], [], db=fin_db).series[0].basis == "standalone"
    assert route("RELIANCE consolidated revenue", ["RELIANCE"], [], db=fin_db).series[0].basis == "consolidated"


def test_bank_revenue_maps_to_interest_earned_per_company(fin_db):
    lk = route("HDFCBANK vs RELIANCE revenue", ["HDFCBANK", "RELIANCE"], [], db=fin_db)
    by = {s.company: s for s in lk.series}
    assert by["HDFCBANK"].metric == "interest_earned" and by["HDFCBANK"].requested == "revenue_from_operations"
    assert by["RELIANCE"].metric == "revenue_from_operations"


def test_unknown_company_listed_missing(fin_db):
    lk = route("TCS vs ACME net profit", ["TCS", "ACME"], [], db=fin_db)
    assert [s.company for s in lk.series] == ["TCS"] and lk.missing == ["ACME"]


def test_fy_and_last_n(fin_db):
    assert [r.period_type for r in route("TCS net profit FY26", ["TCS"], [], db=fin_db).series[0].rows] == ["FY"]
    assert len(route("TCS net profit last 2 quarters", ["TCS"], [], db=fin_db).series[0].rows) == 2


def test_zero_rows_are_not_figures(tmp_path):
    # iXBRL wrote 0.0 for undisclosed bank ratios; they must not outvote real standalone rows.
    from datetime import date

    from financials.store import write_db
    from tests.conftest import fin_candidate as c
    p = str(tmp_path / "z.duckdb")
    write_db(p, [*[c("HDFCBANK", e, metric="gross_npa_pct", unit="pct", value=0.0)
                   for e in (date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31))],
                 c("HDFCBANK", date(2025, 12, 31), metric="gross_npa_pct", unit="pct", basis="standalone", value=1.24)],
             [], [])
    s = route("HDFCBANK gross NPA", ["HDFCBANK"], [], db=p).series[0]
    assert s.basis == "standalone" and [r.value for r in s.rows] == [1.24]


def test_segment_questions_are_not_company_totals(fin_db):
    """v4 eval: ITC 'cigarettes segment' revenue was routed to company revenue."""
    from financials.router import route
    assert route("TCS revenue from the BFSI segment in FY26", ["TCS"], [], db=fin_db) is None
    assert route("TCS net profit of its consumer division", ["TCS"], [], db=fin_db) is None
    assert route("TCS net profit trend", ["TCS"], [], db=fin_db) is not None
