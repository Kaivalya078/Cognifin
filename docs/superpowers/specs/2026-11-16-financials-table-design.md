# Phase 3 — Financials table: design

Date: 2026-11-16 · Status: draft for review

## Intent

Phase 4 needs exact numbers. Its numeric router answers "what was X's revenue last
quarter" from a table rather than from retrieved prose, its charts plot trends where
every point links to the filing, and comparisons come out as tables. Phase 3 builds that
table: one row per reported figure, each traceable to the filing and page it came from.

It is a portfolio piece, so "correct and provable" beats "big". A wrong number in a chart
is worse than a missing one.

## Scope as decided (user, 2026-11-16)

- **Companies:** the 47 NIFTY-50 symbols that have data (KWIL has none; skipped).
- **Periods (option A):** the quarter each filing reports, Mar-2025 … Sep-2026
  (7 quarter-ends), plus full-year FY2025 and FY2026 taken from the Q4 filings'
  year-to-date / "year ended" column. Prior-year comparative columns are **not** stored.
- **Line items (option C):** headline items for everyone, plus bank and life-insurer
  items (table below).
- **PDF extraction (option C):** rules first; the LLM only fills items the rules did not
  produce or whose rule value failed a check. Both paths pass the same checks.
- **Sources:** the 203 NSE integrated-filing iXBRL web pages already cached, and 169 BSE
  results PDFs for the quarters NSE was missing. Nothing is fetched at query time.

## Goals

1. A DuckDB file with every in-scope figure, in rupees, standalone and consolidated
   where the filing has both, each row carrying its source file, URL and page.
2. One command rebuilds it from the source files, deterministically (LLM answers cached).
3. A measured accuracy number: a hand-checked answer key, and a report of
   precision (stored values that are right) and coverage (expected values present).
4. A small read API for Phase 4.

## Non-goals

- Numeric router, charts, comparison UI, chat integration (Phase 4).
- Scheduled fetching from NSE/BSE, or any new downloads (sources are already on disk).
- Prior-year comparatives, restatements, FY2024 or earlier.
- Segment revenue, full expense breakdown, balance sheet, cash flow.
- NBFC-specific items (Bajaj Finance, Bajaj Finserv, Shriram, Jio Financial get the
  common items only), annual-report statement parsing.
- OCR: SBIN Mar-2025 is an image-only PDF and stays a listed gap.

## Anti-goals

- A stored value that differs from what the filing prints (after unit conversion).
- A value with no source link, or a value the LLM produced that is not on the page.
- Silent unit errors (lakh read as crore, million as crore).
- Mixing standalone and consolidated, or quarter and year-to-date, under one label.

## Line items

Canonical metric names; amounts in INR, ratios in percent, EPS in INR per share.

| Group | Metric | Unit |
|---|---|---|
| All | `revenue_from_operations`, `other_income`, `total_income`, `total_expenses`, `profit_before_tax`, `tax_expense`, `net_profit`, `net_profit_owners` (attributable to owners of the parent; consolidated only), `eps_basic`, `eps_diluted` | INR / INR per share |
| Banks (BANKING filings) | `interest_earned`, `gross_npa_pct`, `net_npa_pct`, `capital_adequacy_pct`, `cet1_pct`, `return_on_assets_pct` | INR / % |
| Life insurers (LI filings) | `gross_premium`, `net_premium`, `first_year_premium`, `renewal_premium`, `single_premium`, `solvency_ratio` | INR / ratio |

Banks have no `revenue_from_operations` line; it stays empty for them (not derived).
`solvency_ratio` is stored as printed (e.g. 1.96), unit `ratio`. Return on assets
is stored as printed for the period (quarterly, not annualised).

## Storage

`backend/index_cache/financials.duckdb` (ships with the index tarball at deploy).
New dependency: `duckdb`.

**`financials`** — one row per figure.

| column | notes |
|---|---|
| `company` | NSE symbol |
| `basis` | `standalone` / `consolidated` |
| `period_type` | `Q` / `FY` |
| `period_start`, `period_end` | dates |
| `fiscal_year` | FY label, e.g. 2026 for Apr-2025…Mar-2026 |
| `fiscal_quarter` | 1–4, null for FY |
| `metric` | from the table above |
| `value` | DOUBLE, converted (INR, %, ratio) |
| `unit` | `INR`, `INR_per_share`, `pct`, `ratio` |
| `source_kind` | `nse_ixbrl` / `bse_pdf` |
| `source_file`, `source_url` | relative path under `backend/data/quarterly/`, original URL |
| `page` | 1-based PDF page; null for iXBRL |
| `method` | `xbrl` / `rule` / `llm` |
| `audited` | bool where the filing states it, else null |

