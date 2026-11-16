from datetime import date

from financials.numbers import parse_date, parse_number, to_value, unit_multiplier


def test_indian_grouping():
    assert parse_number("1,08,532.40") == 108532.40
    assert parse_number("108,532.40") == 108532.40


def test_parens_negative():
    assert parse_number("(625.30)") == -625.30 and parse_number("-625.30") == -625.30
    assert parse_number("–625.30") == -625.30


def test_dash_is_none():
    assert parse_number("-") is None and parse_number("") is None and parse_number("—") is None


def test_units():
    assert unit_multiplier("(₹ in crore, except per share data)") == 1e7
    assert unit_multiplier("Rs. in Lakhs") == 1e5 and unit_multiplier("₹ million") == 1e6
    assert unit_multiplier("Statement of results") is None
    assert unit_multiplier("INR (in Actuals)") == 1


def test_eps_not_scaled():
    assert to_value("12.34", "eps_basic", 1e7) == 12.34
    assert to_value("1,234.5", "net_profit", 1e7) == 1234.5e7


def test_pct_not_scaled():
    assert to_value("1.33", "gross_npa_pct", 1e7) == 1.33


def test_dates():
    for s in ["31-03-2026", "31-Mar-2026", "31.03.2026", "31/03/2026", "March 31, 2026",
              "31st March, 2026"]:
        assert parse_date(s) == date(2026, 3, 31), s
