"""Pure scoring for the answer eval (tests/eval_answers.py). No network."""

import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.citation_verifier import _REF, bare_chunk_id  # noqa: E402

# gpt-4o-mini, USD per 1M tokens (checked 2026-11-24, openai.com/api/pricing).
PRICE_IN_PER_M = 0.15
PRICE_OUT_PER_M = 0.60

# Mirrors frontend/src/utils/refusal.js.
_REFUSAL = "not available in the provided documents"
_EDGES = re.compile(r"^[\"'*\s]+|[\"'*\s]+$")
_CREDIT = {"yes": 1.0, "partial": 0.5, "no": 0.0}


def is_exact_refusal(text: str) -> bool:
    bare = _EDGES.sub("", text or "")
    bare = bare[:-1] if bare.endswith(".") else bare
    return bare.lower() == _REFUSAL


def parse_judge(raw: str, kind: str) -> dict | None:
    """Validated judge reply, or None if anything is off (caller retries once)."""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("claims"), list) or d.get("correct") not in _CREDIT:
        return None
    claims = []
    for c in d["claims"]:
        if not isinstance(c, dict) or not isinstance(c.get("supported"), bool):
            return None
        cited = c.get("cited") or []
        if not isinstance(cited, list):
            return None
        claims.append({"text": str(c.get("text", "")), "supported": c["supported"],
                       "cited": [bare_chunk_id(str(x)) for x in cited]})
    refused = d.get("refused", False)
    if kind == "refusal" and not isinstance(d.get("refused"), bool):
        return None
    return {"claims": claims, "correct": d["correct"], "refused": refused is True,
            "reason": str(d.get("reason", ""))}


def _credit(r: dict) -> float:
    if r["status"] != "ok":
        return 0.0
    if r["kind"] == "refusal":
        return 1.0 if r["refused"] else 0.0
    return 0.0 if r["refused"] else _CREDIT.get(r["correct"], 0.0)


def _faith(rows: list) -> float | None:
    ok = [r for r in rows if r["status"] == "ok" and r["kind"] != "refusal"]
    total = sum(len(r["claims"]) for r in ok)
    return sum(c["supported"] for r in ok for c in r["claims"]) / total if total else None


def _cost(tok: dict) -> float:
    return tok["in"] / 1e6 * PRICE_IN_PER_M + tok["out"] / 1e6 * PRICE_OUT_PER_M


def _fill_split(answered: list) -> tuple:
    """(share of answered questions cited only by the code fill, filled markers / all markers)."""
    fill_only = markers = filled = 0
    for r in answered:
        fill = {bare_chunk_id(i) for i in (r.get("metadata") or {}).get("citation_fill", [])}
        valid = {bare_chunk_id(i) for i in (r["citation_check"] or {}).get("valid_citations", [])}
        fill_only += bool(valid) and valid <= fill
        filled += len((r.get("metadata") or {}).get("citation_fill", []))
        markers += len(_REF.findall(r.get("answer") or ""))
    return (fill_only / len(answered) if answered else None,
            filled / markers if markers else None)


def score_rows(rows: list) -> dict:
    n = len(rows)
    checks = [r["citation_check"] for r in rows if r["citation_check"]]
    valid = sum(len(c.get("valid_citations", [])) for c in checks)
    invalid = sum(len(c.get("invalid_citations", [])) for c in checks)
    answered = [r for r in rows if r["status"] == "ok" and r["kind"] != "refusal"]
    refusals = [r for r in rows if r["kind"] == "refusal"]
    lat = sorted(r["latency_ms"] for r in rows)
    p95 = statistics.quantiles(lat, n=20)[-1] if len(lat) >= 2 else (lat[0] if lat else 0.0)
    kinds = sorted({r["kind"] for r in rows})
    fill_only_share, filled_marker_share = _fill_split(answered)
    return {
        "faithfulness": _faith(rows),
        "correctness": sum(map(_credit, rows)) / n if n else None,
        "citation_validity": valid / (valid + invalid) if valid + invalid else None,
        "cited_share": (sum(1 for r in answered if (r["citation_check"] or {}).get("valid_citations"))
                        / len(answered)) if answered else None,
        "fill_only_share": fill_only_share,
        "filled_marker_share": filled_marker_share,
        "refusal_accuracy": (sum(_credit(r) for r in refusals) / len(refusals)) if refusals else None,
        "upload_card_rate": (sum(r["exact_refusal"] for r in refusals) / len(refusals)) if refusals else None,
        "by_kind": {k: {"n": len(ks := [r for r in rows if r["kind"] == k]),
                        "faithfulness": _faith(ks),
                        "correctness": sum(map(_credit, ks)) / len(ks)} for k in kinds},
        "errors": sum(r["status"] == "error" for r in rows),
        "judge_errors": sum(r["status"] == "judge_error" for r in rows),
        "latency_ms": {"p50": statistics.median(lat) if lat else 0.0, "p95": p95},
        "cost_usd": {
            "per_question": round(sum(_cost(r["tokens"]) for r in rows) / n, 6) if n else 0.0,
            "judge_per_question": round(sum(_cost(r["judge_tokens"]) for r in rows) / n, 6) if n else 0.0,
        },
    }
