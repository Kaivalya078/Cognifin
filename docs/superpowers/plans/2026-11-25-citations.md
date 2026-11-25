# Phase 6.0 Reliable Citations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answers carry valid page citations for at least 90% of answered questions, rendered as chips, without losing faithfulness or correctness.

**Architecture:** The prompt demands `[chunk_N]` markers. A pure backend function fills markers only where a sentence's exact figure appears in a context passage, and runs on the final answer before citations are extracted. The frontend turns markers into page chips. The eval reports the split between the model's own citations and the code fill.

**Tech Stack:** Python 3 / FastAPI / pytest / ruff; React 19 + react-markdown; Node assert check scripts.

**Spec:** `docs/superpowers/specs/2026-11-25-citations-design.md`

## Global Constraints

- Targets: cited share ≥ 0.90; citation validity ≥ 0.95; faithfulness and correctness each drop ≤ 1 pt vs v2 (0.994 / 0.870).
- Paid eval spend: at most about $0.45. The 15-question tuning subset (below) costs about $0.03 per try; then at most 2 full runs. Tune on the subset only; never edit `golden_set.json`, the judge or the scorer to raise scores.
- Fill matching: whole numbers only, never substrings. Trailing decimal zeros are ignored. A passage number may be rounded to the answer's decimal places; the answer number is never rounded. No unit conversion.
- `finish(fin, answer)` (numbers check) receives the **pre-fill** answer.
- Use `backend/venv/Scripts/python.exe` (bare `python` is miniconda). Backend: `pytest tests/test_*.py -q` and `ruff check .` green. Frontend: `npm run lint`, all `src/utils/*.check.mjs`, and `VITE_API_BASE=https://api.example.invalid npm run build`.
- **Tuning subset (fixed, picked 2026-11-25 before tuning):** `infy-2024-insemi,mm-2026-e3w,cipla-2024-ceo,asianpaint-2025-sleek,wipro-2025-ceo,bharti-2026-rank,bajfinance-2026-aum,coalindia-2024-production,titan-2026-totalincome,ntpc-2026-added,tatasteel-2024-deliveries,maruti-2025-sales,axisbank-q4fy26-gnpa,techm-q1fy27-revenue,trent-fy26-eps` (6 narrative, 6 table, 3 numeric).

## Review Focus

1. **Answer text with the model's own odd marker formats** (`(chunk_12)`, `[chunk_12, chunk_40]`, `chunk_12` bare). The fill must treat these units as already cited; the frontend must link them all. (Task 1 test; Task 5 check)
2. **A figure that appears in several passages:** the first in context order wins, so a `fin_N` row beats a chunk. (Task 1 test)
3. **Markdown tables in the answer:** the marker goes inside the last cell, and the table still renders. (Task 1 test; Task 5 browser check)
4. **A cached answer from before the change** (in-memory cache): it still renders, with no chips and no crash. (Task 5: the helper is a no-op without markers)
5. **Evidence ids with prefixes** (`[expanded]chunk_12`, `[TCS]:chunk_12`): chip lookup matches on the bare id. (Task 5 check)

---

### Task 1: `fill_figure_citations`

**Files:**
- Create: `backend/generation/citation_fill.py`, `backend/tests/test_citation_fill.py`

**Interfaces:**
- Consumes: `_REF`, `bare_chunk_id` from `core/citation_verifier.py`.
- Produces: `fill_figure_citations(answer: str, context_items: list[tuple[str, str]]) -> tuple[str, list[str]]`. `context_items` is `(id, text)` in context order. It returns the new answer and the bare ids added, one per marker, in order. Markers are written as `[<bare id>]`.

