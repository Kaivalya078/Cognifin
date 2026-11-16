import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((BACKEND / "tests" / "golden_set.json").read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]
FIELDS = {"id": str, "question": str, "company": str, "year": str,
          "answer_pages": list, "answer": str, "kind": str, "checked_by": list}


def test_schema():
    assert GOLDEN["version"] == 1 and isinstance(GOLDEN["changelog"], list)
    for c in CASES:
        assert set(c) == set(FIELDS), c["id"]
        for k, t in FIELDS.items():
            assert isinstance(c[k], t), (c["id"], k)
        assert c["kind"] in ("table", "narrative"), c["id"]
        assert c["answer_pages"] and all(isinstance(p, int) and p >= 1 for p in c["answer_pages"]), c["id"]
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_pages_exist():
    fitz = pytest.importorskip("fitz")
    for c in CASES:
        pdf = BACKEND / "data" / c["company"] / f"{c['year']}.pdf"
        if not pdf.exists():
            pytest.skip("data/ not present")
        with fitz.open(pdf) as doc:
            assert max(c["answer_pages"]) <= len(doc), c["id"]


def test_coverage():
    assert 38 <= len(CASES) <= 45
    assert len({c["company"] for c in CASES}) >= 15
    assert {"2023", "2024", "2025"} <= {c["year"] for c in CASES}
    table_share = sum(c["kind"] == "table" for c in CASES) / len(CASES)
    assert 0.4 <= table_share <= 0.6


def test_fully_checked():
    for c in CASES:
        assert c["checked_by"] == ["claude", "user", "claude-recheck"], c["id"]
