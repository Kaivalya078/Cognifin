# Financials Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `backend/index_cache/financials.duckdb`, which holds the exact reported quarterly and FY figures for 47 NIFTY-50 companies. Each figure must trace back to its source file, URL and page.

**Architecture:** A new package, `backend/financials/`, turns source files into `Candidate` rows.
- An iXBRL label-map parser handles the 203 NSE web pages.
- A rules extractor handles the 169 BSE PDFs, and an LLM fallback fills the metrics the rules miss.
- Every candidate passes the same checks before it is stored. Rejected candidates go to a `review` table.
- One build command rebuilds the database atomically.
- A read API serves Phase 4.

**Tech Stack:** Python 3 (backend venv), DuckDB (new dependency), PyMuPDF (already installed), openai (already installed, used through `generation/openai_client.py` settings), pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-financials-table-design.md`

## Global Constraints

- Run every command from `backend/` with `venv/Scripts/python` (Windows). Set `PYTHONIOENCODING=utf-8` for CLI runs.
- **Scope:**
  - The 47 symbols that have data; KWIL is skipped.
  - Quarter ends from 2025-03-31 to 2026-09-30.
  - FY2025 and FY2026 values come only from Q4 filings.
  - Prior-year comparative columns are never stored.
- **Metric names, units and groups** are exactly as in the spec's Line items table. Units are `INR`, `INR_per_share`, `pct` or `ratio`.
- **Banks:** `revenue_from_operations` stays empty. Never derive it.
- **Storage:**
  - Amounts are stored in rupees.
  - `solvency_ratio` is stored as printed.
  - ROA is stored as printed for the period.
- **Primary key:** `(company, basis, period_type, period_end, metric)`.
  - When iXBRL and PDF give the same key, iXBRL wins and the conflict goes to `review`.
- **Before storing**, every value passes four checks: verbatim, arithmetic, units and ratio range. A failed candidate goes to `review`; it is never dropped silently.
- **LLM fallback:**
  - Uses `settings.OPENAI_MODEL` and `settings.OPENAI_BASE_URL` at temperature 0, with JSON output.
  - The input is only the identified statement page(s).
  - It runs only for metrics the rules missed or that failed a check, and only once per metric.
  - Answers are cached on disk, keyed by file SHA-256 plus `PROMPT_VERSION`.
- **Network:** no network access except the LLM fallback. Never print or modify `backend/.env`.
- **Source files:**
  - Live in `backend/data/quarterly/<SYMBOL>/`, which is gitignored.
  - Committed manifest: `backend/data/quarterly/sources.csv`.
- **Basis:** consolidated is the default. Standalone figures are never substituted for consolidated ones.
- **Accuracy targets:**
  - Precision of at least 99%.
  - Coverage of at least 90% for the "All" metrics.
  - Coverage of at least 80% for the bank and insurer metrics.

## Review Focus

1. **A statement continues onto a second page with no header row repeated.** Rows on page 2 must still be read with page 1's column choice and unit (Task 7: `test_continued_page_keeps_column_and_unit`).
2. **"₹ in crore except per share data".** EPS must not be multiplied by 1e7 (Task 3: `test_eps_not_scaled`; Task 7: `test_eps_unscaled_in_pdf`).
3. **Loss quarters printed as "(625.30)" or "-625.30".** These must be stored as negative, and the verbatim check must match the printed form (Task 3: `test_parens_negative`; Task 4: `test_verbatim_matches_parenthesised`).
4. **In Q4 PDFs, "Quarter ended 31.03.2026" and "Year ended 31.03.2026" share a date.** Column choice must use the phrase, not only the date (Task 7: `test_q4_quarter_vs_year_columns`).
5. **iXBRL "Year to date" in a non-Q4 filing (a half-year figure).** It must not become an FY row (Task 5: `test_ytd_only_in_q4`).

---

### Task 1: Package, metric vocabulary, DuckDB store

**Files:**
- Create: `backend/financials/__init__.py`, `backend/financials/metrics.py`, `backend/financials/store.py`
- Modify: `backend/requirements.txt` (add `duckdb>=1.1`)
- Test: `backend/tests/test_fin_store.py`

**Interfaces:**
- Produces:
  - `metrics.METRICS: dict[str, tuple[str, str]]` maps each metric to `(group, unit)`, with `group` one of `"all"`, `"bank"`, `"insurer"`.
  - `metrics.metrics_for(kind: str) -> list[str]`.
    - INDAS and NBFC_INDAS return "all".
    - BANKING returns "all" minus `revenue_from_operations`, plus "bank".
    - LI returns "all" plus "insurer".
  - `store.Candidate` is a dataclass with these fields:
    - `company, basis, period_type, period_start: date, period_end: date, metric, value: float, unit`
    - `printed: str`, `page: int | None`, `method: str`
    - `source_kind, source_file, source_url`, `audited: bool | None`
  - `store.fiscal_labels(period_end: date, period_type: str) -> tuple[int, int | None]`. For example, 2025-06-30 Q gives `(2026, 1)` and 2026-03-31 FY gives `(2026, None)`.
  - `store.write_db(path: str, rows: list[Candidate], filings: list[dict], review: list[dict]) -> None`. It writes to a temp file, then `os.replace`s it into place, and resolves key conflicts. The three tables match the spec.

- [ ] **Step 1: Write failing tests**

```python
def test_metrics_for_kinds():
    assert "gross_npa_pct" in metrics_for("BANKING") and "revenue_from_operations" not in metrics_for("BANKING")
    assert "solvency_ratio" in metrics_for("LI") and "gross_npa_pct" not in metrics_for("NBFC_INDAS")
    assert METRICS["eps_basic"][1] == "INR_per_share" and METRICS["gross_npa_pct"][1] == "pct"

