import json

import pytest

from tests.answer_scoring import is_exact_refusal, parse_judge, score_rows


def test_exact_refusal_matches_variants():
    assert is_exact_refusal("Not available in the provided documents.")
    assert is_exact_refusal('"**not available in the provided documents**"')
    assert not is_exact_refusal("Revenue is not available in the provided documents for 2026.")
    assert not is_exact_refusal("")


def test_parse_judge_valid():
    raw = json.dumps({
        "claims": [
            {"text": "Revenue was 10", "supported": True, "cited": ["[TCS]:chunk_12"]},
            {"text": "Profit was 2", "supported": False, "cited": []},
        ],
        "correct": "yes", "reason": "ok",
    })
    p = parse_judge(raw, "table")
    assert p["claims"][0]["cited"] == ["chunk_12"]
    assert p["correct"] == "yes"
    assert p["refused"] is False


@pytest.mark.parametrize("raw,kind", [
    ("not json", "table"),
    (json.dumps({"claims": [{"text": "a", "supported": "true", "cited": []}], "correct": "yes"}), "table"),
    (json.dumps({"claims": [], "correct": "maybe"}), "table"),
    (json.dumps({"claims": [], "correct": "yes"}), "refusal"),
])
def test_parse_judge_rejects_bad(raw, kind):
    assert parse_judge(raw, kind) is None


def _row(**kw):
    base = {"kind": "table", "status": "ok", "claims": [], "correct": "no", "refused": False,
            "exact_refusal": False, "citation_check": None, "latency_ms": 0,
            "tokens": {"in": 0, "out": 0}, "judge_tokens": {"in": 0, "out": 0}}
    base.update(kw)
    return base


def test_score_rows_math():
    claims = [{"text": "a", "supported": True, "cited": []},
              {"text": "b", "supported": True, "cited": []},
              {"text": "c", "supported": False, "cited": []}]
    rows = [
        _row(claims=claims, correct="partial", latency_ms=1000,
             citation_check={"valid_citations": ["chunk_1", "chunk_2"], "invalid_citations": ["chunk_9"]},
             tokens={"in": 1_000_000, "out": 0}),
        _row(kind="refusal", refused=True, exact_refusal=True, correct="yes", latency_ms=500),
        _row(kind="narrative", status="error", latency_ms=0),
    ]
    s = score_rows(rows)
    assert s["faithfulness"] == pytest.approx(2 / 3)
    assert s["correctness"] == pytest.approx((0.5 + 1 + 0) / 3)
    assert s["citation_validity"] == pytest.approx(2 / 3)
    assert s["refusal_accuracy"] == 1.0
    assert s["upload_card_rate"] == 1.0
    assert s["errors"] == 1
    assert s["judge_errors"] == 0
    assert s["cost_usd"]["per_question"] == round(0.15 / 3, 6)
    assert s["by_kind"]["table"]["faithfulness"] == pytest.approx(2 / 3)


def test_score_rows_no_claims_gives_none():
    s = score_rows([_row(kind="refusal", refused=True, correct="yes")])
    assert s["faithfulness"] is None
    assert s["citation_validity"] is None
