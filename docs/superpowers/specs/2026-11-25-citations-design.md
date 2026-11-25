# Phase 6.0: reliable citations — design

Date: 2026-11-25. Branch: `phase-6-citations` (from `main`).

## Intent

The new landing page (Phase 6.1, `docs/superpowers/specs/2026-11-25-landing-redesign-design.md`) promises "Every answer points to its page". Today that isn't true: in the v2 eval, `cited_share` is 0.021, so about 98% of answers carry no citation. The user chose to make it true before the landing page ships, instead of softening the copy. This also fixes the top open follow-up from Phase 5.3.

## Goals and target (agreed with the user)

| Metric (from `tests.eval_answers`) | v2 baseline | Target |
|---|---|---|
| Cited share (answered questions with ≥ 1 valid citation) | 0.021 | **≥ 0.90** |
| Citation validity | 1.00 | **≥ 0.95** |
| Faithfulness | 0.994 | drop ≤ 1 pt |
| Correctness | 0.870 | drop ≤ 1 pt |

If the target is missed, the landing page falls back to its honest evidence wording (see the landing design); citations are never faked to hit a number.

## Non-goals

- Restyling the chat (Phase 6.2). This project only makes the citation markers render cleanly instead of as raw `[chunk_12]` text.
- Citing narrative sentences by guessing from word overlap (user rejected approach B for that reason).
- Changing the model, retrieval or the financials table.

## Approaches (user's choice: C)

- A: prompt fix only. Rejected alone: gpt-4o-mini may still skip citations.
- B: attach citations after generation by matching figures and phrases. Rejected: phrase overlap can cite the wrong page.
- **C: A + a narrow code fill (picked).** The model cites; code fills gaps only where a sentence's exact figure appears in an evidence passage, which is checkable rather than guessed.

## Design

### 1. Prompt (backend `generation/prompt_builder.py`, `generation/intent_prompts.py`)

- Replace rule 6 in `SYSTEM_PROMPT_TEMPLATE` with a hard format rule: put the id in square brackets, e.g. `[chunk_12]` or `[fin_3]`, right after every sentence, bullet or table row that states a figure or fact from the context. The id must be from the CONTEXT. Several ids go as `[chunk_12][chunk_40]`. Don't cite in headings or follow-up lines.
- Make the template's own section descriptions show a marker, so the format is demonstrated, not just described.
- Make the same change in every intent prompt's "Cite chunk IDs" line in `intent_prompts.py`.
- `build_prompt` and `build_intent_prompt` append one reminder line to the user message, after the question: "Cite the context id in square brackets after each fact, e.g. [chunk_12]." (Small models weigh the end of the prompt most.)

### 2. Code fill for figures (new pure function, backend)

`fill_figure_citations(answer: str, context_items: list[tuple[str, str]]) -> tuple[str, list[str]]` in `generation/citation_fill.py`.

- `context_items` is `(id, text)` in context order: financials rows (`fin_N`) first, as they are placed in the context today, then the RAG chunks.
- It returns the new answer and the list of ids it added (one entry per marker, in order).

Rules:

- Work line by line. Markdown table rows are units: a marker goes inside the last cell, before the closing `|`. Other lines are split into sentences at `. `, `! ` and `? `.
- Skip a unit that already has a marker (`_REF` from `core/citation_verifier.py`), a heading line (`#`), the separator row of a table, and the refusal sentence.
- **Figures** in a unit are number tokens that meet any one of these:
  - have ≥ 3 significant digits
  - contain a decimal point
  - are followed by `%`

  Excluded:
  - 4-digit years from 1990 to 2039, standing alone or as part of `FY24`, `FY2024-25` or `2023-24`
  - quarter and section labels such as `Q1` or `01`
- **Normalise** a number by stripping `₹`, `Rs.`, commas and spaces. This makes Indian and Western grouping the same: `2,40,893` = `240,893` = `240893`. Then compare the digit strings, keeping any decimal point. No unit conversion: the exact printed figure must appear in the passage.
- **Matching (builder check):** compare **whole numbers** taken from the passage the same way, never substrings (`240` must not match `2408930`; `12.5` must not match `112.53`). Two numbers are equal when:
  - they are equal after dropping trailing decimal zeros (`240893` = `240893.0`), or
  - the passage number rounded to the answer number's decimal places equals the answer number. Example: `1.24` → `1.2`, which matches the financials table's 2-decimal ratios against the prompt's 1-decimal rounding.

  Rounding only goes one way: a precise passage figure can match a rounded answer figure, never the reverse.
- **Pick the passage.** The first item in context order that contains a matching number for one of the unit's figures. At most 2 markers per unit, one per distinct figure, in order of appearance. If no passage matches, the unit is left uncited.
- Pure function: no I/O, no LLM.

### 3. Where it runs (backend `main.py` `answer_events`)

