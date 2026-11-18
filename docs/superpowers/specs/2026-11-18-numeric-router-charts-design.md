# Numeric router, charts and comparison: design

Date: 2026-11-18. ROADMAP Phase 4, items 1–3. SSE streaming (item 4) is a separate project done after this one.

## Intent

When a question asks for a number the Phase 3 `financials` table holds (company + metric + period), the answer should use the verified figure from the filing, cite it, and show it as a chart whose points link back to the filing. Today every number comes from RAG chunks, and the product has no charts at all. This "exact numbers from a table, narrative from RAG" setup is the headline architecture for the resume (ROADMAP), so the chart must be trustworthy: every plotted value is a table row, never a value the LLM made up.

ROADMAP success test: *a numeric answer's chart values match the filing; a comparison cites both companies.*

## Goals

- Detect company + metric + period in a question with rules, then fetch the matching rows from `financials.duckdb`.
- Give those rows to the LLM as a cited context block next to the RAG chunks.
- Post-check the answer: flag numbers attributed to the table that match no row.
- Return chart data built from the same rows, and draw it in the chat with Recharts. Clicking a point opens the filing.
- Comparison: two or more companies give one chart series each, and the answer cites rows from every company.

## Non-goals

- SSE streaming (next project).
- Fetching filings for companies not in the corpus (planned after Phase 4).
- An LLM-based metric extractor (approach 2/3 below). Revisit only if measured coverage is weak.
- NIM or any metric not in `financials/metrics.py`. Periods outside Q Mar-2025..Sep-2026 and FY25/FY26.
- More than one chart per answer. Chart styling beyond clean defaults (Phase 6 does the visual system).

## Anti-goals (failure even if it "works")

- A chart point whose value is not exactly a table row.
- Numeric questions answered worse than today. A missed detection must give exactly today's answer.
- Silently mixing consolidated and standalone figures.

## Constraints

- `INTELLIGENT_PARSING_ENABLED` is false by default. The normal path is `retrieve_global` with the rule-based `parse_query` (`query/query_understanding.py`), which gives `companies`, `years` and `intent`, but **no metrics**. The router must work out the metric itself. It must also work when the intelligent path is on (`iq.companies`, `iq.years`).
- Table: 47 companies (NSE symbols, e.g. `ADANIENT`), 5,243 rows, 22 metrics. Units are `INR` (absolute rupees), `INR_per_share`, `pct` and `ratio`. Each row carries `source_url` (a BSE PDF or an NSE iXBRL HTML), `source_file`, `page` (None for iXBRL) and `method` (xbrl/rule/llm).
- Read API exists: `financials/query.py` `get_metric()` and `available()`. `get_metric` never substitutes basis.
- Indian fiscal year: Q1 = Apr–Jun (ends Jun 30), Q4 ends Mar 31. FY26 ends 2026-03-31.
- Response cache is keyed by question. Rows are static between builds, so cached payloads stay valid. Rebuilding the table needs a cache clear (already true for re-indexing).
- No new backend dependencies. The frontend adds `recharts` (not installed today; the app is React 19, so it needs a Recharts version that supports React 19).

## Approaches (how to detect the metric)

1. **Rules (chosen by the user).** An alias list that maps phrases to metric names, plus a period parser. No added latency, deterministic, easy to test. It misses unusual wording, and a miss falls back to today's RAG answer.
2. **LLM extraction.** One small model call per question. Handles paraphrases, but adds ~0.5–1 s and cost to every question, and can return metric names that aren't in the table.
3. **Rules with an LLM backup.** Better coverage, but two code paths. Kept as the upgrade path if approach 1's coverage is weak.

Simplification (my call): there is no three-way numeric/narrative/both classifier. Because rows go to the LLM as context (option A, decided 2026-11-17), RAG **always** runs, and the router only decides whether to add a rows block. "Numeric only" and "both" become the same code path.

## Design

### 1. Router: `backend/financials/router.py` (new)

`route(question, companies, years) -> Lookup | None`

