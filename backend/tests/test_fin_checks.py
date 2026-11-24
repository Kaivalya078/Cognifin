from datetime import date

from financials.checks import (
    check_arithmetic,
    check_plausible,
    check_ratio,
    check_verbatim,
)
from financials.store import Candidate


def _c(metric="net_profit", value=1.0, printed="1.00", unit="INR", method="rule"):
    return Candidate("TCS", "consolidated", "Q", date(2025, 4, 1), date(2025, 6, 30), metric,
                     value, unit, printed, 1, method, "bse_pdf", "TCS/2025-06.pdf", "u", None)


def test_verbatim_matches_parenthesised():
    assert check_verbatim(_c(printed="(625.30)"), "Net loss  (625.30)\n 412.10") is None


def test_verbatim_rejects_absent():
    assert check_verbatim(_c(printed="625.30"), "Net loss 412.10") is not None
    assert check_verbatim(_c(printed="625.30", method="xbrl"), "") is None


def test_verbatim_not_substring():
    assert check_verbatim(_c(printed="12.3"), "EPS 112.35") is not None
    assert check_verbatim(_c(printed="1,234.5"), "Revenue 1,234.5 1,100.0") is None


def test_arithmetic_pass_and_fail():
    cr = 1e7
    good = [_c("revenue_from_operations", 100 * cr), _c("other_income", 5 * cr),
            _c("total_income", 105.01 * cr), _c("profit_before_tax", 20 * cr),
            _c("tax_expense", 5 * cr), _c("net_profit", 15 * cr)]
    assert check_arithmetic(good, rounding=0.01 * cr) == {}
    bad = good[:2] + [_c("total_income", 150 * cr)] + good[3:5] + [_c("net_profit", 1500 * cr)]
    fails = check_arithmetic(bad, rounding=0.01 * cr)
    assert set(fails) == {"revenue_from_operations", "other_income", "total_income",
                          "profit_before_tax", "tax_expense", "net_profit"}
    # an exceptional / associate line between PBT and net profit disables rule 2
    assert set(check_arithmetic(bad, rounding=0.01 * cr, direct_pbt=False)) == {
        "revenue_from_operations", "other_income", "total_income"}


def test_ratio_range():
    assert check_ratio(_c("gross_npa_pct", 133.0, unit="pct")) is not None
    assert check_ratio(_c("gross_npa_pct", 1.33, unit="pct")) is None
    assert check_ratio(_c("net_profit", -5e9)) is None


def test_plausible_unit_error():
    assert check_plausible(_c(value=1e14), [1e9, 1.1e9, 0.9e9]) is not None
    assert check_plausible(_c(value=1.2e9), [1e9, 1.1e9, 0.9e9]) is None
    assert check_plausible(_c(value=1e14), []) is None


def test_verbatim_tolerates_ocr_spacing():
    from financials.checks import check_verbatim
    from financials.store import Candidate
    c = Candidate("X", "consolidated", "Q", None, None, "total_expenses", 1.0, "INR", "13,575.93",
                  14, "llm", "bse_pdf", "x", "u", None)
    assert check_verbatim(c, "Total expenses 13 575.93 13 160.90") is None
    assert check_verbatim(c, "Total expenses 13, 575 .93") is None
    assert check_verbatim(c, "Total expenses 113,575.93") is not None


def test_plausible_needs_three_other_periods():
    assert check_plausible(_c(value=1e14), [1e9, 1.1e9]) is None


def test_diluted_eps_above_basic_rejected():
    """DRREDDY: '1.09' basic, '109' diluted (a lost decimal point)."""
    g = [_c("eps_basic", 1.09, unit="INR_per_share"), _c("eps_diluted", 109.0, unit="INR_per_share")]
    assert set(check_arithmetic(g, rounding=1e5)) == {"eps_basic", "eps_diluted"}
    g[1] = _c("eps_diluted", 1.08, unit="INR_per_share")
    assert check_arithmetic(g, rounding=1e5) == {}
    loss = [_c("eps_basic", -2.5, unit="INR_per_share"), _c("eps_diluted", -2.5, unit="INR_per_share")]
    assert check_arithmetic(loss, rounding=1e5) == {}


def test_one_figure_under_two_metrics_rejected():
    """TITAN: the LLM gave PBT's figure as net profit. Neither can be trusted."""
    from financials.checks import check_duplicates
    pbt, np_ = _c("profit_before_tax", 4535e7, "4,535"), _c("net_profit", 4535e7, "4,535", method="llm")
    assert check_duplicates([pbt, np_, _c("tax_expense", 991e7, "991")]) == {id(pbt), id(np_)}
    # equal with a reason: no tax, no other income, EPS pair, no minority
    ok = [pbt, np_, _c("tax_expense", 0.0, "0"),
          _c("revenue_from_operations", 5e9, "500"), _c("total_income", 5e9, "500"),
          _c("other_income", 0.0, "-"),
          _c("eps_basic", 2.0, "2.00", "INR_per_share"), _c("eps_diluted", 2.0, "2.00", "INR_per_share"),
          _c("net_profit_owners", 4535e7, "4,535")]
    assert check_duplicates(ok) == set()
