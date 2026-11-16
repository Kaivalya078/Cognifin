# Phase 2 — Retrieval quality: design

Date: 2026-11-16 · Status: draft for review

## Intent

Cognifin answers questions over 139 NIFTY-50 annual reports (47 symbols × FY2023–25,
`backend/data/<SYMBOL>/<YEAR>.pdf`, ~264k chunks today). Answer quality is capped by
indexing, not by the retriever: `normalize_text` (`core/retriever_pipeline.py:116`)
collapses every newline, PyMuPDF's default `get_text()` flattens tables, and
`chunk_text` slices blindly every 900 chars. A balance sheet reaches the embedder as
`Revenue 231456 198234 Other income 5432 …` with no way to tell FY24 from FY23.
Annual reports are roughly half tables.

Why it matters: the project is a portfolio centrepiece. It must give correct answers to
table questions, and every claimed improvement must be backed by a number that holds up
in an interview. Deployment is deliberately deferred until Phases 2–6 are done.

## Goals

1. A frozen, hand-checked **golden question set** and a retrieval scorer, with a
   baseline recorded on the *current* index before anything changes.
2. **Step 1 — better chunks + better embeddings**, still stored in FAISS + pickles.
   Measured against the baseline.
3. **Step 2 — storage moves to LanceDB** (vectors + full-text + metadata filters in one
   disk-backed store). Measured to show quality holds while RAM and search latency drop.

## Non-goals

- Phase 3+ work: XBRL, DuckDB, numeric router, charts, new companies.
- Deployment, Docker changes beyond what the new deps require, rebuilding the R2 index
  tarball (that happens when we deploy).
- Changing the LLM prompts, the reranker model, or the answer-generation step.
- A ~100-case golden set with faithfulness scoring (Phase 5 extends this one).

## Anti-goals (would be a failure even if it "works")

