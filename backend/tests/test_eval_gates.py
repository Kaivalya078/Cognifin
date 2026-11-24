"""CI gates on the offline evals: fail the build below today's numbers."""

from tests.eval_financials import gate_failures


def _report(precision, coverage):
    return {"overall": {"precision": precision, "coverage": coverage}}


def test_gate_passes_at_todays_numbers():
    # 228/245 stored = 0.93061…, printed as 93.1%: must not fail on rounding
    assert gate_failures(_report(1.0, 228 / 245), 100, 93.1) == []


def test_gate_names_a_precision_drop():
    fails = gate_failures(_report(0.99, 0.95), 100, 93.1)
    assert len(fails) == 1 and "precision" in fails[0]


def test_gate_names_a_coverage_drop():
    fails = gate_failures(_report(1.0, 0.92), 100, 93.1)
    assert len(fails) == 1 and "coverage" in fails[0]


def test_router_part1_returns_its_failures():
    from tests.eval_router import part1
    assert isinstance(part1(), list)
