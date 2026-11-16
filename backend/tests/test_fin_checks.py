from datetime import date

from financials.checks import check_arithmetic, check_plausible, check_ratio, check_verbatim
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
