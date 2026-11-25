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

## Numeric router (Phase 4)

2026-11-18, `tests/eval_router.py` over `tests/router_golden.json` (41 cases, 15 end-to-end through `/chat` with gpt-4o-mini), after the final-review fixes.

Router, no LLM: 41 cases, hit rate 32/41, exact match 41/41 (100%).

| Question | Router | Chart points | Chart ≠ DB | Numbers checked | Unmatched | All companies cited |
|---|---|---|---|---|---|---|
| TCS revenue trend | hit | 6 | 0 | 0 | 0 | - |
| What was INFY's PAT in Q2 FY27? | hit | 0 | 0 | 1 | 0 | - |
| INFY net profit FY26 | hit | 0 | 0 | 0 | 0 | - |
| HDFCBANK gross NPA trend | hit | 2 | 0 | 0 | 0 | - |
| HDFCBANK net NPA in Q2 FY27 | hit | 0 | 0 | 1 | 0 | - |
| KOTAKBANK revenue | hit | 5 | 0 | 0 | 0 | - |
| SBILIFE solvency ratio | hit | 4 | 0 | 0 | 0 | - |
| HDFCLIFE gross premium FY26 | hit | 0 | 0 | 0 | 0 | - |
| MARUTI turnover | hit | 5 | 0 | 0 | 0 | - |
| INFY standalone net profit | hit | 4 | 0 | 4 | 0 | - |
| TCS net profit margin | miss | 0 | 0 | - | 0 | - |
| TCS vs INFY revenue Q2 FY27 | hit | 2 | 0 | 3 | ₹32,469.0 crore | yes |
| HDFCBANK vs ICICIBANK gross NPA | hit | 7 | 0 | 0 | 0 | NO |
| HDFCBANK vs RELIANCE revenue | hit | 13 | 0 | 0 | 0 | NO |
| ITC vs MARUTI net profit FY26 | hit | 2 | 0 | 0 | 0 | NO |

Chart values not equal to the DB: 0 of 50 points. Unmatched answer numbers: 1.

**Read with care.**
- The 41 router cases were written alongside the alias list, so 100% shows the rules work as designed, not real-world coverage. Re-measure on questions from real users.
- The first run (before the review fixes) charted HDFCBANK gross NPA as a flat 0.00%: the Phase 3 iXBRL extractor stores 0.0 for ratios a filing doesn't disclose (56 such rows across bank ratios). The router now drops exact-zero rows. The extractor still writes them, so a rebuild fix is open.
- Citations: gpt-4o-mini often writes the verified figures without the `[fin_N]` tag (sometimes with no citations at all). Uncited sentences are skipped by the number check (`checked` 0), and 3 of 4 comparisons fail "all companies cited" for this reason, even though their numbers match the rows.
- `₹32,469.0 crore` is a derived difference (TCS minus INFY), a known false flag of the regex check.

# Answer eval results

2026-11-25, `PYTHONUTF8=1 python -m tests.eval_answers --label v2-baseline` (report `20261125-1225-v2-baseline-answers.json`, also written to `frontend/public/metrics.json`).

**Set:** `tests/golden_set.json` v2, 100 cases over 47 companies: 46 table, 41 narrative, 8 numeric (financials-table figures, no answer page), 5 refusal (key is the refusal sentence). v1's 40 cases unchanged. Every key was checked on its source page twice by Claude; the user spot-checked 10 (all OK).

**Method:** every question goes through the app's real pipeline (`answer_events`, `INTELLIGENT_PARSING_ENABLED=false`, `MULTI_QUERY_ENABLED=false`, generation at temperature 0). A gpt-4o-mini judge gets the exact system + user prompt the model saw, the answer, the key and the kind, and returns claims, `correct` and `refused` as JSON.