Primary key `(company, basis, period_type, period_end, metric)`. If two sources ever give
the same key, iXBRL wins and the conflict goes to `review`. *(Claude's call.)*

**`filings`** — one row per source file: path, URL, symbol, kind (INDAS / BANKING /
NBFC_INDAS / LI / PDF), basis, period, status (`parsed` / `partial` / `failed`), reason.

**`review`** — every rejected candidate: key, candidate value, method, which check
failed, page. This is the work list for fixing rules, not a silent drop.

## Source files

Moved out of `.superpowers/` (scratch) into `backend/data/quarterly/<SYMBOL>/`
(gitignored like the PDFs): `YYYY-MM_<basis>.html` for iXBRL, `YYYY-MM.pdf` for BSE.
A committed `backend/data/quarterly/sources.csv` lists symbol, period end, kind, basis,
URL and SHA-256 for every file, so the corpus is reproducible and auditable.
*(Claude's call: the source of truth must not live in a scratch folder.)*

## Extraction

### iXBRL (203 files)

The web pages are HTML tables of labelled rows; values are in actual rupees
("INR (in Actuals)" — the "Level of rounding" row describes presentation and is ignored
for conversion, but recorded). Header rows give symbol, basis, reporting period and
audited flag. One label map per filing kind maps row labels to metrics; the
"3 months ended" column is the quarter value and, in Q4 filings, the "year to date"
column is the FY value. Dates come in `31-03-2026` and `31-Mar-2025` forms.

### BSE PDFs (169 files) — rules, then LLM fallback

1. **Find the statement pages.** Pages whose text has "financial results" and the
   quarter-end date; classify each as standalone or consolidated from its heading. A
   filing may hold both.
2. **Rebuild rows** with the geometry logic already in `core/pdf_chunker.py`
   (rows by y-centre, cells split at x-gaps), reused, not copied.
3. **Pick the column:** the column whose header contains the quarter-end date with
   "quarter / three months ended"; for FY, "year ended" with 31 March. Never positional.
4. **Units** from the page header ("₹ in crore", "Rs. lakh", "₹ million", "in ₹ crore
   except per share data"). No header found → nothing from that page is stored.
5. **Labels → metrics** through a synonym list per metric (shared with iXBRL where
   possible).
6. **LLM fallback** (gpt-4o-mini via the existing `OPENAI_*` settings, temperature 0,
   JSON output) for metrics the rules did not fill or whose rule value failed a check.
   Input: the text of the identified statement page(s) only. It returns, per metric, the
   number *exactly as printed*, the column header it took it from, and the page. Answers
   are cached on disk keyed by file hash + prompt version, so rebuilds are free and
   deterministic.

### Checks (both methods, before anything is stored)

1. **Verbatim:** the printed number string occurs on the cited page.
2. **Arithmetic**, where the parts exist: revenue + other income = total income;
   profit before tax − tax = net profit (allowing for exceptional items / share of
   associates when printed); tolerance one unit of the page's rounding.
3. **Units:** the unit came from the page header; converted values in a plausible range
   for the company (e.g. not 1000× the same metric in its other quarters).
4. **Ratios:** percentages within 0–100.

A failed check sends the candidate to `review`; if the rule value failed, the LLM is
tried once for that metric, and its value must pass the same checks.

## Build command

`python -m financials.build` (new package `backend/financials/`): reads `sources.csv`,
parses every file, runs checks, writes a fresh DuckDB atomically (temp file + rename),
prints a summary (files parsed / partial / failed, rows, review count, LLM calls made vs
cached).

## Read API (for Phase 4)

`financials/query.py`:
`get_metric(company, metric, basis="consolidated", period_type="Q", start=None, end=None)
-> list[Row]` ordered by `period_end`, each with value, unit and source link;
`available(company) -> dict` of metrics and periods present. Consolidated is the default;
if a company has no consolidated figure for a period, the standalone one is **not**
silently substituted — the caller sees what basis each row is.

## Accuracy proof

`backend/tests/financials_golden.json`: about 20 BSE PDFs and 5 iXBRL filings, spread
across banks, insurers, NBFCs and other companies and across layouts. For each,
the in-scope values read by hand from the filing (Claude drafts, user spot-checks, Claude
re-checks — the Phase 2 process). Frozen before extraction is tuned; changes only to fix
a verified mistake, logged in its changelog.

`tests/eval_financials.py` reports precision and coverage, overall and per method
(xbrl / rule / llm) and per sector. **Targets:** precision ≥ 99 % (a wrong number is the
failure that matters); coverage ≥ 90 % of the "All" metrics, ≥ 80 % for bank/insurer
metrics. Results recorded in `tests/eval_reports/`.

## Approaches considered (PDF extraction)

- **Rules only:** deterministic and free; brittle across 169 layouts.
- **LLM for everything, with checks:** robust; every value depends on a model call.
- **Rules first, LLM fills gaps (chosen by the user):** most values are deterministic and
  free; the LLM covers the odd layouts; both go through the same checks. Costs two code
  paths, which the shared checks and the answer key keep honest.

## Constraints

- Windows dev box, Python venv in `backend/venv`; CPU only for this phase.
- No new network sources; the OpenAI key in `backend/.env` is used only by the fallback.
- `backend/.env` is never printed or changed.

## Left to the builder

- Exact synonym lists and label maps per filing kind.
- Page-classification heuristics and how multi-page statements are stitched.
- Prompt wording and JSON schema for the fallback.
- Tolerances beyond "one rounding unit", and the plausibility rule's exact form.
- Test layout (one file per extractor is enough).