- [ ] **Step 1: Write the tests.** Use `ctx = [("fin_1", "Revenue | Q | ₹240,893.0 crore | AR p.17"), ("chunk_7", "revenue from operations 2,40,893 ..."), ("chunk_9", "gross NPA 1.24% ...")]`. Cases:
  - `test_figure_gets_first_matching_passage`: `"Revenue was ₹2,40,893 crore."` → ends with `[fin_1]` before the period or at the end of the sentence (assert `"[fin_1]" in out`), and `added == ["fin_1"]`.
  - `test_chunk_when_no_fin`: same sentence with `ctx[1:]` → `[chunk_7]`.
  - `test_whole_number_only`: `"It rose 240 bps."` with ctx `[("chunk_1", "code 2408930")]` → unchanged, `added == []`.
  - `test_rounding_one_way`: `"NPA was 1.2%."` with chunk_9 → `[chunk_9]`; `"NPA was 1.24%."` with ctx `[("chunk_2", "NPA 1.2%")]` → unchanged.
  - `test_years_and_small_ints_ignored`: `"In FY2024 and 2023-24, 3 segments grew."` → unchanged.
  - `test_existing_cite_untouched`: for each of `"Revenue ₹2,40,893 crore [chunk_7]."`, `"Revenue ₹2,40,893 crore (chunk_7)."` and `"Revenue ₹2,40,893 crore [chunk_7, chunk_9]."`, the output equals the input.
  - `test_table_row_marker_in_last_cell`: `"| Revenue | 2,40,893 |"` → `"| Revenue | 2,40,893 [fin_1] |"`; the separator row `"|---|---|"` is unchanged.
  - `test_heading_and_refusal_untouched`: `"## Revenue 2,40,893"` unchanged; `"Not available in the provided documents."` unchanged.
  - `test_at_most_two_markers_per_unit`: a sentence with 3 matching distinct figures in 3 passages gets exactly 2 markers.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_citation_fill.py -q` from `backend/`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** per the spec's "Code fill" rules. The number regex captures digit runs with `,` grouping and an optional decimal part. Normalise by dropping commas, `₹` and `Rs.`, then compare as `Decimal`. A figure qualifies with ≥ 3 significant digits, or a decimal point, or a following `%`. Years 1990–2039 are excluded, whether standalone or inside `FY…` or `20xx-yy`. To compare, check the passage numbers: equal after normalisation, or the passage number quantised to the answer's decimal places equals the answer number.
- [ ] **Step 4: Run** the tests. Expected: all pass. Then run `ruff check .`. Expected: clean.
- [ ] **Step 5: Commit** `git add backend/generation/citation_fill.py backend/tests/test_citation_fill.py && git commit -m "feat(citations): fill figure citations only on exact figure matches"`

### Task 2: Prompt demands bracketed citations

**Files:**
- Modify: `backend/generation/prompt_builder.py` (rule 6, section descriptions, `build_prompt` user message), `backend/generation/intent_prompts.py` (each "Cite chunk IDs" line, `build_intent_prompt` user message)
- Test: `backend/tests/test_prompt_citations.py`

**Interfaces:**
- Produces: the module constant `CITE_REMINDER = "Cite the context id in square brackets after each fact, e.g. [chunk_12]."` in `prompt_builder.py`. Both builders' user messages end with it.

- [ ] **Step 1: Write tests.**
  - `test_generic_prompt_reminder_and_format`: `build_prompt("[chunk_1]: x", "Q?")` gives a user message ending with `CITE_REMINDER`, and a system prompt containing `"[chunk_12]"`.
  - `test_intent_prompt_reminder`: the same assertions for `build_intent_prompt` with each intent key used by `main._STRUCTURED_PROMPTS`.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_prompt_citations.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Rule 6 becomes the hard bracket rule from the spec (§1): after every sentence, bullet or table row with a figure or fact; ids only from CONTEXT; `[chunk_12][chunk_40]` for several; none in headings or follow-up lines.
  - Section descriptions show one inline example marker.
  - Intent prompts get the same rule text.
  - Append `"\n\n" + CITE_REMINDER` to both user messages.
- [ ] **Step 4: Run** these tests and the whole suite: `venv/Scripts/python.exe -m pytest tests/test_*.py -q`. Expected: all pass. Fix any existing test that asserted the old user message equals the bare question, updating it to the new contract, and note it in the ledger.
- [ ] **Step 5: Commit** `git commit -am "feat(citations): prompt demands bracketed context ids after each fact"` (with the new test file added).

### Task 3: Wire the fill into `answer_events`

**Files:**
- Modify: `backend/main.py` (`answer_events`, around lines 900–973)
- Test: `backend/tests/test_chat_stream.py` (new tests using the existing `fresh_pipeline` fixture)

**Interfaces:**
- Consumes: `fill_figure_citations` (Task 1).
- Produces: the final payload `answer` includes filled markers; `metadata["citation_fill"]: list[str]`.

- [ ] **Step 1: Write tests.**
  - `test_final_answer_gets_filled_citation`: monkeypatch `main.retrieve_global` to return one result (SimpleNamespace with `chunk_id="chunk_7"`, `snippet="revenue 2,40,893 crore"`, `score=1.0`, `page_number=17`, `document_label="TCS AR 2024"`, `pdf_url=""`), and the LLM to stream `"Revenue was ₹2,40,893 crore."`. Assert:
    - the final `answer` contains `[chunk_7]`
    - `metadata["citation_fill"] == ["chunk_7"]`
    - `citations` contains `chunk_7`
  - `test_numbers_check_gets_prefill_answer`: monkeypatch `main.finish` to record its `answer` argument. Assert the recorded answer has no `[chunk_7]`.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_chat_stream.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - After `extract_follow_ups`, keep `model_answer = answer`.
  - Build `context_items = [(e["chunk_id"], e["snippet"]) for e in (fin.evidence if fin else [])] + [(r.chunk_id, r.snippet) for r in results]` (fin rows first, the same order as the context), then run `answer, filled = fill_figure_citations(answer, context_items)`.
  - `extract_citations`, `compute_confidence` and `verify_citations` use the filled `answer`.
  - `finish(fin, model_answer)`.
  - Add `"citation_fill": filled` to metadata.
- [ ] **Step 4: Run** the full suite and `ruff check .`. Expected: green.
- [ ] **Step 5: Commit** `git commit -am "feat(citations): fill figure citations in the final answer; numbers check sees the model's own answer"`

### Task 4: Eval reports the fill split

**Files:**
- Modify: `backend/tests/answer_scoring.py` (`score_rows`), `backend/tests/test_answer_scoring.py`

**Interfaces:**
- Consumes: each row's `metadata["citation_fill"]` (the eval runner already copies metadata into rows), and `row["answer"]`.
- Produces: `score_rows(...)["fill_only_share"]` and `["filled_marker_share"]` (`None` when there's nothing to divide). `build_metrics` copies `answers` keys through, so `metrics.json` gets them with no runner change.

- [ ] **Step 1: Write the test** `test_score_rows_fill_split`, with three answered rows:
  - A: valid `["chunk_1"]`, fill `[]`, answer containing `[chunk_1]`
  - B: valid `["chunk_2"]`, fill `["chunk_2"]`, answer containing `[chunk_2]` once
  - C: valid `[]`, fill `[]`

  Assert `fill_only_share == 1/3` and `filled_marker_share == 1/2`. Markers are counted with `_REF` over the answer.
- [ ] **Step 2: Run** it. Expected: FAIL (KeyError).
- [ ] **Step 3: Implement.**
  - fill-only: answered rows with valid citations, where every valid id is in `citation_fill`, divided by answered rows. Use bare ids.
  - filled_marker_share: total `len(citation_fill)` over total `_REF` matches in answered answers.
  - Rows without metadata count as fill `[]`.
- [ ] **Step 4: Run** `pytest tests/test_*.py -q` and `ruff check .`. Expected: green.
- [ ] **Step 5: Commit** `git commit -am "feat(eval): report fill-only and filled-marker shares"`

### Task 5: Citation chips in the chat

**Files:**
- Create: `frontend/src/utils/citations.js`, `frontend/src/utils/citations.check.mjs`
- Modify: `frontend/src/components/chat/MessageList.jsx` (assistant text → `linkCitations` → `ReactMarkdown` with an `a` component; also the streaming preview), `frontend/src/styles/chat.css` (one `.cite-chip` rule), `.github/workflows/ci.yml` (append `&& node src/utils/citations.check.mjs`)

**Interfaces:**
- Produces: `linkCitations(text: string, evidence: Array<{chunk_id, page_number}>|null) -> string`. Each marker group becomes markdown links `[label](#cite-<bareId>)`. The label is `p.<n>` when `page_number > 0`, `table` for `fin_*`, else `source`.
  - With non-empty evidence, ids missing from it are removed (along with the group's brackets or parentheses when empty).
  - With empty or null evidence, every id links as `source`.
  - Ids are compared bare (strip `[expanded]` and `[X]:` prefixes).

- [ ] **Step 1: Write the check script.**
  - `linkCitations('Rev ₹2,40,893 crore [chunk_12].', [{chunk_id:'chunk_12', page_number:17}])` gives `'Rev ₹2,40,893 crore [p.17](#cite-chunk_12).'`
  - `[fin_3]` with `{chunk_id:'fin_3', page_number:0}` gives `[table](#cite-fin_3)`.
  - `'[chunk_1, chunk_2]'` and `'[chunk_1][chunk_2]'` each give two links.
  - `'(chunk_1)'` gives one link.
  - An unknown id with non-empty evidence is removed.
  - A prefixed evidence id `'[expanded]chunk_12'` still labels `p.17`.
  - `'no markers'` is unchanged.
  - With null evidence, `[chunk_12]` gives `[source](#cite-chunk_12)`.
- [ ] **Step 2: Run** `node src/utils/citations.check.mjs` (from `frontend/`). Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `linkCitations`. In `MessageList`, pass `components={{ a: CiteLink }}`.
  - `CiteLink`: for `href` starting `#cite-`, render a `<button className="cite-chip">` (keyboard reachable, `aria-label="Open source, page N"`) that opens the evidence item's PDF at its page, the same way `EvidenceChunk`'s Open PDF does (`fin_*` opens its `pdf_url` if present).
  - Other links render as normal `<a>`.
  - The streaming preview uses `linkCitations(text, null)`.
- [ ] **Step 4: Run** the check, then `npm run lint` and the build. Expected: pass. Add the check to the CI `Unit checks` line.
- [ ] **Step 5: Browser check** (backend running locally with the real index, dev server): ask "What was TCS's revenue in FY24?".
  - Chips show `p.N` (no raw `[chunk_` text), and clicking one opens the PDF at that page.
  - A table answer still renders as a table.
  - Screenshot it.
- [ ] **Step 6: Commit** `git add frontend/src .github/workflows/ci.yml && git commit -m "feat(chat): render citation markers as page chips"`

### Task 6: Tune, measure, publish

**Files:**
- Modify (only if tuning needs it): `backend/generation/prompt_builder.py`, `backend/generation/intent_prompts.py`
- Create: `backend/tests/eval_reports/<ts>-v3-citations-answers.json`
- Modify: `frontend/public/metrics.json`, `backend/tests/eval_reports/README.md`, `frontend/src/pages/EngineeringPage.jsx` (`WEAK_SPOTS` only)

- [ ] **Step 1: Subset tuning.** Run `PYTHONUTF8=1 venv/Scripts/python.exe -m tests.eval_answers --label cite-tune-N --only <subset> --no-metrics`.
  - Read each answer's cited share, and its correct/faithful verdicts against the same ids in the v2 report.
  - If cited share on the subset is < 14/15, or any case that was correct in v2 becomes wrong: adjust prompt wording (within the spec's rules), commit with a message naming the change, and rerun.
  - Delete the subset reports after reading them.
  - Ledger each try and its cost.
  - Stop tuning at 14/15 cited with no regressions, or after 5 tries.
- [ ] **Step 2: Full run** `PYTHONUTF8=1 venv/Scripts/python.exe -m tests.eval_answers --label v3-citations`. Expected: 100 rows, `errors 0`.
  - On transient API errors, discard the run and rerun. That counts against the 2 full runs.
  - Compare against the targets. If any is missed and a full run remains, make one prompt change, verify it on the subset, and do the second full run.
  - Publish the better run: its report file and `metrics.json`. Delete the other run's report file and list it in the README.
- [ ] **Step 3: README.**
  - Add a `v3-citations` row to the answer-eval table, plus the new columns cited share, fill-only share and filled-marker share.
  - Add a "Citations (Phase 6.0)" note: the fill rule in one paragraph, pass/fail per target, every run listed with its cost.
- [ ] **Step 4: `/engineering` copy.** Update the `WEAK_SPOTS` citation line to match the new numbers truthfully. If the target was met, replace it with what still holds, e.g. the fill-only share. If it was missed, state the new cited share.
- [ ] **Step 5: Run** the backend suite, `ruff check .`, frontend lint, all checks and the build. Expected: green.
- [ ] **Step 6: Commit** `git add backend/tests/eval_reports frontend/public/metrics.json frontend/src/pages/EngineeringPage.jsx && git commit -m "eval: v3 citations — cited share, fill split, metrics.json"`