def test_fiscal_labels():
    assert fiscal_labels(date(2025, 6, 30), "Q") == (2026, 1)
    assert fiscal_labels(date(2026, 3, 31), "Q") == (2026, 4)
    assert fiscal_labels(date(2026, 3, 31), "FY") == (2026, None)

def test_write_and_read_back(tmp_path): ...   # 2 rows → SELECT count(*) = 2, fiscal_year filled
def test_conflict_xbrl_wins(tmp_path): ...     # same key from nse_ixbrl and bse_pdf → 1 row (method 'xbrl'), 1 review row reason 'conflict'
def test_atomic_replace(tmp_path): ...         # existing db file replaced; no *.tmp left behind
```

- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_store.py -q`. Expected: FAIL (`ModuleNotFoundError: financials`).
- [ ] **Step 3: Implement** `metrics.py` and `store.py` per Interfaces, then install the dependency with `venv/Scripts/python -m pip install "duckdb>=1.1"`.
- [ ] **Step 4: Run** the same command. Expected: 5 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): metric vocabulary and DuckDB store"`.

### Task 2: Source files and manifest

**Files:**
- Create: `backend/financials/sources.py`
- Test: `backend/tests/test_fin_sources.py`
- Data (not committed except the csv): `backend/data/quarterly/`

**Interfaces:**
- Produces:
  - `sources.Source` is a dataclass with `symbol, period_end: date, kind, basis: str | None, path: Path, url, sha256`.
    - `kind` is one of `INDAS`, `BANKING`, `NBFC_INDAS`, `LI` or `PDF`.
    - `basis` is None for PDFs, which can hold both bases.
  - `sources.import_scratch(xbrl_manifest: Path, xbrl_cache: Path, results_dir: Path, links_csv: Path, out_dir: Path) -> int`. It copies files to:
    - `out_dir/<SYM>/YYYY-MM_<basis>.html` for iXBRL;
    - `out_dir/<SYM>/YYYY-MM.pdf` for PDFs.
    - It writes `out_dir/sources.csv` with the columns `symbol,period_end,kind,basis,file,url,sha256` and returns the file count.
  - `sources.load_sources(out_dir: Path) -> list[Source]`. It verifies each sha256 and raises `ValueError` naming the file on a mismatch or a missing file.
