# Phase 2 Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure retrieval against a hand-checked golden set, then improve it in two measured steps: structure-aware chunking + bge embeddings (FAISS kept), then LanceDB storage.

**Architecture:** A retrieval-only scorer reuses the app's real global path (`retrieve_context` → `refine_results`), extracted from `main.answer_question`. Step 1 replaces the chunker with a new `core/pdf_chunker.py` behind the existing `prepare_document` seam, so batch ingest and `/upload` both get it. Step 2 puts vectors, text, metadata and full-text search into one LanceDB table behind a `ChunkStore` class and deletes FAISS, the pickles and `rank_bm25`.

**Tech Stack:** Python 3.13, PyMuPDF 1.26.7 (`find_tables`, `get_text("dict")`), sentence-transformers, `BAAI/bge-base-en-v1.5`, FAISS (Step 1 only), LanceDB ≥0.41 (Step 2), pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-retrieval-quality-design.md`

## Global Constraints

- All work on branch `phase-2-retrieval`; commit per task there. The user merges and pushes `main` themselves.
- Run tests from `backend/` with `venv/Scripts/python -m pytest tests/<file> -q`. Never collect `tests/quick_test.py` (needs a live server). Current baseline: 108 passed across `test_security, test_corpus_router, test_execute_plan, test_persistence, test_auth, test_query_understanding`.
- Frozen for all eval runs: `RETRIEVAL_K=60`, `FINAL_K=8`, `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`, `RERANKER_MAX_CANDIDATES=30`. The scorer forces `MULTI_QUERY_ENABLED=false`, `INTELLIGENT_PARSING_ENABLED=false`.
- `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`, `QUERY_INSTRUCTION="Represent this sentence for searching relevant passages: "`; documents embedded with no instruction.
- `CHUNK_SIZE` target 900 chars, hard max 1,500. `section_hint` truncated to 120 chars.
- CUDA torch is a local-only install. `requirements.txt` and `backend/Dockerfile` stay CPU-only.
- Golden set is frozen once Task 3 ends. Edits after that only fix a verified mistake and add a line to its `changelog`.
- `backend/.env` holds secrets: change only the keys named in a task, never print the file.

## Review Focus

1. **Scanned / image-only pages** (no text, no tables) → chunker yields no chunks for that page and does not crash; a fully image-only PDF still raises `ValueError("…no extractable text")` as today. Test in Task 6.
2. **A table that spans a page break** (common in annual reports) → each page's part is its own table chunk with its own header row; no chunk spans two pages. Test in Task 6.
3. **Company symbols with SQL-special characters** (`M&M`, `BAJAJ-AUTO`, an apostrophe in an upload label) in LanceDB `where` clauses → quoted safely, filter still exact. Test in Task 11.
4. **`/upload` of a PDF on the cold-start path** → page numbers correct. Today `index_document` uses the non-page-aware `chunk_text`, so every chunk of the first ingested PDF (and every session upload) gets `page_number=1`. Test in Task 7.
5. **Expanded chunk IDs** (`[expanded]chunk_340`) reaching the scorer or `enrich_context` → parsed back to the right row, not dropped. Test in Task 2 (scorer) and Task 12 (neighbours).

---

## Step 0 — Golden set and baseline

### Task 1: Extract corpus loading and global retrieval from `main.py`

**Files:**
- Create: `backend/core/app_retrieval.py`
- Modify: `backend/main.py` (lifespan block ~`:300-395`, global path in `answer_question` ~`:866-886`)

**Interfaces:**
- Produces:
  - `load_global_corpus(cache_dir: str) -> tuple[RetrieverPipeline, CorpusManager]` — exactly today's lifespan steps 1–4 plus `init_reranker()` and `init_bm25(pipeline.chunks)`; raises the same `RuntimeError`s.
  - `retrieve_global(question: str, pipeline, corpus_manager, top_k: int, final_k: int) -> tuple[list[RetrievalResult], list[RetrievalResult], ParsedQuery]` — returns `(candidates, final, parsed)`, where `candidates` is `retrieve_context`'s merged list and `final` is `refine_results(...)` on it.

- [ ] **Step 1:** Move the code. `main.py` lifespan calls `load_global_corpus`; the global branch of `answer_question` calls `retrieve_global` under one `tracker.track("retrieval")` (that branch loses its separate `reranking` timing key). At the end of `load_global_corpus`, log `psutil.Process().memory_info().rss` in MB (add `psutil` to `requirements.txt`).
- [ ] **Step 2:** Run the six test files. Expected: 108 passed.
- [ ] **Step 3:** Commit `refactor: extract load_global_corpus/retrieve_global for reuse by the scorer`.

### Task 2: Retrieval scorer

**Files:**
- Create: `backend/tests/eval_retrieval.py`, `backend/tests/test_eval_scoring.py`
- Modify: `backend/.gitignore` (nothing — `tests/eval_reports/` is committed)

**Interfaces:**
- Consumes: Task 1 `load_global_corpus`, `retrieve_global`.
- Produces:
  - `chunk_location(chunk_id: str, chunk_metadata: dict) -> tuple[str, str, int] | None` — `(company, year, page_number)`; strips `[expanded]` and parses `chunk_<vid>`.
  - `score_case(case: dict, candidates: list, final: list, chunk_metadata: dict) -> dict` with keys `id, kind, hit3, hit8, rr, recall60` (bools, `rr` float, 0.0 when no hit).
  - `summarize(rows: list[dict], latencies_ms: list[float]) -> dict` with `overall`, `by_kind` (each: `n, hit3, hit8, mrr, recall60` as fractions), `latency_ms: {p50, p95}`.
  - CLI: `python -m tests.eval_retrieval --label <name> [--cache index_cache] [--set tests/golden_set.json]` → prints a table and writes `tests/eval_reports/<YYYYMMDD-HHMM>-<label>.json` containing `summary`, per-case `rows`, `rss_mb` after corpus load, and a `settings` snapshot (embedding model, the frozen keys, both thresholds).

- [ ] **Step 1: Write failing tests** in `test_eval_scoring.py` with hand-built `RetrievalResult`s and a dict of `ChunkMetadata` stand-ins (`SimpleNamespace(company=…, year=…, page_number=…)`):
  - `test_hit_requires_company_year_and_page` — right page wrong year → no hit.
  - `test_hit3_vs_hit8` — correct chunk at rank 5 → `hit3 False, hit8 True, rr == 0.2`.
  - `test_expanded_chunk_id_is_scored` — `"[expanded]chunk_7"` resolves to vid 7.
  - `test_recall60_uses_candidates_not_final` — correct chunk only in `candidates` → `recall60 True, hit8 False`.
  - `test_summarize_splits_by_kind_and_reports_p95`.
- [ ] **Step 2:** Run `pytest tests/test_eval_scoring.py -q`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement. The CLI sets `settings.MULTI_QUERY_ENABLED = False` and `settings.INTELLIGENT_PARSING_ENABLED = False` before `load_global_corpus`, sets `settings.INDEX_CACHE_DIR` from `--cache`, and times each `retrieve_global` call. It does not construct `OpenAIClient`.
- [ ] **Step 4:** Run again. Expected: 5 passed.
- [ ] **Step 5:** Commit `test: retrieval scorer (hit@3/hit@8/MRR/recall@60)`.

### Task 3: Draft, check and freeze the golden set

**Files:**
- Create: `backend/tests/golden_set.json`, `backend/tests/test_golden_set.py`

**Interfaces:**
- Produces: `golden_set.json` = `{"version": 1, "changelog": [], "cases": [ … ]}`; each case exactly the spec's fields: `id, question, company, year, answer_pages (list[int], 1-based PDF index), answer, kind ("table"|"narrative"), checked_by (list)`.

- [ ] **Step 1: Write the validator test** `test_golden_set.py`:
  - `test_schema` — every case has the fields above with the right types; ids unique.
  - `test_pages_exist` — each `answer_pages` entry ≤ page count of `data/<company>/<year>.pdf` (skip if `data/` missing).
  - `test_coverage` — 38 ≤ cases ≤ 45; ≥15 distinct companies; years ⊇ {2023, 2024, 2025}; table share between 0.4 and 0.6.
  - `test_fully_checked` — every `checked_by == ["claude", "user", "claude-recheck"]`. (Fails until Step 4; that's the gate.)
- [ ] **Step 2: Draft.** Read pages with a throwaway script in the scratchpad (`fitz` page text dump + keyword search), pick answers by reading the PDF pages, never by running retrieval. Write cases with `checked_by: ["claude"]`. Run `pytest tests/test_golden_set.py -q`. Expected: all pass except `test_fully_checked`.
- [ ] **Step 3: User check.** Stop and hand the file to the user with a page-by-page list (`id · question · company/year · pages · answer`). Apply their fixes; append `"user"`.
- [ ] **Step 4: Re-check.** Re-open each cited page and confirm the answer is on it; fix or drop (keep ≥38); append `"claude-recheck"`. Run the validator. Expected: all pass.
- [ ] **Step 5:** Commit `test: golden retrieval set v1 (frozen)`.

### Task 4: Baseline run and threshold calibration data

**Files:**
- Create: `backend/tests/calibration_queries.json` (the 4 `main.SHOWCASE_QUESTIONS` + 20 new queries, none overlapping the golden set, ≥8 naming a company and year), `backend/tests/calibrate_thresholds.py`, `backend/tests/eval_reports/*-baseline.json`

**Interfaces:**
- Produces: `calibrate_thresholds.py --cache <dir> [--from-report <calibration json>]`. Without `--from-report`: for every calibration query, records all dense scores before the `SIMILARITY_THRESHOLD` filter (call `corpus_manager.retriever.search_scoped` path via a `threshold=-1` override; simplest is to temporarily set `settings.SIMILARITY_THRESHOLD = -1.0`) and the top score `refine_results` would compare to `SKIP_RERANKER_THRESHOLD`; writes `tests/eval_reports/<ts>-calibration-<model>.json` with the two score arrays and the percentile rank of the current threshold values in each. With `--from-report <MiniLM report>`: prints the score at the same percentiles under the current model — the recalibrated values.

- [ ] **Step 1:** `python -m tests.eval_retrieval --label baseline`. Expected: report written; record hit@3/hit@8/MRR/recall@60 overall and by kind.
- [ ] **Step 2:** `python -m tests.calibrate_thresholds --cache index_cache`. Expected: calibration report for `all-MiniLM-L6-v2` with two percentile ranks.
- [ ] **Step 3:** Commit both reports + scripts `test: baseline eval + MiniLM threshold calibration`.

---

## Step 1 — Chunker + bge (FAISS kept)

### Task 5: Line-preserving normalisation

**Files:**
- Modify: `backend/core/retriever_pipeline.py:50` (`NORMALIZATION_VERSION = "2"`), `:116-147` (`normalize_text`)
- Create: `backend/tests/test_chunker.py`

- [ ] **Step 1: Failing tests** in `test_chunker.py`:
  - `test_normalize_keeps_single_newlines` — `"a  b\nc"` → `"a b\nc"`.
  - `test_normalize_collapses_3plus_newlines` — `"a\n\n\n\nb"` → `"a\n\nb"`.
  - `test_normalize_strips_nonprintable_and_trailing_space_per_line` — `"x\x00y \t\nz"` → `"xy\nz"`.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement: NFC, drop non-printables except `\n`/`\t`/space, collapse `[ \t]+` → `" "`, strip each line, `\n{3,}` → `"\n\n"`, strip.
- [ ] **Step 4:** Run `test_chunker.py` + the six files. Expected: pass (the cache fingerprint now differs; that's intended).
- [ ] **Step 5:** Commit `feat(ingest): keep line structure in normalize_text`.

### Task 6: `core/pdf_chunker.py`

**Files:**
- Create: `backend/core/pdf_chunker.py`; tests in `backend/tests/test_chunker.py`; a fixture builder `backend/tests/pdf_fixtures.py`
- Modify: `backend/core/retriever_pipeline.py` `Chunk` dataclass: add `heading: str = ""`, `content_form: str = "narrative"`

**Interfaces:**
- Produces:
  - `chunk_pdf(pdf_path: str, target: int = settings.CHUNK_SIZE, hard_max: int = 1500) -> list[Chunk]` — `chunk_id` = `chunk_<i>` in document order; `text` already prefixed with `heading + "\n"` when a heading is known; `page_number` exact; `content_form` `"tabular"` or `"narrative"`.
  - `pdf_fixtures.make_pdf(path, pages: list[list[tuple]])` — each item `("heading", text)`, `("para", text)` or `("table", rows: list[list[str]])` (draws ruled grid lines so `find_tables()` detects it). Heading = 16pt bold, body = 10pt.

- [ ] **Step 1: Failing tests** (all using `make_pdf` in `tmp_path`):
  - `test_table_becomes_markdown_with_header` — a 3-col table → one chunk, `content_form == "tabular"`, contains `"| Particulars |"` and the FY24 and FY23 values in the same row line.
  - `test_table_numbers_not_repeated_in_prose` — a number unique to the table appears in exactly one chunk.
  - `test_long_table_splits_on_rows_and_repeats_header` — 80 rows → ≥2 chunks, each starts (after the heading line) with the header row, none cuts a row, each ≤ 1500 chars.
  - `test_table_across_page_break` — table continuing on page 2 → separate chunks with `page_number` 1 and 2, both with a header row.
  - `test_prose_splits_on_sentences_with_one_sentence_overlap` — 3 kB of numbered sentences → no chunk starts or ends mid-word; chunk *n+1* begins with the last sentence of chunk *n*.
  - `test_overlong_sentence_split_at_word_boundary` — one 4,000-char sentence → every chunk ≤ 1500, none mid-word.
  - `test_heading_prefix_and_carry_over` — heading on page 1, prose on pages 1–2 → every chunk starts `"Segment Revenue\n"`; a new heading on page 2 switches it.
  - `test_chunk_never_spans_pages`.
  - `test_blank_page_yields_no_chunks_and_keeps_numbering` — pages [text, blank, text] → chunks only on pages 1 and 3.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3: Implement.** Per page: `tables = page.find_tables().tables`; table text = `t.to_markdown()`; prose = text blocks from `page.get_text("dict")` whose bbox does not intersect any table bbox, each block run through `normalize_text`. A span is a heading when its size ≥ 1.25 × the page's median body span size, or it is bold and ≤ 120 chars on its own line — builder may tune thresholds against real reports. Order tables and prose blocks by bbox top `y0`. Pack prose blocks → paragraphs → sentences (`re.split(r"(?<=[.!?])\s+", …)`) up to `target`, words as last resort to respect `hard_max`. Tables: header = first markdown row + separator row; pack body rows under it up to `target`.
- [ ] **Step 4:** Run `test_chunker.py`. Expected: all pass.
- [ ] **Step 5:** Spot-check on a real report: `python -c "from core.pdf_chunker import chunk_pdf; …"` on `data/HDFCBANK/2024.pdf` — print 5 random `tabular` chunks; rows readable with headers. Print total time; if > 60 s for one PDF, note it for Task 8's multiprocessing.
- [ ] **Step 6:** Commit `feat(ingest): structure-aware PDF chunker with tables and headings`.

### Task 7: Wire the chunker into ingestion and metadata

**Files:**
- Modify: `backend/core/retriever_pipeline.py` (`prepare_document` `:514`, `index_document` `:357`, `append_vectors` `:605`, `CODE_VERSION`), `backend/core/corpus_manager.py:183-238`
- Test: `backend/tests/test_chunker.py`

**Interfaces:**
- Consumes: Task 6 `chunk_pdf`.
- Produces: `RetrieverPipeline.prepare_document(pdf_path) -> list[Chunk]`; `append_vectors(embeddings, chunks: list[Chunk])`; `index_document` builds through `prepare_document` (fixes all-page-1 on cold start). `CorpusManager.add_document` sets `metadata.section_hint = chunk.heading[:120] or None` and `metadata.content_form = chunk.content_form`.

- [ ] **Step 1: Failing tests:**
  - `test_cold_start_add_document_has_real_page_numbers` — fresh `CorpusManager(RetrieverPipeline())` + 3-page fixture → metadata page numbers include 1, 2 and 3.
  - `test_metadata_gets_heading_and_content_form` — a table chunk's metadata has `content_form == "tabular"`, `section_hint` equal to the fixture heading.
  - `test_append_path_matches_cold_start_path` — same PDF added via cold start and via append → identical texts and page numbers.
- [ ] **Step 2:** Run; FAIL.
- [ ] **Step 3:** Implement; delete `chunk_text`, `chunk_text_from_pages`, `load_pdf` once nothing imports them. Bump `CODE_VERSION`.
- [ ] **Step 4:** Run `test_chunker.py` + the six files. Expected: all pass (update any test that called the deleted functions to use `chunk_pdf`).
- [ ] **Step 5:** Commit `feat(ingest): route all ingestion through chunk_pdf; fix page 1 on cold start`.

### Task 8: bge embeddings, GPU ingestion, re-index

**Files:**
- Modify: `backend/config.py` (`EMBEDDING_MODEL`, `QUERY_INSTRUCTION` defaults), `backend/.env.example`, `backend/Dockerfile` (`ARG EMBEDDING_MODEL`), `backend/.env` (those two keys only), `backend/ingestion/batch_ingest_annual_reports.py`, `backend/.gitignore` (`index_cache_baseline/`), `README.md` (one "Re-indexing locally on a GPU" paragraph)

- [ ] **Step 1:** Install CUDA torch into the local venv: `venv/Scripts/pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128`. Verify: `venv/Scripts/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` → `True NVIDIA GeForce RTX 3050 Laptop GPU`.
- [ ] **Step 2:** In the batch script, after creating the pipeline: if CUDA is available, `pipeline.model.half()` and log the device; embed with `batch_size=64`. If chunking is the bottleneck (Task 6 timing), chunk PDFs in a `ProcessPoolExecutor` and embed/append in the main process in the existing sorted order so vector ranges stay deterministic.
- [ ] **Step 3:** Set the config/`.env`/Dockerfile values from Global Constraints.
- [ ] **Step 4:** `mv index_cache index_cache_baseline`, then `venv/Scripts/python -m ingestion.batch_ingest_annual_reports`. Expected: 139 documents indexed, `index_manifest.json` shows `embedding_model: BAAI/bge-base-en-v1.5`, `embedding_dim: 768`. Record wall time and chunk count.
- [ ] **Step 5:** Run the six test files + `test_chunker.py`. Expected: pass.
- [ ] **Step 6:** Commit `feat(embed): bge-base-en-v1.5 with query instruction; GPU re-index`.

### Task 9: Step 1 evaluation (frozen vs recalibrated)

**Files:**
- Create: `backend/tests/eval_reports/*-step1-frozen.json`, `*-calibration-bge.json`, `*-step1-recal.json`
- Modify: `backend/config.py`, `backend/.env.example`, `backend/.env` — only if recalibrated wins

- [ ] **Step 1:** `python -m tests.eval_retrieval --label step1-frozen`.
- [ ] **Step 2:** `python -m tests.calibrate_thresholds --cache index_cache --from-report tests/eval_reports/<MiniLM calibration>.json` → new `SIMILARITY_THRESHOLD` / `SKIP_RERANKER_THRESHOLD`.
- [ ] **Step 3:** Set them in `.env`, run `--label step1-recal`.
- [ ] **Step 4:** Ship the better of the two by hit@8, then hit@3 as tie-break; write both into a short `tests/eval_reports/README.md` table (baseline / frozen / recal) with how the recalibrated values were derived. Expected: hit@3 and hit@8 beat baseline overall and on `table`. If not, stop and report to the user before Step 2 — do not tune against the golden set.
- [ ] **Step 5:** Manual `/upload` check: start the backend, upload `data/TCS/2024.pdf` as a session, ask one table question; cited page opens on the right page.
- [ ] **Step 6:** Commit `eval: Step 1 results (chunker + bge)`.

---

## Step 2 — LanceDB

### Task 10: Dependency + store skeleton

**Files:**
- Modify: `backend/requirements.txt` (add `lancedb>=0.41`, `pyarrow`)
- Create: `backend/core/chunk_store.py`, `backend/tests/test_chunk_store.py`

**Interfaces:**
- Produces `class ChunkStore`:
  - `ChunkStore(path: str, dim: int)` — opens or creates table `chunks` in `lancedb.connect(path)`.
  - `add(chunks: list[Chunk], metas: list[ChunkMetadata], vectors: np.ndarray) -> None` — columns: `vector`, `text`, all `ChunkMetadata` fields, `chunk_seq` (index within its document).
  - `count() -> int`
  - `build_text_index() -> None` — `table.create_fts_index("text", replace=True)` (native, not tantivy).
  - `search_dense(vector: np.ndarray, k: int, where: str | None) -> list[tuple[float, dict]]` — `.search(vector).distance_type("cosine").where(where, prefilter=True).limit(k)`; score = `1 - _distance`.
  - `search_text(query: str, k: int, where: str | None) -> list[tuple[float, dict]]` — `.search(query, query_type="fts").where(where, prefilter=True).limit(k)`; score = `_score`.
  - `neighbors(document_label: str, chunk_seq: int, window: int) -> list[dict]` ordered by `chunk_seq`.
  - `get(vector_id: int) -> dict | None`

- [ ] **Step 1: Failing tests** with 4-dim vectors in `tmp_path`: `test_add_and_count`, `test_dense_prefilter_only_returns_scope` (two companies; filter one; k larger than its rows → only its rows), `test_text_search_finds_exact_term` (`"CASA"`), `test_neighbors_stay_in_document`, `test_reopen_persists`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** pass. **Step 5:** commit `feat(store): LanceDB ChunkStore`.

### Task 11: Scope → `where` clause

**Files:**
- Modify: `backend/core/chunk_store.py`; tests in `test_chunk_store.py`

**Interfaces:**
- Produces: `scope_to_where(scope: RetrievalScope) -> str` — `is_active = true` AND optional `company IN (…)`, `year IN (…)`, `document_type IN (…)` from the scope's fields (read `core/lookup_index.py:79-105` for them); string literals single-quoted with `'` doubled.

- [ ] **Step 1: Failing tests:** `test_where_quotes_special_symbols` (`M&M`, `BAJAJ-AUTO`, `O'Brien_upload`) — each used with `search_dense` returns exactly that company's rows; `test_where_empty_scope_is_active_only`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** commit `feat(store): scope filters as SQL where clauses`.

### Task 12: CorpusManager and refiner on ChunkStore

**Files:**
- Modify: `backend/core/corpus_manager.py` (`add_document`, `search`, `execute_plan`, registry load/save, `validate_cache_integrity`), `backend/core/result_refiner.py:210-297`, `backend/core/retrieval_pipeline_v2.py` (pass the store instead of `all_chunks/chunk_metadata`), `backend/core/app_retrieval.py`
- Test: update `test_corpus_router.py`, `test_execute_plan.py`, `test_persistence.py`; add to `test_chunk_store.py`

**Interfaces:**
- Consumes: Tasks 10–11.
- Produces: `CorpusManager(retriever, store: ChunkStore)`; `search(scope, query_vector)` uses `store.search_dense(vec, RETRIEVAL_K, scope_to_where(scope))`, keeps the `SIMILARITY_THRESHOLD` filter and returns the same `RetrievalResult` shape with `chunk_id = f"chunk_{vector_id}"`. `vector_id` stays a global row sequence (keeps citations and the scorer working). `enrich_context(results, store, window=None)` uses `store.neighbors`.
- Keep `document_registry.json` (document list, pdf paths for `pdf_url`). Whether `LookupIndex` survives is the builder's call: delete it if nothing but range resolution uses it.

- [ ] **Step 1: Failing test** `test_enrich_uses_chunk_seq_and_expanded_ids` — `[expanded]chunk_3` resolves; neighbours never cross `document_label`.
- [ ] **Step 2:** Port; fix the three existing test files to build a `ChunkStore` in `tmp_path` instead of FAISS ranges.
- [ ] **Step 3:** Run all test files. Expected: pass.
- [ ] **Step 4:** Commit `refactor(store): CorpusManager + context window on LanceDB`.

### Task 13: Keyword search on LanceDB FTS

**Files:**
- Modify: `backend/query/query_orchestrator.py` (`:45`, `:120-140`, `:166-213`, `:365-380`), `backend/core/app_retrieval.py`, `backend/main.py` (startup BM25 lines)
- Delete: `backend/core/bm25_retriever.py`; `rank-bm25` from `requirements.txt`

- [ ] **Step 1:** Failing test in `test_chunk_store.py`: `test_orchestrator_keyword_hits_respect_scope` — `retrieve_context` on a two-company store with a scoped query returns no keyword hit from the other company.
- [ ] **Step 2:** Replace `bm25_search` calls with `corpus_manager.store.search_text(variant, RETRIEVAL_K, where)` (where = OR of each sub-query's `scope_to_where`); keep `merge_results` unchanged.
- [ ] **Step 3:** All tests pass. **Step 4:** commit `refactor(search): LanceDB full-text search replaces rank_bm25`.

### Task 14: Remove FAISS, pickles; sessions on temp stores

**Files:**
- Modify: `backend/core/retriever_pipeline.py` (drop `faiss`, `index`, `chunks`, `save_index`/`load_index`, `search_scoped`, `_ChunkUnpickler`, `_cross_env_unpickle`; keep model loading, `prepare_document`, `embed_texts`, `embed_query`), `backend/main.py:619` (session corpora), session eviction code, `backend/ingestion/batch_ingest_annual_reports.py`, `backend/ingestion/ingest.py`, `backend/tests/evaluation.py`, `backend/core/app_retrieval.py`, `backend/asset_manager.py` if it lists cache files, `requirements.txt` (drop `faiss-cpu`), `backend/Dockerfile` only if it references removed files
- Test: `test_security.py` session tests

**Interfaces:**
- Session corpus = `CorpusManager(pipeline, ChunkStore(tempfile.mkdtemp(prefix="cognifin-session-"), dim))`; eviction (LRU and TTL) calls `shutil.rmtree` on that dir.
- Batch ingest writes `index_cache/lancedb/` + registry, then `store.build_text_index()`.

- [ ] **Step 1: Failing test** `test_session_store_dir_removed_on_eviction` (set `SESSION_MAX=1`, create two sessions → first dir gone).
- [ ] **Step 2:** Implement; `grep -rn "faiss\|pickle\|bm25" backend --include=*.py` (excluding venv) returns nothing outside comments.
- [ ] **Step 3:** All tests pass. **Step 4:** commit `refactor: drop FAISS and pickles; session corpora on temp LanceDB`.

### Task 15: Re-index into LanceDB and Step 2 evaluation

**Files:**
- Create: `backend/tests/eval_reports/*-step2.json`; update `tests/eval_reports/README.md`, `ROADMAP.md` Phase 2 section (local file)

- [ ] **Step 1:** Re-index from `backend/data/` with the batch script (GPU). Expected: same chunk count as Task 8.
- [ ] **Step 2:** `python -m tests.eval_retrieval --label step2`. Expected: hit@3 and hit@8 within ±1 case of the shipped Step 1 run.
- [ ] **Step 3:** Compare `rss_mb` and `latency_ms.p95` between the shipped Step 1 report and the Step 2 report. Expected: both lower in Step 2. Add both to the README table.
- [ ] **Step 4:** Manual `/upload` check as in Task 9 Step 5.
- [ ] **Step 5:** Delete `index_cache_baseline/` after the user confirms. Commit `eval: Step 2 results (LanceDB)`.
