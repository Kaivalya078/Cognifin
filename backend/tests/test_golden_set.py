import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((BACKEND / "tests" / "golden_set.json").read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]
FIELDS = {"id": str, "question": str, "company": str, "year": str,
          "answer_pages": list, "answer": str, "kind": str, "checked_by": list}
KINDS = ("table", "narrative", "numeric", "refusal")
V1_IDS = ["tcs-2024-revenue", "tcs-2024-netzero", "infy-2025-revenue", "infy-2025-acquisitions", "hdfcbank-2024-gnpa", "hdfcbank-2024-merger", "reliance-2023-netprofit", "reliance-2023-gigacomplex", "itc-2025-cigarettes", "itc-2025-hotels-demerger", "sbin-2023-netprofit", "sbin-2023-yono", "icicibank-2025-pat", "icicibank-2025-onebank", "lt-2024-orderbook", "lt-2024-middleeast", "maruti-2023-revenue", "maruti-2023-kharkhoda", "hul-2025-pat", "hul-2025-icecream", "bharti-2024-revenue", "bharti-2024-arpu", "wipro-2023-revenue", "wipro-2023-rizing", "tatasteel-2025-turnover", "tatasteel-2025-porttalbot", "ntpc-2024-pat", "ntpc-2024-capacity", "asianpaint-2023-revenue", "asianpaint-2023-vam", "cipla-2025-revenue", "cipla-2025-approvals", "titan-2024-revenue", "titan-2024-caratlane", "coalindia-2025-dividend", "coalindia-2025-production", "mm-2025-tractors", "mm-2025-suvshare", "bajfinance-2024-aum", "bajfinance-2024-deposits"]
NEW = CASES[len(V1_IDS):]


def test_schema():
    assert GOLDEN["version"] == 3 and isinstance(GOLDEN["changelog"], list)
    for c in CASES:
        assert set(c) == set(FIELDS), c["id"]
        for k, t in FIELDS.items():
            assert isinstance(c[k], t), (c["id"], k)
        assert c["kind"] in KINDS, c["id"]
        assert all(isinstance(p, int) and p >= 1 for p in c["answer_pages"]), c["id"]
        if c["kind"] in ("table", "narrative"):
            assert c["answer_pages"], c["id"]
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_v1_unchanged():
    assert [c["id"] for c in CASES[:len(V1_IDS)]] == V1_IDS
    for c in CASES[:len(V1_IDS)]:
        assert c["checked_by"] == ["claude", "user", "claude-recheck"], c["id"]


def test_pages_exist():
    fitz = pytest.importorskip("fitz")
    for c in CASES:
        if not c["answer_pages"]:
            continue
        pdf = BACKEND / "data" / c["company"] / f"{c['year']}.pdf"
        if not pdf.exists():
            pytest.skip("data/ not present")
        with fitz.open(pdf) as doc:
            assert max(c["answer_pages"]) <= len(doc), c["id"]


def test_coverage():
    assert 115 <= len(CASES) <= 125
    assert len({c["company"] for c in CASES}) >= 60
    assert {"2023", "2024", "2025", "2026"} <= {c["year"] for c in CASES}
    assert sum(c["year"] == "2026" for c in CASES) >= 12
    assert sum(c["kind"] == "numeric" for c in CASES) >= 6
    assert sum(c["kind"] == "refusal" for c in CASES) >= 4
    tn = [c for c in CASES if c["kind"] in ("table", "narrative")]
    assert 0.4 <= sum(c["kind"] == "table" for c in tn) / len(tn) <= 0.6


def test_fully_checked():
    for c in NEW:
        assert {"claude", "claude-recheck"} <= set(c["checked_by"]), c["id"]
    assert sum("user" in c["checked_by"] for c in NEW) >= 10
