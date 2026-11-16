"""
Retrieval scorer over the golden set (tests/golden_set.json).

Runs each question through the app's real global retrieval path
(core.app_retrieval.retrieve_global) with no LLM, and scores whether a
chunk from the right company + year + answer page reached the results.

    python -m tests.eval_retrieval --label baseline [--cache index_cache]

Writes tests/eval_reports/<YYYYMMDD-HHMM>-<label>.json.
"""

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_VID = re.compile(r"chunk_(\d+)")


def chunk_location(chunk_id: str, chunk_metadata: dict):
    """(company, year, page_number) for a result's chunk_id, or None."""
    m = _VID.search(chunk_id.replace("[expanded]", ""))
    meta = chunk_metadata.get(int(m.group(1))) if m else None
    if meta is None:
        return None
    return meta.company, str(meta.year), int(meta.page_number)


def _is_hit(case: dict, result, chunk_metadata: dict) -> bool:
    loc = chunk_location(result.chunk_id, chunk_metadata)
    return (loc is not None and loc[0] == case["company"]
            and loc[1] == str(case["year"]) and loc[2] in case["answer_pages"])


def score_case(case: dict, candidates: list, final: list, chunk_metadata: dict) -> dict:
    ranks = [i for i, res in enumerate(final) if _is_hit(case, res, chunk_metadata)]
    first = ranks[0] + 1 if ranks else None
    return {
        "id": case["id"],
        "kind": case["kind"],
        "hit3": first is not None and first <= 3,
        "hit8": first is not None and first <= 8,
        "rr": 1.0 / first if first else 0.0,
        "recall60": any(_is_hit(case, res, chunk_metadata) for res in candidates[:60]),
    }


def _agg(rows: list) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit3": 0.0, "hit8": 0.0, "mrr": 0.0, "recall60": 0.0}
    return {
        "n": n,
        "hit3": sum(r["hit3"] for r in rows) / n,
        "hit8": sum(r["hit8"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
        "recall60": sum(r["recall60"] for r in rows) / n,
    }


def summarize(rows: list, latencies_ms: list) -> dict:
    kinds = sorted({r["kind"] for r in rows})
    lat = sorted(latencies_ms)
    p95 = statistics.quantiles(lat, n=20)[-1] if len(lat) >= 2 else (lat[0] if lat else 0.0)
    return {
        "overall": _agg(rows),
        "by_kind": {k: _agg([r for r in rows if r["kind"] == k]) for k in kinds},
        "latency_ms": {"p50": statistics.median(lat) if lat else 0.0, "p95": p95},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--cache", default="index_cache")
    ap.add_argument("--set", default=str(BACKEND / "tests" / "golden_set.json"))
    args = ap.parse_args()

    from config import settings
    # Deterministic, LLM-free retrieval regardless of .env.
    settings.MULTI_QUERY_ENABLED = False
    settings.INTELLIGENT_PARSING_ENABLED = False
    settings.INDEX_CACHE_DIR = args.cache

    from core.app_retrieval import load_global_corpus, retrieve_global, rss_mb

    cases = json.loads(Path(args.set).read_text(encoding="utf-8"))["cases"]
    pipeline, cm = load_global_corpus(args.cache)
    rss = rss_mb()

    rows, lat = [], []
    for case in cases:
        t0 = time.perf_counter()
        candidates, final, _ = retrieve_global(
            case["question"], pipeline=pipeline, corpus_manager=cm,
            top_k=settings.TOP_K, final_k=settings.FINAL_K,
        )
        lat.append((time.perf_counter() - t0) * 1000)
        row = score_case(case, candidates, final, cm.chunk_metadata)
        row["returned"] = [chunk_location(r.chunk_id, cm.chunk_metadata) for r in final]
        rows.append(row)
        mark = "✓" if row["hit3"] else ("~" if row["hit8"] else ("·" if row["recall60"] else "✗"))
        print(f"{mark} {case['id']:<40} rr={row['rr']:.2f}  {lat[-1]:.0f} ms")

    summary = summarize(rows, lat)
    print("\n          n   hit@3  hit@8   MRR  recall@60")
    for name, s in [("overall", summary["overall"]), *summary["by_kind"].items()]:
        print(f"{name:<9} {s['n']:>3}  {s['hit3']:.3f}  {s['hit8']:.3f}  {s['mrr']:.3f}  {s['recall60']:.3f}")
    print(f"latency p50 {summary['latency_ms']['p50']:.0f} ms, p95 {summary['latency_ms']['p95']:.0f} ms; RSS {rss:.0f} MB")

    out_dir = BACKEND / "tests" / "eval_reports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M}-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "golden_set": Path(args.set).name,
        "settings": {k: getattr(settings, k) for k in (
            "EMBEDDING_MODEL", "QUERY_INSTRUCTION", "RETRIEVAL_K", "FINAL_K",
            "RERANKER_MODEL", "RERANKER_MAX_CANDIDATES", "SIMILARITY_THRESHOLD",
            "SKIP_RERANKER_THRESHOLD", "CONTEXT_WINDOW", "BM25_ENABLED")},
        "rss_mb": rss,
        "summary": summary,
        "rows": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nreport: {out}")


if __name__ == "__main__":
    main()
