# Retrieval eval results

Golden set: `tests/golden_set.json` (40 questions, 20 table / 20 narrative, 20 companies, FY2023–25; frozen 2026-11-16).
Scorer: `python -m tests.eval_retrieval --label <name>` — the app's real global retrieval path, no LLM.
A hit = a chunk from the right company + year on one of the answer pages. hit@k / MRR are on the 8 chunks the LLM receives; recall@60 is on the merged candidate pool before reranking.

| run | index | hit@3 | hit@8 | MRR | recall@60 | table hit@3 | narrative hit@3 | p50 / p95 | RSS |
|---|---|---|---|---|---|---|---|---|---|
| baseline | legacy: 900-char slices, MiniLM, 263,967 chunks | 0.675 | 0.900 | 0.585 | 0.925 | 0.650 | 0.700 | 2.21 s / 3.01 s | 4.4 GB |
| step1-frozen | structured chunks + bge-base, 491,123 chunks; thresholds unchanged | 0.775 | 0.975 | 0.682 | 1.000 | 0.800 | 0.750 | 2.44 s / 3.29 s | 6.2 GB |
| step1-recal | same; SIMILARITY_THRESHOLD 0.30 → 0.50 | 0.775 | 0.975 | 0.682 | 1.000 | 0.800 | 0.750 | 2.40 s / 3.19 s | 6.2 GB |
| step2 | same chunks + embeddings in LanceDB (disk-backed vectors, native FTS pre-filtered by scope) | 0.800 | 1.000 | 0.705 | 1.000 | 0.800 | 0.800 | 1.85 s / 2.03 s | 0.88 GB |
| **step2-reviewfix** (shipped) | same; context enrichment only on the final 8, scope relaxation for unindexed years/doc types | 0.800 | 1.000 | 0.705 | 1.000 | 0.800 | 0.800 | 1.38 s / 1.63 s | 0.88 GB |

Frozen for every run: RETRIEVAL_K=60, FINAL_K=8, reranker cross-encoder/ms-marco-MiniLM-L-6-v2 on 30 candidates, multi-query and LLM query parsing off.

**Baseline pages.** The legacy index stores no page numbers (every chunk reported page 1, so every "Open PDF" link opened page 1). `tests/legacy_page_map.py` recovered them from the PDFs (263,967/263,967 chunks located) so the baseline is scored at page level.

**Threshold recalibration** (`tests/calibrate_thresholds.py`, on 24 queries not in the golden set):
- `SIMILARITY_THRESHOLD`: 0.30 sat at percentile 0.104 of MiniLM dense scores and at 0.000 of bge's (it filtered nothing). The bge score at percentile 0.104 is 0.506 → shipped 0.50. Per-question results are identical to the frozen run; it trims only candidates that never reached the top 8.
- `SKIP_RERANKER_THRESHOLD` (0.85): percentile 1.000 under both models — it never triggers, because hybrid search hands refine_results an RRF score (≤ 0.033). Left at 0.85; the script's suggested 0.0328 would skip the reranker on every dense-only query, where the compared score is a raw cosine.

No value was chosen by looking at golden-set scores.

**Step 2 vs Step 1.** Same chunks and embeddings; quality within one question (one more hit, from LanceDB's FTS ranking differing from rank_bm25's). RSS falls 7× because vectors, text and metadata stay on disk instead of a 1.5 GB FAISS array plus pickles in RAM, and keyword search is pre-filtered by company/year instead of scoring all 491k chunks first. Re-index: 48 min on an RTX 3050 (Step 1: 66 min, mostly full-index rewrites after every PDF).

# Financials table eval results

