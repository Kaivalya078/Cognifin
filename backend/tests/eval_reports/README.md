# Retrieval eval results

Golden set: `tests/golden_set.json` (40 questions, 20 table / 20 narrative, 20 companies, FY2023–25; frozen 2026-11-16).
Scorer: `python -m tests.eval_retrieval --label <name>` — the app's real global retrieval path, no LLM.
A hit = a chunk from the right company + year on one of the answer pages. hit@k / MRR are on the 8 chunks the LLM receives; recall@60 is on the merged candidate pool before reranking.

| run | index | hit@3 | hit@8 | MRR | recall@60 | table hit@3 | narrative hit@3 | p50 / p95 | RSS |
|---|---|---|---|---|---|---|---|---|---|
| baseline | legacy: 900-char slices, MiniLM, 263,967 chunks | 0.675 | 0.900 | 0.585 | 0.925 | 0.650 | 0.700 | 2.21 s / 3.01 s | 4.4 GB |
| step1-frozen | structured chunks + bge-base, 491,123 chunks; thresholds unchanged | 0.775 | 0.975 | 0.682 | 1.000 | 0.800 | 0.750 | 2.44 s / 3.29 s | 6.2 GB |
| **step1-recal** (shipped) | same; SIMILARITY_THRESHOLD 0.30 → 0.50 | 0.775 | 0.975 | 0.682 | 1.000 | 0.800 | 0.750 | 2.40 s / 3.19 s | 6.2 GB |

Frozen for every run: RETRIEVAL_K=60, FINAL_K=8, reranker cross-encoder/ms-marco-MiniLM-L-6-v2 on 30 candidates, multi-query and LLM query parsing off.

**Baseline pages.** The legacy index stores no page numbers (every chunk reported page 1, so every "Open PDF" link opened page 1). `tests/legacy_page_map.py` recovered them from the PDFs (263,967/263,967 chunks located) so the baseline is scored at page level.

**Threshold recalibration** (`tests/calibrate_thresholds.py`, on 24 queries not in the golden set):
- `SIMILARITY_THRESHOLD`: 0.30 sat at percentile 0.104 of MiniLM dense scores and at 0.000 of bge's (it filtered nothing). The bge score at percentile 0.104 is 0.506 → shipped 0.50. Per-question results are identical to the frozen run; it trims only candidates that never reached the top 8.
- `SKIP_RERANKER_THRESHOLD` (0.85): percentile 1.000 under both models — it never triggers, because hybrid search hands refine_results an RRF score (≤ 0.033). Left at 0.85; the script's suggested 0.0328 would skip the reranker on every dense-only query, where the compared score is a raw cosine.

No value was chosen by looking at golden-set scores.