- Scratch inputs:
  - `.superpowers/xbrl-discovery/manifest.csv` (columns `symbol,kind,basis,period_start,period_end,rounding,url`). Its cache file names are the URL basenames.
  - `.superpowers/results-q/<SYM>/YYYY-MM.pdf` and `.superpowers/results-q/links.csv` (rows `sym,M/YYYY,Pname=<file>.pdf`). The PDF URL is `https://www.bseindia.com/xml-data/corpfiling/AttachHis/<file>`.

- [ ] **Step 1: Write failing tests:**
  - `test_import_and_load_roundtrip(tmp_path)`: two tiny fake inputs give `import_scratch == 2`, and `load_sources` returns 2 with the right `kind`/`basis`/`url`.
  - `test_hash_mismatch_raises(tmp_path)`.
  - `test_dates_both_formats`: `"31-03-2026"` and `"31-Mar-2025"` both parse.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_sources.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, plus a `__main__` block that runs `import_scratch` on the real scratch paths.
- [ ] **Step 4: Run tests.** Expected: 3 passed. Then run `venv/Scripts/python -m financials.sources`. Expected: `372 files` (203 + 169). Check that `git status` shows only `data/quarterly/sources.csv` as new. If `data/` ignores the csv, add `!data/quarterly/sources.csv` to `backend/.gitignore`.
- [ ] **Step 5: Commit** `financials/sources.py`, the tests, `sources.csv` and `.gitignore` with `git commit -m "feat(financials): source manifest for 372 filings"`.

### Task 3: Number, unit and date parsing

**Files:**
- Create: `backend/financials/numbers.py`
- Test: `backend/tests/test_fin_numbers.py`

**Interfaces:**
- Produces:
  - `parse_number(s: str) -> float | None`.
    - Handles Indian and western grouping, `(x)` and leading `-`/`–` as negative.
    - A blank cell, `-` or `—` gives None.
  - `unit_multiplier(header_text: str) -> float | None`.
    - crore gives 1e7, lakh gives 1e5, million gives 1e6, "in actuals" gives 1.
    - Matches `₹`/`Rs.`/`INR` variants. Returns None when no unit is stated.
  - `to_value(printed: str, metric: str, multiplier: float) -> float`. Applies the multiplier only when the metric's unit is `INR`.
  - `parse_date(s: str) -> date`. Accepts `31-03-2026`, `31-Mar-2025`, `31.03.2026`, `31/03/2026`, `March 31, 2026` and `31st March, 2026`.

- [ ] **Step 1: Write failing tests**

```python
def test_indian_grouping(): assert parse_number("1,08,532.40") == 108532.40
def test_parens_negative(): assert parse_number("(625.30)") == -625.30 and parse_number("-625.30") == -625.30
def test_dash_is_none(): assert parse_number("-") is None and parse_number("") is None
def test_units():
    assert unit_multiplier("(₹ in crore, except per share data)") == 1e7
    assert unit_multiplier("Rs. in Lakhs") == 1e5 and unit_multiplier("₹ million") == 1e6
    assert unit_multiplier("Statement of results") is None
def test_eps_not_scaled(): assert to_value("12.34", "eps_basic", 1e7) == 12.34
def test_pct_not_scaled(): assert to_value("1.33", "gross_npa_pct", 1e7) == 1.33
def test_dates(): ...  # all six formats → date(2026, 3, 31)
```

- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_numbers.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 7 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): number, unit and date parsing"`.

### Task 4: Checks

**Files:**
- Create: `backend/financials/checks.py`
- Test: `backend/tests/test_fin_checks.py`

