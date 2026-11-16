"""
Measure where SIMILARITY_THRESHOLD and SKIP_RERANKER_THRESHOLD sit in the
current embedder's score distribution, on calibration queries that are not
in the golden set.

    python -m tests.calibrate_thresholds --cache index_cache
        -> tests/eval_reports/<ts>-calibration-<model>.json

    python -m tests.calibrate_thresholds --cache index_cache --from-report <old.json>
        -> also prints the values that sit at the same percentiles now

Scores recorded are exactly what the code compares:
  dense  — cosine scores from CorpusManager.search before the threshold filter
  top    — retrieve_context()'s first merged score, which refine_results()
           compares with SKIP_RERANKER_THRESHOLD (an RRF score when BM25 adds
           a second list, a raw cosine when it doesn't)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def percentile_rank(scores, value) -> float:
    """Fraction of scores strictly below value."""
    s = np.asarray(scores, dtype=float)
    return float((s < value).mean()) if s.size else 0.0


def value_at_rank(scores, rank: float) -> float:
    """The score at the same percentile rank (inverse of percentile_rank)."""
    s = np.sort(np.asarray(scores, dtype=float))
    if rank >= 1.0:  # threshold never reached: stay above everything
        return float(s[-1] + 1e-6)
    if rank <= 0.0:
        return float(s[0])
    return float(np.quantile(s, rank))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="index_cache")
    ap.add_argument("--from-report")
    args = ap.parse_args()

    from config import settings
    settings.MULTI_QUERY_ENABLED = False
    settings.INTELLIGENT_PARSING_ENABLED = False
    sim_t, skip_t = settings.SIMILARITY_THRESHOLD, settings.SKIP_RERANKER_THRESHOLD
    settings.SIMILARITY_THRESHOLD = -1.0  # see every dense score

    from core.app_retrieval import load_global_corpus
    from query.query_orchestrator import retrieve_context
    from query.query_understanding import parse_query
    from query.search_plan_builder import build_plan

    queries = json.loads((BACKEND / "tests" / "calibration_queries.json").read_text(encoding="utf-8"))["queries"]
    pipeline, cm = load_global_corpus(args.cache)
    companies = cm.list_available_entities().get("companies", [])

    dense, top = [], []
    for q in queries:
        plan = build_plan(parse_query(q, companies), settings.TOP_K)
        dense += [r.score for r in cm.execute_plan(plan, pipeline.embed_query)]
        merged, _ = retrieve_context(q, corpus_manager=cm, embed_query=pipeline.embed_query,
                                     default_top_k=settings.TOP_K)
        if merged:
            top.append(merged[0].score)

    report = {
        "embedding_model": settings.EMBEDDING_MODEL,
        "thresholds": {"SIMILARITY_THRESHOLD": sim_t, "SKIP_RERANKER_THRESHOLD": skip_t},
        "percentile_rank": {
            "SIMILARITY_THRESHOLD": percentile_rank(dense, sim_t),
            "SKIP_RERANKER_THRESHOLD": percentile_rank(top, skip_t),
        },
        "dense_scores": dense,
        "top_scores": top,
    }
    print(f"{settings.EMBEDDING_MODEL}: {len(dense)} dense scores, {len(top)} top scores")
    for k, v in report["percentile_rank"].items():
        print(f"  {k}={report['thresholds'][k]} sits at percentile rank {v:.3f}")

    if args.from_report:
        old = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        report["recalibrated_from"] = Path(args.from_report).name
        report["recalibrated"] = {
            "SIMILARITY_THRESHOLD": value_at_rank(dense, old["percentile_rank"]["SIMILARITY_THRESHOLD"]),
            "SKIP_RERANKER_THRESHOLD": value_at_rank(top, old["percentile_rank"]["SKIP_RERANKER_THRESHOLD"]),
        }
        print("recalibrated (same percentile as", old["embedding_model"], "):")
        for k, v in report["recalibrated"].items():
            print(f"  {k}={v:.4f}")

    out_dir = BACKEND / "tests" / "eval_reports"
    out_dir.mkdir(exist_ok=True)
    model = settings.EMBEDDING_MODEL.split("/")[-1]
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M}-calibration-{model}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("report:", out)


if __name__ == "__main__":
    main()
