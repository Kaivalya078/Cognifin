from core.app_retrieval import outside_coverage

HELD = {"HINDZINC": {"2025", "2026"}, "TCS": {"2023", "2024", "2025", "2026"}}


def test_year_no_company_holds_is_outside():
    """v4 eval: HINDZINC FY2024 was answered (wrongly) from the FY2025 report's prior-year column."""
    assert outside_coverage(["HINDZINC"], ["2024"], HELD)
    assert outside_coverage(["TCS", "HINDZINC"], ["2019"], HELD)


def test_held_year_unparsed_parts_or_one_covered_company_stay_inside():
    assert not outside_coverage(["HINDZINC"], ["2025"], HELD)
    assert not outside_coverage(["HINDZINC", "TCS"], ["2024"], HELD)   # TCS holds it
    assert not outside_coverage([], ["2024"], HELD)
    assert not outside_coverage(["HINDZINC"], [], HELD)