**Interfaces:**
- Consumes: `store.Candidate` (Task 1) and `numbers.parse_number` (Task 3).
- Produces:
  - `check_verbatim(c: Candidate, page_text: str) -> str | None`. Returns None if the check passes, otherwise the reason.
    - Compares with whitespace normalised.
    - The printed string must occur as a whole token.
    - Skipped (passes) for `method == "xbrl"`.
  - `check_arithmetic(group: list[Candidate], rounding: float) -> dict[str, str]`. `group` holds the candidates for one company, basis and period. It returns a mapping from metric to reason for those that fail.
    - Rule 1: `revenue_from_operations + other_income == total_income`.
    - Rule 2: `profit_before_tax - tax_expense == net_profit`. This rule is applied only when no exceptional, discontinued or associate line sits between them.
    - Tolerance: one rounding unit times 2.
  - `check_ratio(c: Candidate) -> str | None`. A `pct` value must be between 0 and 100.
  - `check_plausible(c: Candidate, same_metric_other_periods: list[float]) -> str | None`. Rejects a value that differs by more than 100x from the median of the other periods.

- [ ] **Step 1: Write failing tests:**
  - `test_verbatim_matches_parenthesised`: printed `"(625.30)"` is found in `"Net loss (625.30) 412.10"`.
  - `test_verbatim_rejects_absent`.
  - `test_verbatim_not_substring`: `"12.3"` is not found in `"112.35"`.
  - `test_arithmetic_pass_and_fail`.
  - `test_ratio_range`: a `pct` value of 133 fails.
  - `test_plausible_unit_error`: a value 1e5 times the median fails.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_checks.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 6 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): extraction checks"`.

### Task 5: iXBRL extractor

**Files:**
- Create: `backend/financials/ixbrl.py`, `backend/tests/fixtures/financials/indas_q1.html`, `banking_q4.html`, `li_q2.html`
  - Each fixture is trimmed from a real cached file: the header rows plus the rows for the in-scope items and the period columns. All other rows are deleted.
- Test: `backend/tests/test_fin_ixbrl.py`

**Interfaces:**
- Consumes: `metrics_for`, `Candidate`, `parse_date`, `parse_number` and `Source`.
- Produces: `parse_ixbrl(src: Source) -> tuple[list[Candidate], dict]`. The dict is the filings row: `status` plus `reason`, `rounding` and `audited`.
  - Values are rupees as printed ("INR (in Actuals)"), so the multiplier is 1.
  - The quarter column is the "3 months / 6 months ended" column.
  - In Q4 filings only (`period_end` month 3), the "Year to date" column produces an FY row with `period_start` of 1 April of the previous year.
  - Label maps live in this module, one per kind. Each maps lowercase label prefixes to metrics.
- Known labels (from the real files):
  - `Revenue from operations`, `Other income`, `Total income`, `Total expenses`, `Total profit before tax`, `Total tax expenses`, `Total profit (loss) for period`, `Profit or loss, attributable to owners of parent`, `Basic earnings (loss) per share from continuing and discontinued operations`, and the matching `Diluted ...` label.
  - BANKING: `Interest earned`, `% of gross NPAs`, `% of net NPAs`, `Capital adequacy ratio`, `CET 1 ratio`, `Return on assets`.
  - LI: `Gross premium income`, `Net premium income`, `First Year Premium`, `Renewal Premium`, `Single Premium`, `Solvency Ratio`.

- [ ] **Step 1: Write failing tests:**
  - `test_indas_q1_values`: the TATASTEEL Q1 FY26 consolidated fixture gives `revenue_from_operations == 531781200000`, `net_profit == 20073600000` and `eps_basic == 1.67`. It has no FY rows and its basis is `consolidated`.
  - `test_banking_q4_has_fy_and_bank_metrics`: the fixture gives `gross_npa_pct`, `capital_adequacy_pct`, and Q plus FY rows for `net_profit`.
  - `test_li_premiums`.
  - `test_ytd_only_in_q4`: a Q2 file with a YTD column produces no FY rows.
  - `test_all_real_files` (skipped if `data/quarterly/sources.csv` is absent): every iXBRL source parses with status `parsed` and at least 6 "all" metrics.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_ixbrl.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Extend label maps until `test_all_real_files` passes. Every label added goes into the map, never into special cases in code.
