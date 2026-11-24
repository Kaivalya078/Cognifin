"""
Answer eval over the golden set: answers each question through the app's real
pipeline (main.answer_question, in-process, response cache off), judges each
answer with gpt-4o-mini, and writes a per-case report plus metrics.json.

    PYTHONUTF8=1 python -m tests.eval_answers --label NAME [--only id1,id2] [--limit N] [--no-metrics]

Costs real OpenAI tokens (~$0.20 per full run). Not part of pytest or CI.
Design: docs/superpowers/specs/2026-11-24-answer-eval-design.md
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from core.citation_verifier import _REF  # noqa: E402
from tests.answer_scoring import is_exact_refusal, parse_judge, score_rows  # noqa: E402

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORTS = BACKEND / "tests" / "eval_reports"
METRICS = BACKEND.parent / "frontend" / "public" / "metrics.json"
V1_CASES = 40  # v2 appends; the first 40 cases are the frozen v1 set

JUDGE_PROMPT = """You grade one answer from a financial-filings Q&A app.

You get CONTEXT (everything the app's model was shown), ANSWER (what it replied), \
KEY (the verified correct answer) and KIND (table, narrative, numeric or refusal).

1. Split ANSWER into atomic factual claims (one fact or figure each). Skip \
follow-up suggestions, headings, citation markers and pure refusals.
2. For each claim: "supported" = true only if CONTEXT states it (same figure, \
unit and period; rounding allowed). "cited" = the chunk_N / fin_N ids written \
written next to that claim in ANSWER itself (empty list if ANSWER writes none; never take ids from CONTEXT).
3. "correct": compare ANSWER with KEY. "yes" = it gives the key's fact (numbers \
must match within rounding); "partial" = part of it, or right with a wrong \
detail; "no" = wrong, missing, or refused.
4. "refused": true if ANSWER declines to give the asked fact (e.g. says the \
documents do not disclose it), else false.

Reply with JSON only:
{"claims": [{"text": str, "supported": bool, "cited": [str]}],
 "correct": "yes" | "partial" | "no", "refused": bool, "reason": str}"""


class RecordingClient:
    """Wraps OpenAIClient: same streaming call as generate_stream, plus token usage."""

    def __init__(self, real):
        self.real = real
        self.model = real.model
        self.is_configured = real.is_configured
        self.client = real.client
        self.last = None

    def generate_stream(self, system_prompt: str, user_message: str):
        self.last = {"system": system_prompt, "user": user_message, "in": 0, "out": 0}
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_message}],
            temperature=0,
            max_tokens=1000,
            stream=True,
            stream_options={"include_usage": True},
        )
        try:
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    self.last["in"] = chunk.usage.prompt_tokens
                    self.last["out"] = chunk.usage.completion_tokens
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield text
        finally:
            getattr(stream, "close", lambda: None)()


def check_flags(settings) -> None:
    for flag in ("INTELLIGENT_PARSING_ENABLED", "MULTI_QUERY_ENABLED"):
        if getattr(settings, flag):
            raise SystemExit(f"{flag} is on: the eval measures the retrieve_global path only. Turn it off.")


def judge(client, context: str, answer: str, key: str, kind: str):
    """(parsed judge verdict or None after one retry, tokens summed over attempts)."""
    tok = {"in": 0, "out": 0}
    user = f"KIND: {kind}\n\nKEY:\n{key}\n\nANSWER:\n{answer}\n\nCONTEXT:\n{context}"
    for _ in range(2):
        r = client.client.chat.completions.create(
            model=client.model,
            messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        tok["in"] += r.usage.prompt_tokens
        tok["out"] += r.usage.completion_tokens
        parsed = parse_judge(r.choices[0].message.content, kind)
        if parsed is not None:
            return parsed, tok
    return None, tok


def build_metrics(label, answer_summary, retrieval_summary, v1_retrieval, financials_report,
                  index_info, golden_meta, settings_info, model, judge_model) -> dict:
    r = retrieval_summary["overall"]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "model": model,
        "judge_model": judge_model,
        "settings": settings_info,
        "golden_set": golden_meta,
        "answers": {k: v for k, v in answer_summary.items() if k not in ("latency_ms", "cost_usd")},
        "retrieval": {"hit@3": r["hit3"], "hit@8": r["hit8"], "mrr": r["mrr"],
                      "recall@60": r["recall60"], "v1_hit@3": v1_retrieval["overall"]["hit3"]},
        "financials": {"precision": financials_report["precision"],
                       "coverage": financials_report["coverage"]},
        "latency_ms": answer_summary["latency_ms"],
        "cost_usd": answer_summary["cost_usd"],
        "index": index_info,
    }


def keep_written_cites(claims: list, answer: str) -> list:
    """Drop judge-reported ids the answer never wrote (the judge can pull them from CONTEXT)."""
    written = {m.group() for m in _REF.finditer(answer)}
    return [{**c, "cited": [i for i in c["cited"] if i in written]} for c in claims]


def _answer_row(main, rc, case) -> dict:
    row = {"id": case["id"], "kind": case["kind"], "company": case["company"], "year": case["year"],
           "question": case["question"], "key": case["answer"], "status": "ok", "answer": "",
           "claims": [], "correct": "no", "refused": False, "exact_refusal": False,
           "citation_check": None, "latency_ms": 0, "tokens": {"in": 0, "out": 0},
           "judge_tokens": {"in": 0, "out": 0}, "intent": None, "reason": ""}
    rc.last = None
    t0 = time.perf_counter()
    try:
        payload = main.answer_question(case["question"])
    except Exception as e:
        row.update(status="error", reason=f"{type(e).__name__}: {e}",
                   latency_ms=round((time.perf_counter() - t0) * 1000))
        return row
    meta = payload.get("metadata", {})
    row.update(answer=payload["answer"], citation_check=meta.get("citation_check"),
               latency_ms=meta.get("latency_ms", 0), intent=meta.get("intent"),
               exact_refusal=is_exact_refusal(payload["answer"]),
               metadata={k: v for k, v in meta.items() if k not in ("citation_check", "latency_breakdown")})
    last = rc.last or {"system": "", "user": "", "in": 0, "out": 0}
    row["tokens"] = {"in": last["in"], "out": last["out"]}
    try:
        parsed, jt = judge(rc, last["system"] + "\n" + last["user"], row["answer"], case["answer"], case["kind"])
    except Exception as e:
        row.update(status="judge_error", reason=f"{type(e).__name__}: {e}")
        return row
    row["judge_tokens"] = jt
    if parsed is None:
        row["status"] = "judge_error"
        return row
    row.update(claims=keep_written_cites(parsed["claims"], row["answer"]), correct=parsed["correct"], reason=parsed["reason"],
               refused=parsed["refused"] or row["exact_refusal"])
    return row


def _disk_mb(path: Path) -> float:
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-metrics", action="store_true")
    ap.add_argument("--set", default=str(BACKEND / "tests" / "golden_set.json"))
    args = ap.parse_args()

    from config import settings
    check_flags(settings)
    settings.CACHE_ENABLED = False

    import main as app
    from core.app_retrieval import load_global_corpus, retrieve_global
    from core.corpus_router import CorpusRouter
    from generation.openai_client import OpenAIClient
    from tests.eval_retrieval import score_case, summarize

    app.response_cache._enabled = False
    real = OpenAIClient()
    if not real.is_configured:
        raise SystemExit("OPENAI_API_KEY is not set.")
    app.pipeline, app.corpus_manager = load_global_corpus(settings.INDEX_CACHE_DIR)
    app.corpus_router = CorpusRouter(app.corpus_manager)
    rc = app.llm_client = RecordingClient(real)
    cm = app.corpus_manager

    golden = json.loads(Path(args.set).read_text(encoding="utf-8"))
    all_cases = golden["cases"]
    v1_ids = {c["id"] for c in all_cases[:V1_CASES]}
    cases = all_cases
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.limit:
        cases = cases[:args.limit]

    rows = []
    for case in cases:
        row = _answer_row(app, rc, case)
        rows.append(row)
        sup = sum(c["supported"] for c in row["claims"])
        print(f"{row['status']:<11} {case['id']:<40} correct={row['correct']:<7} "
              f"claims {sup}/{len(row['claims'])}  {row['latency_ms']} ms")

    ret_rows, ret_lat = [], []
    for case in (c for c in cases if c.get("answer_pages")):
        t0 = time.perf_counter()
        candidates, final, _ = retrieve_global(case["question"], pipeline=app.pipeline, corpus_manager=cm,
                                               top_k=settings.TOP_K, final_k=settings.FINAL_K)
        ret_lat.append((time.perf_counter() - t0) * 1000)
        ret_rows.append(score_case(case, candidates, final, cm.chunk_metadata))
    retrieval = summarize(ret_rows, ret_lat)
    v1_retrieval = summarize([r for r in ret_rows if r["id"] in v1_ids], [])

    summary = score_rows(rows)
    fin_reports = sorted(REPORTS.glob("*-financials.json"))
    financials = json.loads(fin_reports[-1].read_text(encoding="utf-8"))["report"]["overall"] if fin_reports \
        else {"precision": None, "coverage": None}
    index_info = {
        "chunks": cm.num_chunks,
        "documents": len(cm.documents),
        "companies": len({r.metadata.company for r in cm.documents.values()}),
        "disk_mb": _disk_mb(Path(settings.INDEX_CACHE_DIR) / "lancedb"),
    }
    golden_meta = {"version": golden["version"], "cases": len(cases),
                   "companies": len({c["company"] for c in cases}),
                   "kinds": dict(Counter(c["kind"] for c in cases))}
    settings_info = {"intelligent_parsing": settings.INTELLIGENT_PARSING_ENABLED,
                     "multi_query": settings.MULTI_QUERY_ENABLED,
                     "top_k": settings.TOP_K, "final_k": settings.FINAL_K}
    metrics = build_metrics(args.label, summary, retrieval, v1_retrieval, financials, index_info,
                            golden_meta, settings_info, real.model, real.model)

    a = metrics["answers"]
    print(f"\nfaithfulness {a['faithfulness']}  correctness {a['correctness']}  "
          f"citation validity {a['citation_validity']}  refusal {a['refusal_accuracy']}  "
          f"errors {a['errors']}/{a['judge_errors']}")
    print(f"retrieval {metrics['retrieval']}")
    print(f"latency {metrics['latency_ms']}  cost {metrics['cost_usd']}")

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{datetime.now():%Y%m%d-%H%M}-{args.label}-answers.json"
    out.write_text(json.dumps({"metrics": metrics, "retrieval_rows": ret_rows, "rows": rows},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nreport: {out}")
    if not args.no_metrics:
        METRICS.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"metrics: {METRICS}")


if __name__ == "__main__":
    main()
