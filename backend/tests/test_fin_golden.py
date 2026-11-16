import json
from pathlib import Path

from financials.metrics import METRICS

KEY = json.loads((Path(__file__).parent / "financials_golden.json").read_text())
BANKS = {"AXISBANK", "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN"}
INSURERS = {"HDFCLIFE", "SBILIFE"}
NBFC = {"BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "JIOFIN"}


def test_schema():
    assert KEY["version"] == 1 and isinstance(KEY["changelog"], list)
    ids = [c["id"] for c in KEY["cases"]]
    assert len(ids) == len(set(ids))
    for c in KEY["cases"]:
        assert c["period_type"] in ("Q", "FY") and c["basis"] in ("standalone", "consolidated")
        assert c["values"] and all(m in METRICS for m in c["values"])
        assert (c["page"] is None) == c["source_file"].endswith(".html")


def test_spread():
    cases = KEY["cases"]
    pdf = [c for c in cases if c["source_file"].endswith(".pdf")]
    assert len(pdf) >= 20 and len(cases) - len(pdf) >= 5
    assert sum(c["company"] in BANKS for c in cases) >= 4
    assert sum(c["company"] in INSURERS for c in cases) >= 2
    assert sum(c["company"] in NBFC for c in cases) >= 3
    assert len({c["company"] for c in cases}) >= 8


def test_fully_checked():
    assert all(c["checked_by"] == ["claude", "user", "claude-recheck"] for c in KEY["cases"])