- [ ] **Step 4: Run.** Expected: 5 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): iXBRL extractor"`.

### Task 6: Public page-row helper in the chunker

**Files:**
- Modify: `backend/core/pdf_chunker.py`. Add a public wrapper around `_segments` and `_rows`; do not change chunking behaviour.
- Test: `backend/tests/test_chunker.py` (add one test)

**Interfaces:**
- Produces: `page_rows(page) -> list[list[dict]]`. It returns the visual rows of a PyMuPDF page, left to right. Each cell dict has `text`, `x0`, `x1`, `y0`, `y1`, as `_seg` produces them.

- [ ] **Step 1:** Add `test_page_rows_public`: a `make_pdf` page with a 2x3 table gives 2 rows of 3 cells, with the cell texts in order.
- [ ] **Step 2:** Run `venv/Scripts/python -m pytest tests/test_chunker.py -q`. Expected: the new test FAILs (ImportError).
- [ ] **Step 3:** Implement `page_rows` as `_rows(_segments(page.get_text("dict")["blocks"]))`. Filter to text blocks as `_page_elements` already does.
- [ ] **Step 4:** Run the whole chunker test file. Expected: all pass.
- [ ] **Step 5:** Commit with `git commit -m "refactor(chunker): expose page_rows"`.

### Task 7: PDF rules extractor

**Files:**
- Create: `backend/financials/pdf_rules.py`
- Test: `backend/tests/test_fin_pdf_rules.py` (fixtures are built with `tests/pdf_fixtures.make_pdf`)

**Interfaces:**
- Consumes: `page_rows` (Task 6), `unit_multiplier`, `to_value`, `parse_date`, `parse_number` (Task 3), `Candidate` and `Source`.
- Produces:
  - `find_statement_pages(doc, period_end: date) -> list[tuple[int, str]]`. It returns `(page_no, basis)` pairs.
    - A statement page has text matching `financial results` and the quarter-end date.
    - Basis comes from the heading words: "consolidated", otherwise "standalone".
    - A page with no statement heading that directly follows a statement page inherits that page's basis, unit and column positions.
  - `extract_rules(src: Source) -> tuple[list[Candidate], dict[int, str]]`. It returns the candidates and the page text by page number, which the checks and the LLM use.
    - The column is chosen by header text:
      - Q column: a header cell containing "quarter ended", "three months ended" or "3 months ended", plus the period-end date.
      - FY column: a header cell with "year ended" and 31 March, used only when `period_end.month == 3`.
    - Unit comes from the first `unit_multiplier` hit in the page's top rows. If there is none, the page yields nothing.
    - Labels are matched with `LABELS: dict[str, list[str]]`, which maps a metric to its synonyms, compared on a lowercase, whitespace-collapsed prefix.
    - `printed` is the cell text, and `page` is 1-based.

- [ ] **Step 1: Write failing tests:**
  - `test_basic_crore_statement`: a crore header and a Q column give `revenue_from_operations == 1234.5e7`.
  - `test_lakh_unit`.
  - `test_no_unit_header_yields_nothing`.
  - `test_two_bases_in_one_pdf`: a standalone page and a consolidated page give both bases with the right values.
  - `test_column_by_header_not_position`: the Q column is the second numeric column.
  - `test_q4_quarter_vs_year_columns`: a 31.03.2026 quarter column and a year column give a Q row and an FY row with different values.
  - `test_continued_page_keeps_column_and_unit`: EPS sits on page 2, which has no header.
  - `test_eps_unscaled_in_pdf`.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_pdf_rules.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 8 passed. Then run a coverage probe over the real PDFs: `venv/Scripts/python -m financials.pdf_rules --probe`. It prints, for each file, the statement pages found and the metrics filled. Record the totals in the ledger. They are not a gate; Task 9 measures them.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): rule-based PDF extractor"`.