- **Faithfulness** = supported claims / all claims over answered (non-refusal) cases. The judge splits the answer into atomic claims and checks each against the context, the same method as RAGAS faithfulness.
- **Correctness** = mean credit (yes 1, partial 0.5, no 0). A refusal on a non-refusal case scores 0; a refusal case scores 1 only if the app refused.
- **Citation validity** = valid / (valid + invalid) cited ids, from `verify_citations`. **Cited share** = answered cases with at least one valid citation.
- **Upload-card rate** = refusal cases whose reply is exactly the refusal sentence (the frontend's upload card triggers on it).
- **Cost** = tokens × gpt-4o-mini prices (constants in `answer_scoring.py`, checked 2026-11-24).

| Run | Faithfulness | Correctness | Citation validity | Cited share | Refusal acc. | Upload card | hit@3 | hit@8 | p50 / p95 | $/question |
|---|---|---|---|---|---|---|---|---|---|---|
| v2-baseline | 0.994 | 0.870 | 1.00 | 0.02 | 1.00 | 1.00 | 0.793 | 0.966 | 9.3 s / 15.0 s | $0.00067 (+ $0.00071 judge) |
| v3-citations (2026-11-25, `20261125-1504-v3-citations-r2-answers.json`) | 0.995 | 0.870 | 0.995 | 0.95 | 1.00 | 1.00 | 0.793 | 0.966 | 6.0 s / 8.9 s | $0.00071 (+ $0.00074 judge) |

By kind, correctness: narrative 0.939, table 0.837, numeric 0.625, refusal 1.000. Retrieval over the 87 page-scored cases; v1's 40 alone: hit@3 0.775 (same as the 186-doc report from 2026-11-16).

**Read with care.**
- **Judge spot-check.** The first baseline's judge was wrong on 5 of the rows read by hand: it invented claims from the key (a refusal scored faithfulness 0; a US$ figure the answer never wrote marked unsupported), misread a written sum, and marked rounded / lakh-crore figures "partial". The judge prompt was revised (claims only from the answer, refusal = no claims, unit conversion, rounding to the key's precision, fiscal-year spellings equal) and the run repeated. In this run the judge is still wrong on about 4 rows: 3 too strict (`tatasteel-2025-turnover` and `lt-2026-orderinflow` rounding, `tcs-2024-netzero` asking for key detail the question didn't ask for) and 1 too lenient (`ntpc-2026-added` "partial" for 1,823 MW vs 9.62 GW). Net effect on correctness is about ±1 point. A stronger judge model would cost more per run.
- **Citations.** Cited share 0.02: gpt-4o-mini almost never writes `[chunk_N]` / `[fin_N]` tags. Faithfulness is still high because the judge checks claims against the whole context, but users see uncited answers. Known open follow-up.
- **Numeric 0.625.** 3 of 8 quarterly-figure questions (`hcltech-q1fy27-revenue`, `kotakbank-q2fy27-gnpa`, `bel-q1fy27-revenue`) were refused although the figures are in the financials table. Router coverage gap, open.
- **Real wrong answers** (not judge noise): `reliance-2023-netprofit`, `wipro-2023-revenue`, `shriramfin-2025-aum` (a nearby figure from a different line), `tatasteel-2024-deliveries` (1.06 MT for 19.91 MT), `icicibank-2024-pat` and `kotakbank-2026-customers` (refused; the second misses retrieval@8).
- One run, published as-is. Two earlier runs were discarded: the first for the judge fix, the second for 2 `APIConnectionError` rows.

## Citations (Phase 6.0)

Goal: answers that point to their page. v2 cited 2% of answered questions.

- **Prompt.** A hard rule asks for the context id in square brackets after every sentence, bullet or table row with a figure or fact (`[chunk_12]`, `[fin_3]`). The template's own examples show it, and a reminder follows the question. *Key Insights* and *Interpretation* may only use cited context, with no general commentary.
- **Code fill** (`generation/citation_fill.py`). A sentence or table row the model left uncited gets a marker only when **every** figure in it matches a number in a passage the model was shown:
  - whole numbers only, never substrings
  - Indian and Western digit grouping are the same
  - a passage figure may round to the answer's precision, never the reverse
  - no unit conversion
  - years and small integers are ignored
  - financials rows win over chunks

  Narrative sentences are never filled.
- **Honesty split.** *Fill-only share* = answered questions cited only because of the fill. *Filled-marker share* = filled markers / all markers.

| Target | v2 | v3 run 1 | **v3 run 2 (published)** | |
|---|---|---|---|---|
| Cited share ≥ 0.90 | 0.021 | 0.947 | **0.947** | pass |
| Citation validity ≥ 0.95 | 1.00 | 0.995 | **0.995** | pass |
| Faithfulness, drop ≤ 1 pt | 0.994 | 0.959 | **0.995** | pass |
| Correctness, drop ≤ 1 pt | 0.870 | 0.855 | **0.870** | pass |
| Fill-only share | – | 0.32 | **0.20** | report |
| Filled-marker share | – | 0.29 | **0.18** | report |

**Runs**, all at gpt-4o-mini prices; total spend about $0.45 against a $0.45 cap:
1. Subset try 1: the fixed 15-question subset (6 narrative, 6 table, 3 numeric, listed in the plan). Cited 15/15, no verdict worse than v2. About $0.03.
2. Full run 1, `v3-citations`: the citation targets passed. Faithfulness dropped 3.5 pts: all 8 unsupported claims were generic *Key Insights / Interpretation* commentary in 2 answers (`icicibank-2025-onebank`, `cipla-2025-revenue`). Correctness was −1.5: two answers picked a different figure line (`itc-2025-cigarettes`, `techm-2023-revenue`), and one is a judge call. Report deleted. About $0.14.
3. Prompt change: insights and interpretation only from cited context. Subset try 2: 15/15 cited, no regressions. About $0.03.
4. Full run 2, `v3-citations-r2`: all targets pass. Published as-is. About $0.14.

Faithfulness and correctness come from one LLM-judged run, so read them ±1 pt (see the judge note above). Latency p50 fell from 9.3 s to 6.0 s, because answers are shorter with at most 3 insights. Also in this change: the chat's "Sources:" row was always empty for cited answers (it deduped by document before filtering to cited passages), and is now fixed. That went unnoticed while almost nothing was cited.