- **Companies:** from the parser already run (`parsed.companies` / `iq.companies`), kept only if the company has rows in the table. If none are left, return `None`.
- **Metrics:** a module-level alias dict, phrase → canonical metric. Matching is case-insensitive with word boundaries, longest phrase first (so "net profit margin" doesn't fire `net_profit`; see the ambiguity list below). Seed aliases (the builder extends them from the test questions):
  - `revenue_from_operations`: revenue, revenues, sales, topline, turnover, revenue from operations
  - `total_income`: total income · `other_income`: other income · `total_expenses`: total expenses, expenses
  - `profit_before_tax`: profit before tax, PBT · `tax_expense`: tax expense, tax
  - `net_profit`: net profit, profit, PAT, profit after tax, net income, earnings · `net_profit_owners`: profit attributable to owners/shareholders
  - `eps_basic`: EPS, earnings per share, basic EPS · `eps_diluted`: diluted EPS
  - Bank: `interest_earned` (interest earned, interest income), `gross_npa_pct` (gross NPA, GNPA), `net_npa_pct` (net NPA, NNPA), `capital_adequacy_pct` (capital adequacy, CAR, CRAR), `cet1_pct` (CET1), `return_on_assets_pct` (ROA, return on assets)
  - Insurer: `gross_premium`, `net_premium`, `first_year_premium` (FYP), `renewal_premium`, `single_premium`, `solvency_ratio` (solvency)
  - When a bank is asked for "revenue", map it to `interest_earned` (banks have no `revenue_from_operations`; see `metrics_for`). Ambiguous phrases that are **not** mapped: margin, NIM, ROE, growth (fall back to RAG).
- **Periods** (regex, no year guessing):
  - `Q1–Q4 FY26` / `Q2FY26` / `Q2 FY2026` → Q row with that period end
  - `Sep 2026` / `September 2026` / `quarter ended 30 Sep 2026` → Q row
  - `FY25` / `FY2025` / `2024-25` → FY row (2025-03-31)
  - `last N quarters` → the latest N Q rows
  - a bare year from `years` (e.g. "2026") → FY row for that FY, **only if no other period form matched** (the most specific form wins; `parse_query.years` also holds "2026" for "Sep 2026" or "Q2 FY2026", and that must not add an FY row)
  - No period, or words like trend/over time/history → all Q rows (up to 7)
  - Period stated but not in the table → no rows for that company (see per-company below).
- **Per company** (my call): every decision (basis, available periods) is made separately for each company. A company with no rows for the asked metric and period is left out of the rows and listed in the block as `not in verified table: <COMPANY>`, so the LLM answers for it from RAG chunks. If no company has rows, return `None`.
- **Basis** (my call): `consolidated` by default, and `standalone` if the question says "standalone". Otherwise, for each company, pick the basis with **more rows** in the requested range, with ties going to consolidated (this covers zero consolidated rows, and 1 consolidated vs 7 standalone). Label a standalone pick "standalone" in the block, the series name and the metadata. Never mix bases within one series.
- Multiple metrics found: fetch rows for all of them (cap 3), chart the first.
- `Lookup` holds `rows: list[Row]`, `metric`, `basis`, `companies`, `period_desc`.

### 2. Rows context block (`generation/`)

Prepended to the RAG context. Each row gets an id the LLM can cite, `fin_1`, `fin_2`, …, alongside the existing `chunk_N` ids:

```
VERIFIED FIGURES (from company filings; use these numbers exactly and cite [fin_N]):
[fin_1] ADANIENT | net_profit | Q ended 30-Sep-2026 | consolidated | ₹1,221.0 crore | BSE results filing p.8
```

INR values are shown in ₹ crore (1 crore = 1e7) with 1 decimal. pct as `x.xx%`, ratio as `x.xx×`, EPS as `₹x.xx`. One line goes into the system prompt: "Figures in VERIFIED FIGURES are authoritative; prefer them over chunk text for the same metric and period." This works with both the generic and the intent prompts.

`fin_N` ids go into `chunk_ids`, **and** the `chunk_\d+` regexes in `extract_citations` (`generation/prompt_builder.py`) and `verify_citations` (`core/citation_verifier.py`) must be widened to `(chunk|fin)_\d+`. Today they accept only `chunk_N`. Each row also becomes an `EvidenceItem` (`snippet` = the line above, `pdf_url` = `source_url`, `page_number` = `page`, `document_label` = e.g. "ADANIENT results Q2 FY27"), so it appears in the existing Evidence panel.

### 3. Post-check

After generation: for each sentence or table row in the answer that cites `[fin_N]`, extract its numbers, convert crore/lakh/billion/% to the row's unit, and check that each one matches some row value within rounding (relative 0.5%, or ±0.05 for pct/ratio/EPS). Ignore years, quarter numbers, and numbers in sentences without a `fin` citation (those are RAG numbers, already covered by `verify_citations`). Output `metadata.numbers_check = {"checked": n, "unmatched": ["…"]}`. It doesn't block the answer. The UI shows a small note if `unmatched` is non-empty.

### 4. Payload: `metadata.chart`

`answer_question` adds `payload["metadata"]["chart"]` (or `None`), along with `numbers_check`. It goes inside `metadata` because `ChatResponse` (`main.py`) is a strict response model and would strip a new top-level key. The frontend then reads it as `message.metadata.pipeline.chart` (`ChatPage.jsx` stores backend metadata under `pipeline`).

**Persistence** (my call): `persist_exchange` also saves `chart` and `numbers_check` in the assistant message's metadata, and the history load exposes them at the same path, so charts survive a conversation reload.

`metric`, `label` and `basis` live **per series**, because a comparison can mix a bank (`interest_earned`) with a non-bank (`revenue_from_operations`), or a consolidated company with a standalone one. Each series name shows any difference, e.g. "HDFCBANK (interest earned)" or "SBIN (standalone)". All series in one chart must share `unit`/`display_unit`.

```json
{"unit": "INR", "display_unit": "₹ crore", "period_type": "Q",
 "series": [{"company": "ADANIENT", "metric": "net_profit", "label": "Net profit",
             "basis": "consolidated", "points": [
   {"period_end": "2026-09-30", "label": "Q2 FY27", "value": 1221.0,
    "source_url": "https://…pdf", "page": 8, "fin_id": "fin_1"}]}]}
```

Values in the chart are the row values converted to the display unit, with no rounding beyond that conversion. A chart is sent only when there are ≥2 points total (a single number needs no chart).

### 5. Frontend: `components/chat/FinancialChart.jsx` (new)

- Rendered in `MessageList.jsx` under the answer, from `message.metadata.pipeline.chart`.
- One company → line chart over periods. Several companies with one period each → grouped bar chart. Several companies over several periods → line chart, one line per company.
- Tooltip: company, period label, value, "method: xbrl/rule/llm".
- Click a point: open `source_url` in a new tab, with `#page=N` for PDFs. (Changed while planning: the filings live on bseindia.com/nseindia.com, which we don't serve, and pdf.js in `PDFViewerModal` would hit CORS.)
- Unmatched-numbers note: one muted line under the chart.

### 6. Wiring in `answer_question` (`backend/main.py`)

Run `route()` once retrieval is done, on all three paths (session, intelligent, global), using whichever parse result exists. If it returns a `Lookup`: build the block and evidence items, add the ids, then run the post-check and build the chart after generation. If it returns `None`, nothing changes. Record `"router": {"hit": bool, "metric": …, "rows": n}` in metadata.

### 7. Comparison

No separate feature. ≥2 companies already makes `intent == "comparison"`, which uses the compare prompt (it demands a table). The router returns rows for every company it has data for, the block lists them, and the chart has one series each. Coverage is uneven (e.g. APOLLOHOSP has 1 consolidated Q row for net_profit, and SBIN and RELIANCE have 4 of 7), so a company may be charted with fewer points or not at all. Eval pass rule: the answer cites every company, with a `fin` row where the table has one and a `chunk` otherwise.

## Testing

- `tests/test_financials_router.py`: ~40 questions → expected `(companies, metric, period_type, period ends)` or `None`. Covers each alias group, each period form, bank-revenue mapping, ambiguous terms → None, out-of-range period → None, and standalone fallback.
- Post-check unit tests: crore/lakh conversion, rounding tolerance, ignoring years and uncited numbers.
- Phase 4 eval (`tests/eval_financials_router.py` + a section in `tests/eval_reports/README.md`): ~15 real questions (single-company trend, specific quarter, FY, bank, insurer, 3 comparisons) through `answer_question`. Assert that chart values equal DB rows exactly, report `unmatched` counts, check that comparisons cite both companies, and report router hit rate on the set. Needs the LLM, so it is run by hand, not in pytest.

## Calls made by Claude (user to check)

- No three-way classifier: RAG always runs, and rows are added when detected.
- Consolidated by default. Otherwise, for each company, the basis with more rows, labeled when standalone.
- Decided per company: a company without rows is left out of the chart and answered from RAG, and the block says so.
- Metric and basis are per series in the chart (bank vs non-bank, consolidated vs standalone), with the difference in the series name.
- The chart rides in `metadata` and is saved to Mongo, so it survives a reload.
- A bare year counts as FY only when no more specific period was stated.
- Bank "revenue" → `interest_earned`. Margin/NIM/ROE/growth not mapped.
- Display in ₹ crore. One chart per answer, first metric only. No chart for a single value.
- Post-check flags only; it never rewrites or blocks the answer.

## Left to the builder

Exact regexes and the alias list beyond the seeds; how `Lookup` is shaped internally; the Recharts version (must support React 19); chart colours and sizes (keep plain; Phase 6 restyles); file split inside `generation/` for the block builder.