### Task 8: LLM fallback

**Files:**
- Create: `backend/financials/pdf_llm.py`
- Test: `backend/tests/test_fin_pdf_llm.py`

**Interfaces:**
- Consumes: `Candidate`, `Source`, `METRICS` and `settings` (`config.py`: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`).
- Produces:
  - `PROMPT_VERSION = "1"`.
  - `extract_llm(src: Source, pages: dict[int, str], want: list[tuple[str, str, str]], cache_dir: Path, client=None) -> list[Candidate]`.
    - `want` is a list of `(basis, period_type, metric)`.
    - The prompt includes only the statement pages.
    - The model returns JSON in the form `{"items":[{"basis","period_type","metric","printed","column_header","unit_header","page"}]}`.
    - The value comes from `to_value(printed, metric, unit_multiplier(unit_header))`, with `method="llm"`.
    - The cache file is `cache_dir/<sha256>_<PROMPT_VERSION>_<hash of want>.json`. A cache hit makes no client call.
    - `client` defaults to an `openai.OpenAI` built from settings. Tests inject a fake.
  - The cache directory is `backend/index_cache/financials_llm_cache/`, which is gitignored with the rest of `index_cache/`.

- [ ] **Step 1: Write failing tests:**
  - `test_parses_fake_response` (fake client returns fixed JSON).
  - `test_cache_hit_skips_client` (a second call gives a client call count of 1).
  - `test_unknown_metric_dropped`.
  - `test_missing_unit_header_dropped`.
  - `test_only_statement_pages_sent`: the fake records its prompt, and a non-statement page's text is absent from it.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_pdf_llm.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Use `response_format={"type": "json_object"}` and `temperature=0`.
- [ ] **Step 4: Run.** Expected: 5 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): LLM fallback with disk cache"`.

### Task 9: Build command

**Files:**
- Create: `backend/financials/build.py`
- Test: `backend/tests/test_fin_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `build(sources_dir: Path, out_db: Path, use_llm: bool = True, client=None) -> dict`. It returns a summary with the keys `files, parsed, partial, failed, rows, review, llm_calls, llm_cached`.
  - CLI: `python -m financials.build [--no-llm]`. Paths default to `data/quarterly` and `index_cache/financials.duckdb`, and it prints the summary.
- Flow for each source:
  - iXBRL: parse, then run `check_ratio`.
  - PDF:
    1. Run `extract_rules`.
    2. Check each candidate with verbatim, ratio and arithmetic (grouped by company, basis and period).
    3. Collect the missing or failed `(basis, period_type, metric)` triples, using `metrics_for` with the kind inferred from `sources.csv` (most recent iXBRL kind for that symbol; INDAS if none).
    4. Call `extract_llm` for those triples, at most once per file.
    5. Re-check the results.
  - Across all rows: run `check_plausible`, then `write_db`.
  - A file whose extraction raises becomes a `filings` row with status `failed` and the reason. The build continues.
  - Status rules:
    - `parsed` means at least 6 "all" metrics for some basis.
    - `partial` means at least 1.
    - `failed` means none.

- [ ] **Step 1: Write failing tests:**
  - `test_build_fixture_corpus(tmp_path)`: one iXBRL fixture, one rules-only PDF fixture, and one PDF where a metric needs the fake LLM. Expect `rows > 0`, the fixture metric present with `method == "llm"`, and `failed == 0`.
  - `test_llm_value_failing_verbatim_goes_to_review`.
  - `test_broken_file_is_failed_not_fatal`.
  - `test_no_llm_flag`: the fake client is never called.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_build.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 4 passed. Then run the real build: `PYTHONIOENCODING=utf-8 venv/Scripts/python -m financials.build`. Expected: `files 372` and `failed` at most 1 (SBIN 2025-03 is image-only). Record the summary in the ledger.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): build command"`.

### Task 10: Read API

**Files:**
- Create: `backend/financials/query.py`
- Test: `backend/tests/test_fin_query.py`

**Interfaces:**
- Produces:
  - `Row` is a dataclass with `company, basis, period_type, period_end, fiscal_year, fiscal_quarter, metric, value, unit, source_url, source_file, page, method`.
  - `get_metric(company, metric, basis="consolidated", period_type="Q", start: date | None = None, end: date | None = None, db: str = DEFAULT_DB) -> list[Row]`. Rows are ordered by `period_end`.
  - `available(company, db=DEFAULT_DB) -> dict[str, list[str]]` maps each metric to its ISO period ends.
  - The database is opened read-only.

- [ ] **Step 1: Write failing tests** against a db built with `write_db` in tmp:
  - `test_ordered_by_period`.
  - `test_no_standalone_substitution`: a company with only standalone rows gives `get_metric(...basis="consolidated") == []`.
  - `test_fy_filter`.
  - `test_available`.
- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_fin_query.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 4 passed.
- [ ] **Step 5: Commit** with `git commit -m "feat(financials): read API"`.

### Task 11: Answer key and accuracy report

**Files:**
- Create: `backend/tests/financials_golden.json`, `backend/tests/eval_financials.py`, `backend/tests/test_fin_golden.py`
- Modify: `backend/tests/eval_reports/README.md` (add a "Financials" results table)

**Interfaces:**
- Golden format: `{"version": 1, "changelog": [], "cases": [...]}`. Each case is `{"id", "company", "period_end", "period_type", "basis", "source_file", "page", "values": {metric: value}, "checked_by": [...]}`.
  - Values are in stored units: rupees, %, ratio, or INR per share.
- `eval_financials.py --db PATH --label NAME` writes `tests/eval_reports/<timestamp>-<label>-financials.json` and prints a table.
  - **Precision:** stored values within one rounding unit of the key, divided by the key values that are stored.
  - **Coverage:** key values that are stored, divided by all key values.
  - Both are reported overall, by method and by group.

- [ ] **Step 1: Write `test_fin_golden.py`:**
  - `test_schema`.
  - `test_spread`: at least 20 PDF cases and 5 iXBRL cases. At least 4 bank, 2 insurer and 3 NBFC cases. At least 8 companies with distinct layouts.
  - `test_fully_checked`: every case has `checked_by == ["claude", "user", "claude-recheck"]`.
- [ ] **Step 2: Draft the key** by reading the PDFs and HTML directly, never from `financials.duckdb` output. Choose cases before running any eval. Mark them `["claude"]`.
- [ ] **Step 3: STOP. The user spot-checks the key.** Then re-check every case against its source and set `checked_by` to the full list. This is a hard stop: do not run the eval until it is done.
- [ ] **Step 4: Run** `venv/Scripts/python -m pytest tests/test_fin_golden.py -q`. Expected: 3 passed. Then run `PYTHONIOENCODING=utf-8 venv/Scripts/python -m tests.eval_financials --db index_cache/financials.duckdb --label v1`.
  - Gate: precision of at least 99%, coverage of at least 90% for "all" and at least 80% for bank/insurer.
  - Below the gate, fix label maps or rules (never the key), rebuild and re-run. Log each iteration in the README table.
- [ ] **Step 5: Run the full suite** with `venv/Scripts/python -m pytest -q --ignore=tests/quick_test.py`. Expected: all pass.
- [ ] **Step 6: Commit** the key, eval and README with `git commit -m "eval(financials): answer key and accuracy report"`.