- After `extract_follow_ups` and before `extract_citations`, run `answer, filled = fill_figure_citations(answer, context_items)`.
- `finish(fin, answer)`, the Phase 4 numbers check, keeps receiving the **pre-fill** answer, so today's behaviour is unchanged. Each `fin_N` marker the fill adds would otherwise pull more numbers into that check and raise false "unmatched" warnings. The fill's own markers are exact matches by construction.
- `context_items` is built from the same `results` and `fin` rows that went into the context. Use the **same id strings and snippets** the model saw: `build_context` labels and `fin.block` rows. The builder exposes them, e.g. by having `build_context` also return the `(id, text)` pairs.
- Add `"citation_fill": filled` (the list of ids) to `metadata`, next to `citation_check`, so it's visible how many markers came from code versus from the model.
- The final event's `answer` already replaces the streamed text in the UI (`ChatPage.handleSend`), and the same payload is cached and saved. So no streaming change is needed. While streaming, the preview shows only the model's own markers; filled ones appear when the final event arrives.

### 4. Rendering markers (frontend)

- New pure helper `src/utils/citations.js`:
  - `linkCitations(text, evidence) -> string` turns each marker group (`[chunk_12]`, `[chunk_12][fin_3]`, `[chunk_12, chunk_40]`, `(chunk_12)`) into markdown links with a fragment href `#cite-<id>`.
  - Label: `p.<page>` when that evidence item has `page_number > 0`, `table` for `fin_N`, else `source`.
  - Ids not in `evidence` are dropped from the text, never shown raw.
- `MessageList` runs the assistant text through it before `ReactMarkdown`, and passes an `a` component. A `#cite-` link renders as a small chip (mono, muted gold hairline; final styling is Phase 6.2). Clicking a chip opens that evidence item's PDF at its page, in the same way the evidence list's "Open PDF" does today.
- While streaming, the same transform runs on the preview text, with the evidence known so far (none until the final event, so labels fall back to `source`).
- The existing "Sources:" row stays.

### 5. Eval and write-up

- Run `PYTHONUTF8=1 python -m tests.eval_answers --label v3-citations` (about $0.15; the cost was approved with 5.3).
- `eval_answers` records `citation_fill` per row.
- **Fill-only share** = answered questions whose valid citations all came from the fill / answered questions. These are questions that count as cited only because of the code fill.
- **Filled marker share** = filled markers / all markers.
- Both go in the README and in `metrics.json` as `answers.fill_only_share` and `answers.filled_marker_share`. That shows how much of the cited share is code rather than the model.
- The README gets a `v3-citations` row in the answer-eval table, with a note on the fill rule.
- `/engineering`'s static `WEAK_SPOTS` copy is updated by hand: drop or rewrite the "rarely show citation tags" line to match the new numbers.
- Check the result against the target table. Record pass/fail per metric in the README.
- **Budget and stopping rule (user's choice A):**
  1. First, tune the prompt on a fixed 15-question subset with `--only` and `--no-metrics` (about $0.03 per try). The subset is 6 narrative, 6 table and 3 numeric questions, picked before tuning starts and listed in the plan.
  2. Then do at most **2 full runs**. Worst case is about $0.45 in total.
  3. The best full run is published as-is, with all runs listed in the README.
  4. If the target is still missed, stop, record the miss honestly, and Phase 6.1 uses its fallback wording.
  5. Tune on the subset only; never change the eval set or the judge to raise scores.

## Tests

- **Backend pytest `tests/test_citation_fill.py`**, assertions:
  - A sentence with `₹2,40,893 crore` gets the first passage containing that number: plain `240893`, `2,40,893` or `₹240,893.0`.
- `240` does not match a passage that only has `2408930`.
- An answer `1.2%` matches a passage `1.24%`; an answer `1.24%` does not match a passage `1.2%`.
  - A table row gets its marker inside the last cell.
  - Years (`FY2024`, `2023-24`) and small integers don't trigger a fill.
  - A unit that already cites is unchanged.
  - With no matching passage, the answer is unchanged and the count is 0.
  - When both a `fin_N` row and a chunk contain the figure, the `fin_N` row wins (it's first).
  - Headings and the refusal sentence are untouched.
  - At most 2 markers per unit.
- **Prompt test:** the user message built by `build_prompt` and `build_intent_prompt` ends with the reminder line, and the system prompt contains the bracket format.
- **Frontend `src/utils/citations.check.mjs`**, assertions:
  - `[chunk_12]` with page 17 evidence becomes `[p.17](#cite-chunk_12)`.
  - `[fin_3]` becomes a `table` link.
  - `[chunk_12, chunk_40]` and `[chunk_12][chunk_40]` become two links.
  - An id that isn't in the evidence is removed, but only when evidence is given. While streaming (evidence empty) markers stay as `source` chips.
  - Ids are matched on the bare `chunk_N` / `fin_N`, because context and evidence ids can carry `[expanded]` or `[TCS]:` prefixes.
  - Text without markers is unchanged.
- The check goes on the CI `Unit checks` line.
- **Browser check:** a real `/chat` question shows chips (not raw ids), and clicking one opens the PDF at the right page.

## Constraints

- Zero added recurring cost; paid eval spend capped at about $0.45 (see the stopping rule).
- `pytest tests/test_*.py`, `ruff check .`, `npm run lint`, the check scripts and the production build all pass.
- The response cache is in memory, so restarting the backend clears old uncited answers. Nothing else to migrate.

## Left to the builder

- The exact prompt wording (within the rules above), and the regexes for figures and sentence splitting.
- The chip's interim markup and CSS.
- How `build_context` exposes the `(id, text)` pairs.