Answer key: `tests/financials_golden.json` (26 cases, 245 values: 20 PDF cases, 6 iXBRL; 4 banks, 2 insurers, 3 NBFCs; hand-drafted, spot-checked by the user, every value re-found on its source page).
Scorer: `python -m tests.eval_financials --label <name>` over `index_cache/financials.duckdb`.
Precision = stored values matching the key / key values stored. Coverage = key values stored / all key values. A match is within one unit of the stored value's last printed digit in its unit ("1,234.56" in crore: ₹1 lakh; "4,082" in millions: ₹10 lakh) — v1–v6 used ₹1 lakh or 0.01%, whichever was larger, which let a last-digit misread of a large figure pass. The scorer also lists corpus-wide SUSPECTs: one printed figure stored as two metrics of one filing.
Gate: precision ≥ 99%; coverage ≥ 90% overall, ≥ 80% bank and insurer metrics.

| run | change | precision | coverage | all | bank | insurer | wrong |
|---|---|---|---|---|---|---|---|
| v1 | first build | 94.7% | 76.7% | 77.3% | 52.6% | 94.7% | 10 |
| v2 | rules: space-padded number spans split; an unreadable first row settles its label; profit after associates wins. LLM values must sit under a column of the claimed period | 99.5% | 74.3% | 74.9% | 47.4% | 94.7% | 1 |
| v3 | rules: undated header columns explain their numbers; OCR'd "croresl" unit; policyholders' account skipped for PBT/tax/profit; "Earnings per share: Basic and diluted"; OCR spaces beside separators; wrapped labels. Verbatim tolerates OCR spacing; LLM's wrong page corrected when the value is on exactly one sent page; LLM asked for every basis a page title names | 99.1% | 92.7% | 92.8% | 89.5% | 94.7% | 2 |
| v4-ocr | rules: "a) Current tax" is an item, not a wrapped label; owners' share after a discontinued block wins. OCR (rapidocr) for image-only pages: failed files 22 → 14 | 99.1% | 92.2% | 92.8% | 89.5% | 89.5% | 2 |
| v5-ocr-deskew | OCR cells deskewed by the median box slope (a 1.5° scan of SBILIFE's statement paired labels with the next row); text-layer pages read before OCR'd copies | 99.6% | 93.1% | 92.8% | 89.5% | 100.0% | 1 |
| v6 | solvency normalised at extraction (percent ÷ 100, hundredth × 100) and anything outside 0.5–10x sent to review (the LLM had read "14,500" from the Fair Value Change row) | **100.0%** | **92.7%** | 92.8% | 89.5% | 94.7% | 0 |

| **v7-review-fixes** (shipped) | whole-branch review: the LLM's unit must be the only unit word on its cited page and the rules' unit on a laid-out page (NESTLEIND's "crore" on a ₹ million page, DRREDDY's crore on a millions page: 10× errors); a label no longer carries across pages and "ii Profit before tax" is an item (ADANIPORTS' PBT as EPS); EPS from the all-operations block, never discontinued-only (TMPV); diluted EPS above basic rejected (DRREDDY "109"); one figure under two metrics of a filing rejected (TITAN PBT as net profit, LT, BHARTIARTL, SBILIFE); cash-flow and notes tables skipped; plausibility needs ≥3 other periods and never rejects iXBRL. Scored with the stricter tolerance | **100.0%** | **93.1%** | 93.7% | 89.5% | 89.5% | 0 |

Build v7: 372 files — 330 parsed, 20 partial, 22 failed; 5,243 rows (iXBRL 2,954, rules 1,491, LLM 798); 473 values held in `review`. The 8 extra failed files vs v6 are LLM-only filings whose pages print no unit word: their values cannot be checked, and NESTLEIND's were 10× off.

Build v6: 372 files — 340 parsed, 18 partial, 14 failed; 5,513 rows (iXBRL, rules, LLM); 498 values held in `review`.
The answer key has no scan-only case, so values read by OCR are guarded by the arithmetic and plausibility checks but not measured here.
Remaining misses (18 values): EPS and ratio rows the rules and LLM both left empty, and values that failed verbatim/arithmetic (correctly or not) — see the `missing` list in the v6 report.
