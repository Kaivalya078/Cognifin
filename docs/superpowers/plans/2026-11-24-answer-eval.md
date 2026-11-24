# Answer Eval + Faithfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the golden set to ~100 verified cases and add a local runner that answers each through the real pipeline, judges faithfulness/correctness with gpt-4o-mini, and writes `frontend/public/metrics.json`.

**Architecture:** Pure scoring helpers in `backend/tests/answer_scoring.py` (unit-tested, no network). A runner `backend/tests/eval_answers.py` loads the app in-process like `main.lifespan`, turns the response cache off, wraps `main.llm_client` to record prompt + token usage, calls `main.answer_question`, judges each answer, and writes a per-case report plus `metrics.json`. Retrieval numbers reuse `tests/eval_retrieval.py`'s `score_case`/`summarize`.

**Tech Stack:** Python 3.13, OpenAI SDK (already installed), pytest, PyMuPDF (`fitz`) for verifying answer pages.

**Spec:** `docs/superpowers/specs/2026-11-24-answer-eval-design.md`

## Global Constraints

- No new dependency. No production-code change (`backend/main.py`, `generation/`, `core/` untouched).
- Models: answers `gpt-4o-mini` (whatever `llm_client.model` is), judge `gpt-4o-mini`, judge `temperature=0`, `response_format={"type":"json_object"}`.
- Runner exits non-zero if `settings.INTELLIGENT_PARSING_ENABLED` or `settings.MULTI_QUERY_ENABLED` is true.
- Response cache: no reads, no writes during the run.
- v1's 40 cases byte-identical (same ids and fields); v1 hit@3 must still read 0.800.
- Kinds: `table`, `narrative`, `numeric`, `refusal`. `answer_pages` may be `[]` only for `numeric` (iXBRL source) and `refusal`.
- `checked_by`: v1 cases `["claude","user","claude-recheck"]`; new cases at least `["claude","claude-recheck"]`, plus `"user"` if spot-checked.
- Correctness: yes = 1, partial = 0.5, no / error = 0.
- Refusal sentence (strict rule, mirrors `frontend/src/utils/refusal.js`): whole answer, quotes/`*`/whitespace and one trailing `.` stripped, case-insensitive, equals `not available in the provided documents`.
- Prices (gpt-4o-mini, record the check date in the constant's comment): $0.15 / 1M input, $0.60 / 1M output. Verify on openai.com/api/pricing before Task 4's run.
- Windows: run with `PYTHONUTF8=1`.
- `metrics.json` path: `frontend/public/metrics.json`, committed. Per-case report: `backend/tests/eval_reports/<YYYYMMDD-HHMM>-<label>-answers.json`, committed.

## Review Focus

- A judge reply that is valid JSON but missing keys or with `supported` as a string ("true") → treat as judge_error after one retry, never crash or count it as supported.
- An answer with zero claims that is not a refusal (e.g. empty answer, or the pipeline errored) → contributes 0 claims to faithfulness and `no` to correctness; faithfulness denominator 0 overall → report `null`, not divide-by-zero.
- `answer_question` raising (OpenAI timeout, KeyError) mid-run → case recorded as `error`, run continues, count in `answers.errors`.
- Recording client must still yield text exactly like `generate_stream` (the final usage chunk has empty `choices`) — otherwise `hold_follow_ups` sees different text and answers drift from production.
- `[expanded]chunk_12` / `[TCS]:chunk_12` ids in context vs bare ids the judge returns → compare bare ids (`core.citation_verifier.bare_chunk_id`).

---

### Task 1: Pure scoring helpers

**Files:**
- Create: `backend/tests/answer_scoring.py`
- Test: `backend/tests/test_answer_scoring.py`

**Interfaces:**
- Produces:
  - `is_exact_refusal(text: str) -> bool`
  - `parse_judge(raw: str, kind: str) -> dict | None` — returns `{"claims": [{"text": str, "supported": bool, "cited": [str]}], "correct": "yes"|"partial"|"no", "refused": bool}` or `None` if invalid (not JSON, missing `claims`/`correct`, `supported` not a bool, `correct` not one of the three, `refused` missing/non-bool on a `refusal` case). `refused` defaults to `False` for non-refusal kinds. `cited` ids normalised with `bare_chunk_id`.
  - `score_rows(rows: list[dict]) -> dict` — rows have keys `kind, status ("ok"|"error"|"judge_error"), claims, correct, refused, exact_refusal, citation_check (verify_citations dict or None), latency_ms, tokens {"in","out"}, judge_tokens {"in","out"}`. Returns the `answers` block of metrics.json plus `latency_ms {p50,p95}` and `cost_usd {per_question, judge_per_question}`:
    - `faithfulness` = Σ supported / Σ claims over `status=="ok"` non-refusal rows; `None` if Σ claims == 0. `by_kind[k]["faithfulness"]` likewise.
    - `correctness` = mean of credit over all rows (error/judge_error → 0); refusal rows: credit 1 iff `refused`, else 0; non-refusal rows with `refused` → 0.
    - `citation_validity` = Σ valid / Σ (valid+invalid) over rows with citation_check; `None` if 0. `cited_share` = share of ok non-refusal rows with ≥1 valid citation.
    - `refusal_accuracy`, `upload_card_rate` over refusal rows (`None` if none).
    - `errors` = count of error rows, `judge_errors` = count of judge_error rows.
    - p95 with `statistics.quantiles(n=20)[-1]` (same as `eval_retrieval.summarize`).
  - `PRICE_IN_PER_M = 0.15`, `PRICE_OUT_PER_M = 0.60`.

- [ ] **Step 1: Write the failing tests** in `test_answer_scoring.py`:
  - `test_exact_refusal_matches_variants`: `"Not available in the provided documents."`, `'"**not available in the provided documents**"'` → True; `"Revenue is not available in the provided documents for 2026."`, `""` → False.
  - `test_parse_judge_valid`: JSON with 2 claims, `"cited": ["[TCS]:chunk_12"]` → claims[0]["cited"] == ["chunk_12"], correct "yes", refused False.
  - `test_parse_judge_rejects_bad`: `"not json"`, `{"claims": [{"text":"a","supported":"true","cited":[]}], "correct":"yes"}`, `{"claims": [], "correct":"maybe"}`, and for kind `refusal` a reply without `refused` → all `None`.
  - `test_score_rows_math`: three rows — ok table (3 claims, 2 supported, correct "partial", citations valid 2/invalid 1, latency 1000, tokens in 1_000_000 out 0), ok refusal (0 claims, refused True, exact True), error narrative → faithfulness 2/3, correctness (0.5+1+0)/3, citation_validity 2/3, refusal_accuracy 1.0, upload_card_rate 1.0, errors 1, cost per_question == (0.15)/3 rounded to 6 dp.
  - `test_score_rows_no_claims_gives_none`: only a refusal row → `faithfulness is None`, `citation_validity is None`.

- [ ] **Step 2: Run** `cd backend && python -m pytest tests/test_answer_scoring.py -q` — Expected: FAIL (`ModuleNotFoundError: tests.answer_scoring`).

- [ ] **Step 3: Implement** the four names above in `answer_scoring.py` (stdlib `json`, `re`, `statistics`; import `bare_chunk_id` from `core.citation_verifier`; add `sys.path` insert of backend dir as in `eval_retrieval.py`).

- [ ] **Step 4: Run** `python -m pytest tests/test_answer_scoring.py -q` — Expected: 5 passed. Then `ruff check .` — Expected: All checks passed.

- [ ] **Step 5: Commit** `git add backend/tests/answer_scoring.py backend/tests/test_answer_scoring.py && git commit -m "test(eval): pure scoring for answer eval (faithfulness, correctness, refusal, cost)"`

### Task 2: Runner `eval_answers.py`

**Files:**
- Create: `backend/tests/eval_answers.py`
- Test: `backend/tests/test_eval_answers.py`

**Interfaces:**
- Consumes: Task 1 names; `main.answer_question`, `main.llm_client`, `main.response_cache`; `core.app_retrieval.load_global_corpus, retrieve_global`; `tests.eval_retrieval.score_case, summarize`.
- Produces:
  - `class RecordingClient` — wraps an `OpenAIClient`; has `.model`, `.is_configured`, `.client`; `generate_stream(system_prompt, user_message)` makes the same `chat.completions.create` call as `OpenAIClient.generate_stream` (same messages, `temperature=0`, `max_tokens=1000`, `stream=True`) plus `stream_options={"include_usage": True}`, yields the same text pieces, and sets `.last = {"system": ..., "user": ..., "in": int, "out": int}`.
  - `check_flags(settings) -> None` — raises `SystemExit` with a message naming the flag if `INTELLIGENT_PARSING_ENABLED` or `MULTI_QUERY_ENABLED`.
  - `judge(client, context: str, answer: str, key: str, kind: str) -> tuple[dict | None, dict]` — one call (one retry on `parse_judge` → None); returns `(parsed_or_None, {"in","out"})` tokens summed over attempts.
  - `build_metrics(label, answer_summary, retrieval_summary, v1_retrieval, financials_report, index_info, golden_meta, settings_info, model, judge_model) -> dict` — the exact shape in the spec's `metrics.json` section.
  - CLI: `python -m tests.eval_answers --label NAME [--only id1,id2] [--limit N] [--no-metrics]` (`--no-metrics` writes the report only; used by smoke runs so a partial run never overwrites metrics.json).
- Judge system prompt constant `JUDGE_PROMPT`: given CONTEXT (the system prompt text the model saw), ANSWER, KEY; split ANSWER into atomic factual claims (skip follow-up suggestions and citation markers); per claim `supported` = the CONTEXT states it; `cited` = the `chunk_N`/`fin_N` ids next to it; `correct` = ANSWER vs KEY (yes / partial / no, numbers must match within rounding); for kind refusal, `refused` = ANSWER declines to give the asked fact. JSON only.
- Context passed to the judge = `RecordingClient.last["system"]` plus `"\n"` plus `last["user"]` (`build_prompt` puts the context in the system prompt; intent prompts may split it, so sending both is always complete).
- Index info: `corpus_manager.num_chunks`, `len(corpus_manager.documents)`, distinct companies in `documents`, size of `index_cache/lancedb` (sum of file sizes, MB, 1 dp).
- Financials: newest `tests/eval_reports/*-financials.json` → `report.overall.precision/coverage`.
- Retrieval: for cases with non-empty `answer_pages`, call `retrieve_global` (same args as `eval_retrieval.main`) and `score_case`; `summarize` for all and for v1 ids (`golden_set.json` changelog marks them; simplest: cases whose `id` is in the first 40 of the list — v2 appends).

- [ ] **Step 1: Write the failing tests** in `test_eval_answers.py` (no network):
  - `test_check_flags_refuses`: a `SimpleNamespace(INTELLIGENT_PARSING_ENABLED=True, MULTI_QUERY_ENABLED=False)` → `pytest.raises(SystemExit)`; both False → returns None.
  - `test_recording_client_yields_same_text_and_usage`: fake `client.chat.completions.create` returning an iterator of chunk objects `[delta "Hel", delta "lo", chunk with choices=[] and usage(prompt_tokens=7, completion_tokens=2)]` → `"".join(rc.generate_stream("S","U")) == "Hello"`, `rc.last == {"system":"S","user":"U","in":7,"out":2}`, and the create call kwargs include `stream_options={"include_usage": True}`, `temperature=0`.
  - `test_judge_retries_once_then_none`: fake client returning invalid JSON twice → `(None, tokens)` with 2 calls made; returning invalid then valid → parsed dict, 2 calls.
  - `test_build_metrics_shape`: keys exactly `generated_at, label, model, judge_model, settings, golden_set, answers, retrieval, financials, latency_ms, cost_usd, index`; `retrieval` has `hit@3, hit@8, mrr, recall@60, v1_hit@3`.

- [ ] **Step 2: Run** `python -m pytest tests/test_eval_answers.py -q` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `eval_answers.py`. `main()` order: parse args → `check_flags(settings)` → `settings.CACHE_ENABLED = False` before importing `main` **and** set `main.response_cache._enabled = False` after import → load corpus exactly as `main.lifespan` (OpenAIClient, `load_global_corpus`, `CorpusRouter`; skip Mongo, multi-query, parser, prewarm) and assign `main.pipeline/corpus_manager/corpus_router`, `main.llm_client = RecordingClient(real)` → loop cases (print one line per case like `eval_retrieval`) → retrieval scoring → `score_rows` → write report → unless `--no-metrics`, write `frontend/public/metrics.json` (`indent=2`).

- [ ] **Step 4: Run** `python -m pytest tests/test_eval_answers.py tests/test_answer_scoring.py -q` — Expected: all passed. `ruff check .` clean.

- [ ] **Step 5: Live smoke (costs ~1¢)**: `PYTHONUTF8=1 python -m tests.eval_answers --label smoke --limit 3 --no-metrics` — Expected: 3 case lines, a report path printed, report rows each `status: ok` with ≥1 claim, tokens > 0. Delete the smoke report afterwards (not committed).

- [ ] **Step 6: Commit** `git add backend/tests/eval_answers.py backend/tests/test_eval_answers.py && git commit -m "feat(eval): answer eval runner with LLM judge, writes metrics.json"`

### Task 3: Golden set v2 (60 new verified cases)

**Files:**
- Modify: `backend/tests/golden_set.json` (append cases, `version: 2`, changelog line)
- Modify: `backend/tests/test_golden_set.py`
- Modify: `backend/tests/eval_retrieval.py:~115` (skip cases with empty `answer_pages`)

**Interfaces:**
- Produces: v2 set consumed by Task 2's runner and Task 4.

- [ ] **Step 1: Update tests first** in `test_golden_set.py`:
  - `test_schema`: version == 2; kind in the four kinds; `answer_pages` non-empty for table/narrative, may be `[]` for numeric/refusal; ids unique.
  - `test_v1_unchanged`: the first 40 cases' ids equal the v1 id list (hard-code the 40 ids from the current file) and every one keeps `checked_by == ["claude","user","claude-recheck"]`.
  - `test_coverage`: 95 ≤ n ≤ 105; companies ≥ 45; years ⊇ {2023, 2024, 2025, 2026}; ≥ 12 cases with year 2026; ≥ 6 numeric; ≥ 4 refusal; table share of table+narrative in [0.4, 0.6].
  - `test_fully_checked`: new cases' `checked_by` ⊇ `["claude","claude-recheck"]`; at least 10 new cases include `"user"` (this fails until the spot-check in Step 5 — expected).
  - `test_pages_exist` unchanged (skips cases with `[]`).
- [ ] **Step 2: Run** `python -m pytest tests/test_golden_set.py -q` — Expected: FAIL (version 1, coverage).
- [ ] **Step 3: Draft and verify 60 cases.** Ruling to record: design said 29 uncovered companies / ≥ 45 companies; actual corpus has 47 companies with reports (KWIL has none, `quarterly/` is not a company) and 27 uncovered — every one of the 27 gets ≥ 1 case. For each table/narrative case: open `data/<SYM>/<year>.pdf` with `fitz`, find the figure/fact, record every page it appears on (the scorer counts any), copy the answer as printed. Recheck pass: re-extract each recorded page's text and assert the key answer's digits/key phrase occur on at least one recorded page (script in scratchpad, not committed). Numeric cases: value from `index_cache/financials.duckdb` cross-checked against its source page or iXBRL file. Refusal cases: a plausible question about a listed company whose answer is absent — confirm by full-text search of that company's PDFs for the key terms (0 hits).
- [ ] **Step 4: Run** `python -m pytest tests/test_golden_set.py -q` — Expected: only `test_fully_checked` fails (no `"user"` yet). `python -m tests.eval_retrieval --label v2-check` — Expected: runs all page cases; the v1 subset must show hit@3 0.800 (compute from the report rows for the first 40 ids). Delete that report if v1 subset matches (Task 4 writes the real one).
- [ ] **Step 5: HARD STOP — user spot-check.** Pick 10 new cases spread over kinds and companies; give the user, per case: question, key answer, PDF path + page (or duckdb/iXBRL source). Wait. Fix any error; if any error is found, recheck every case of that kind. Add `"user"` to the 10 checked cases.
- [ ] **Step 6: Run** `python -m pytest -q` (whole backend suite) — Expected: all passed (7 skipped as before or more for data-less checks). `ruff check .` clean.
- [ ] **Step 7: Commit** `git add backend/tests/golden_set.json backend/tests/test_golden_set.py backend/tests/eval_retrieval.py && git commit -m "test(eval): golden set v2 — 100 cases, 47 companies, FY2026, numeric and refusal kinds"`

### Task 4: Baseline run, metrics.json, results doc

**Files:**
- Create: `frontend/public/metrics.json`, `backend/tests/eval_reports/<ts>-v2-baseline-answers.json`
- Modify: `backend/tests/eval_reports/README.md` (new "Answer eval results" section)
- Modify: `backend/tests/answer_scoring.py` price constants only if the pricing page differs (update the date comment either way)

- [ ] **Step 1:** Check gpt-4o-mini prices on openai.com/api/pricing; update constants + date comment.
- [ ] **Step 2: Run** `PYTHONUTF8=1 python -m tests.eval_answers --label v2-baseline` — Expected: 100 case lines, `errors` 0 (rerun individual failures with `--only` if transient), `v1_hit@3` 0.800, metrics.json written.
- [ ] **Step 3:** Read the 10 lowest-faithfulness rows in the report; for each, check by eye whether the judge was right. If the judge is wrong on ≥ 3, revise `JUDGE_PROMPT` and rerun (record as a ruling); never edit the answers or the key to raise scores.
- [ ] **Step 4:** README section: set (v2, counts by kind), scorer command, judge method (claim split → supported against the context; RAGAS-style faithfulness), formulas from Task 1, a results table with one row (`v2-baseline`: faithfulness, correctness, citation validity, cited share, refusal accuracy, upload-card rate, hit@3/hit@8, p50/p95, $/question), and the judge-spot-check finding from Step 3.
- [ ] **Step 5: Run** `python -m pytest -q` and `ruff check .` — Expected: green. `cd ../frontend && npm run lint && npm run build` — Expected: pass (metrics.json is static, copied to dist).
- [ ] **Step 6: Commit** `git add frontend/public/metrics.json backend/tests/eval_reports backend/tests/answer_scoring.py && git commit -m "eval: v2 baseline — answer faithfulness/correctness, metrics.json"`