- **Grading our own homework.** Answer pages are found by reading the PDFs, never by
  looking at what the retriever returns. The set is frozen before Step 1 starts; no
  question is added, dropped, or edited after seeing new scores, except to fix a
  verified mistake in the set (logged in the file's changelog).
- Session uploads (`/upload`) breaking or getting worse — they share the chunker.
- Citations pointing at the wrong page ("Open PDF" must still land on the cited page).
- An unmeasured change: each step ships with before/after numbers in the eval report.

## Constraints

- Dev machine: RTX 3050 Laptop GPU (4 GB VRAM), 12 cores, 24 GB RAM, Windows.
  The venv has CPU torch (`2.10.0+cpu`); a CUDA build is installed **locally only** for
  ingestion. `requirements.txt` and the Dockerfile stay CPU-only.
- Server target (later): 2 OCPU / 12 GB ARM, CPU-only. Query-time embedding with
  bge-base on CPU must stay well under the 5 s answer budget.
- PyMuPDF 1.26.7 is installed; `page.find_tables()` and `Table.to_markdown()` are
  available. No new PDF library.
- Re-indexing must be one command and reproducible from `backend/data/` (no Colab-only
  artefacts).

## Approaches considered

- **A. All at once** — new chunker, bge, and LanceDB in one change. Fewest steps, but a
  score change can't be attributed, and storage bugs look like quality regressions.
- **B. Two measured steps (chosen)** — chunker + bge on the existing FAISS stack first,
  then the LanceDB swap. Costs one extra re-index (~15 min on the GPU) and buys a
  separate number for each change.
- **C. Skip LanceDB** — least work, but keeps the 250 MB pickle in RAM, the full
  264k-doc BM25 scan, and the Colab unpickler hack.

User picked **B** on 2026-11-16.

## Step 0 — Golden set and scorer

**File:** `backend/tests/golden_set.json` — a list of cases:

```json
{
  "id": "hdfcbank-2024-nii",
  "question": "What was HDFC Bank's net interest income in FY2024?",
  "company": "HDFCBANK",
  "year": "2024",
  "answer_pages": [112, 113],
  "answer": "₹1,08,532 crore",
  "kind": "table",
  "checked_by": ["claude", "user"]
}
```

- ~40 cases. Mix: about half `table` (figures from statements, notes,
  segment tables), the rest `narrative` (strategy, risks, governance, ESG). Spread over
  at least 15 companies and all three years. *(Claude's call)* Every case is one
  company + one year; comparison questions are left to Phase 4, where they're answered
  from structured data anyway. This keeps `answer_pages` a flat list and the hit rule
  unambiguous.
- `answer_pages` are 1-based PDF page indices (what `page_number` stores), not the
  printed page numbers.
- Process (decided): Claude drafts the cases by reading the PDFs → the user checks them
  → Claude re-checks each against the PDF before the baseline run. `checked_by` records
  this.

**Scorer:** `backend/tests/eval_retrieval.py`. It runs each question through the real
retrieval path (query understanding → plan → hybrid search → rerank → refine), without
the LLM, and reports:

- **hit@3 / hit@8** — scored on the final list the LLM receives (`FINAL_K=8`, so
  hit@8 = "the answer reached the LLM at all"). A case is a hit if any chunk in the
  top k is from the right company + year and on one of `answer_pages`. *(Claude's
  call: score what users get, not a pre-trim list.)*
- **MRR** over the first correct chunk in that list
- also **recall@60** on the merged candidate list before reranking, to tell
  "never retrieved" apart from "retrieved but ranked out"
- split by `kind`, plus p50/p95 retrieval latency
- writes a JSON report to `backend/tests/eval_reports/<timestamp>.json`; the reports
  for the baseline, Step 1 and Step 2 are committed.

It runs with the app's real `.env` settings, so the score reflects what users get.
The scorer **forces** `MULTI_QUERY_ENABLED=false` and
`INTELLIGENT_PARSING_ENABLED=false` (both already false in `.env`) so no LLM call
runs and results are deterministic. The existing `tests/evaluation.py` (isolation
checks) stays as is.

**Frozen settings for all three runs** (current `.env`): `RETRIEVAL_K=60`,
`FINAL_K=8`, reranker `cross-encoder/ms-marco-MiniLM-L-6-v2` with
`RERANKER_MAX_CANDIDATES=30`. The uncommitted reranker switch is committed **before**
the baseline run so baseline and later steps use the same reranker.

## Score thresholds and the embedder change

`SIMILARITY_THRESHOLD=0.30` (dense cosine filter, `corpus_manager.py:353`) and
`SKIP_RERANKER_THRESHOLD=0.85` were tuned for MiniLM. bge-base cosine scores sit
higher and closer together, so unchanged they would stop filtering and skip the
reranker far more often. *(Claude's call)* Step 1 is reported twice:

1. **Frozen** — thresholds unchanged.
2. **Recalibrated** — each threshold moved to the same *percentile* of scores under
   bge that it sat at under MiniLM, measured on the pre-warmed showcase questions
   and 20 throwaway queries that are **not** in the golden set. No value is picked by
   looking at golden-set scores.

The better of the two becomes the shipped config; the report records both and how the
new values were derived.

## Step 1 — Chunker + embeddings (FAISS kept)

All changes are in the shared path `load_pdf_pages` → `chunk_text_from_pages` →
`prepare_document`, so the batch ingest and `/upload` both pick them up.

1. **Keep line structure.** `normalize_text` keeps newlines: it collapses runs of
   spaces/tabs within a line and runs of 3+ newlines to 2. Unicode NFC and
   non-printable stripping stay.
2. **Tables as tables.** Per page, `page.find_tables()`; each table becomes Markdown via
   `to_markdown()`. The prose for the page is the text *outside* table bounding boxes,
   so numbers aren't indexed twice. Tables and prose blocks keep their reading order on
   the page.
3. **Structure-aware splitting.** Target ~900 chars (`CHUNK_SIZE`), hard max ~1,500.
   - Prose: split on paragraph, then sentence boundaries; never mid-word. Overlap is one
     trailing sentence (replaces the 150-char overlap).
   - Tables: split on row boundaries only; every table chunk repeats the header row(s).
     No overlap.
   - A chunk never spans two pages, so `page_number` stays exact.
4. **Section headings.** Headings are detected from font size/weight in
   `page.get_text("dict")` (spans clearly larger or bolder than the page's body text).
   The current heading carries across pages until the next one. Each chunk's text that
   gets **embedded and indexed** is prefixed `"<heading>\n"`. The text shown to the LLM
   is the same text (the heading helps it too).
5. **Metadata.** Fill the existing `content_form` field: `"tabular"` for table chunks,
   `"narrative"` otherwise. Fill `section_hint` with the heading text, truncated to 120
   chars. No schema change.
6. **Embeddings.** `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5` (768-dim),
   `QUERY_INSTRUCTION="Represent this sentence for searching relevant passages: "`
   (both already staged, commented out, in `.env`). Documents are embedded without the
   instruction. Ingestion uses fp16 on CUDA when available, otherwise CPU.
   Update `config.py` defaults, `.env.example`, and the Dockerfile `EMBEDDING_MODEL` arg
   so they all agree.
7. **Cache invalidation.** The config fingerprint / `code_version` in the manifest must
   change so an old `index_cache/` is rejected rather than silently mixed.
8. **Re-index** with the existing `python -m ingestion.batch_ingest_annual_reports`
   into a fresh `index_cache/`. Keep the old cache as `index_cache_baseline/` (local,
   gitignored) until Step 2 is done.

**Verify:** hit@3 and hit@8, overall and on `table` cases, beat the baseline; `pytest` green;
an `/upload` of one annual report works and cites correct pages; a spot check of 5
random table chunks shows readable Markdown rows with headers.

## Step 2 — LanceDB storage

Replace FAISS + `chunks.pkl` + `chunk_metadata.pkl` + `rank_bm25` with one LanceDB
table on disk (`index_cache/lancedb/`).

- **Table `chunks`:** `vector` (768 floats), `text`, every `ChunkMetadata` field as a
  column, plus `chunk_seq` (order within its document) for neighbour lookup.
- **Dense search:** ANN with the scope as a **pre**-filter (`company IN …`,
  `year IN …`, `document_type`, `is_active = true`). Replaces `search_scoped`, its
  doubling-retry loop, and vector-id range resolution in `lookup_index.resolve_ranges`.
- **Keyword search:** LanceDB's full-text index on `text`, same pre-filter. Replaces
  `core/bm25_retriever.py`. The hybrid merge (`result_merger.py`) keeps its current
  scoring; only its inputs change.
- **Context window:** neighbours are found by `(document_label, chunk_seq ± n)`
  instead of `vector_id ± n` (`result_refiner.py:261`).
- **Deleted:** `faiss.index`, the pickles, `_ChunkUnpickler` / `_cross_env_unpickle`,
  `bm25_retriever.py`, the range logic. `document_registry.json` and the lookup index
  may stay as the list of documents/entities if that is simpler — builder's call.
- **Session uploads:** same code path, using a LanceDB table in a per-session temp
  directory, deleted when the session is evicted (LRU/TTL already exist).
- **Ingestion:** the batch script writes to LanceDB directly; rebuilding from
  `backend/data/` is one command.
- Dependencies: add `lancedb` (and `pyarrow` if not pulled in); remove `faiss-cpu` and
  `rank-bm25` once nothing imports them.

**Verify:** golden-set hit@3/hit@8 within ±1 case of Step 1 (same embeddings and
chunks, so it should match); backend RSS after startup and retrieval p95 both lower
than Step 1, numbers recorded in the eval report; `pytest` green; `/upload` works.

## What's left to the builder

- The exact heading-detection heuristic and its thresholds.
- How prose and table blocks are interleaved within a page.
- Batch size / fp16 details for the GPU run, and whether `find_tables()` needs
  multiprocessing across PDFs to keep ingestion under ~1 hour.
- LanceDB index type and parameters (flat vs IVF-PQ at 264k rows), FTS tokenizer
  settings.
- Whether the registry / lookup index survive Step 2 in a reduced form.
- Test structure for the new chunker (one focused test file is enough).
