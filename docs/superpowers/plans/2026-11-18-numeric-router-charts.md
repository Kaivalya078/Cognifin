# Numeric Router, Charts and Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Questions that ask for a company + metric + period get verified figures from `financials.duckdb`, cited as `[fin_N]`, checked after generation, and drawn as a chart whose points open the filing.

**Architecture:** A rule-based router (`financials/router.py`) turns a question plus the already-parsed companies/years into a `Lookup` of table rows. `financials/present.py` turns that into a context block, evidence items and chart data, and `financials/numcheck.py` post-checks the answer. `answer_question` in `backend/main.py` calls `prepare()` before generation and `finish()` after. RAG always runs, so a miss gives today's behaviour. The frontend adds a Recharts component.

**Tech Stack:** Python 3.13, FastAPI, DuckDB (existing), pytest; React 19 + Vite, Recharts (new).

**Spec:** `docs/superpowers/specs/2026-11-18-numeric-router-charts-design.md`

## Global Constraints

- No new backend dependencies. The frontend adds only `recharts`, at a version that supports React 19 (3.x).
- Metrics must be names from `financials/metrics.py` `METRICS`. Never add metrics.
- Table coverage: Q period ends 2025-03-31..2026-09-30 (7), FY ends 2025-03-31 and 2026-03-31. Indian FY: Q1 ends Jun 30; FY26 = 2025-04-01..2026-03-31; Sep 2026 = Q2 FY27.
- A chart point's value equals a table row's value converted to the display unit (INR ÷ 1e7 → ₹ crore), and nothing else.
- Never mix bases in one series. Per-series `metric`, `label` and `basis`. All series in a chart share `unit`.
- A router miss (`None`) must leave `answer_question` output identical to today's, apart from `metadata.router = {"hit": false}` and `metadata.chart = None`.
- Run backend tests from `backend/` with `venv/Scripts/python.exe -m pytest`. Don't grep `backend/` recursively without excluding `venv/` (it hangs).

## Deviation from the spec (decided while planning)

- **Click target:** results PDFs live on bseindia.com and iXBRL files on nseindia.com. Neither is served by our backend, and pdf.js in `PDFViewerModal` would hit CORS fetching them. So chart points and `fin` evidence items open `source_url` in a new tab, with `#page=N` appended for PDFs (browsers' built-in viewers honour it). Task 6 updates the spec line.

## Review Focus

1. **Numbers in an answer that aren't figures** (years, "Q2", "FY26", growth %, counts) must not appear in `unmatched`. Pinned in Task 4: `test_ignores_years_quarters_and_growth_pct`.
2. **A bank asked for "revenue" in a comparison with a non-bank** should give two series with different metrics and an honest label, not an empty result. Pinned in Task 2: `test_bank_revenue_maps_to_interest_earned_per_company`.
3. **A question naming a company that isn't in the table** (e.g. an uploaded-doc company) along with a table company: the router uses the one it has and lists the other as missing. Pinned in Task 2: `test_unknown_company_listed_missing`.
4. **"Sep 2026" also puts "2026" into `years`**, which must not add an FY26 row. Pinned in Task 1: `test_specific_period_beats_bare_year`.
5. **A conversation reloaded from Mongo** must still show its chart. Pinned in Task 6 (persist test) and checked by hand in Task 7.

---

### Task 1: Period parser

**Files:**
- Create: `backend/financials/router.py`
- Test: `backend/tests/test_fin_router.py`

**Interfaces:**
- Produces: `PeriodSpec` dataclass `(period_type: str, ends: list[date] | None = None, last_n: int | None = None)`. `ends=None, last_n=None` means "all periods of that type". `parse_periods(question: str, years: list[str]) -> PeriodSpec`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from financials.router import PeriodSpec, parse_periods

def test_quarter_fy_forms():
    for q in ["Q2 FY27", "q2fy27", "Q2 FY2027", "Q2 of FY27"]:
        assert parse_periods(f"TCS profit {q}", []) == PeriodSpec("Q", [date(2026, 9, 30)])
    assert parse_periods("Q4 FY26", []) == PeriodSpec("Q", [date(2026, 3, 31)])
    assert parse_periods("Q1 FY26", []) == PeriodSpec("Q", [date(2025, 6, 30)])

def test_month_forms():
    for m in ["Sep 2026", "September 2026", "Sept 2026", "quarter ended 30 Sep 2026", "Sep-2026", "Sep'26"]:
        assert parse_periods(f"profit {m}", ["2026"]) == PeriodSpec("Q", [date(2026, 9, 30)])
    assert parse_periods("profit Dec 2025 and Mar 2026", []) == PeriodSpec("Q", [date(2025, 12, 31), date(2026, 3, 31)])
    assert parse_periods("profit Aug 2026", []).ends is None   # not a quarter end → ignored

def test_fy_forms():
    for f in ["FY25", "FY2025", "FY 25", "2024-25", "fiscal 2025"]:
        assert parse_periods(f"revenue {f}", []) == PeriodSpec("FY", [date(2025, 3, 31)])

def test_last_n_and_trend_and_default():
    assert parse_periods("last 4 quarters revenue", []) == PeriodSpec("Q", last_n=4)
    assert parse_periods("latest quarter revenue", []) == PeriodSpec("Q", last_n=1)
    assert parse_periods("revenue trend", []) == PeriodSpec("Q")
    assert parse_periods("TCS revenue", []) == PeriodSpec("Q")

def test_specific_period_beats_bare_year():
    assert parse_periods("profit Q2 FY2026", ["2026"]) == PeriodSpec("Q", [date(2025, 9, 30)])
    assert parse_periods("profit in 2026", ["2026"]) == PeriodSpec("FY", [date(2026, 3, 31)])
    assert parse_periods("profit 2025 vs 2026", ["2025", "2026"]) == PeriodSpec("FY", [date(2025, 3, 31), date(2026, 3, 31)])

def test_mixed_types_first_match_wins():
    assert parse_periods("FY26 and Q2 FY27", []).period_type == "FY"
```

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_fin_router.py -v`. Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `parse_periods` in `backend/financials/router.py`**

Collect regex matches for the Q-FY, month, FY and "fiscal YYYY" forms with their positions. Mask each Q-FY span before running the FY regex, so "Q2 FY27" doesn't also yield FY27. Two-digit years mean 20YY. The type of the earliest match decides `period_type`, and the `ends` of that type are kept sorted and de-duplicated. If nothing matched, check `last N quarters` / `latest|last quarter`, then fall back to the bare `years` (→ FY ends Mar 31), then `PeriodSpec("Q")`. Quarter end for Qn FYyy: Q1 → Jun 30 of yy-1, Q2 → Sep 30 of yy-1, Q3 → Dec 31 of yy-1, Q4 → Mar 31 of yy.

- [ ] **Step 4: Run the tests.** Expected: PASS.

- [ ] **Step 5: Commit** `git add backend/financials/router.py backend/tests/test_fin_router.py && git commit -m "feat(router): period parser for quarter, month and FY forms"`

---

### Task 2: Metric detection and `route()`

**Files:**
- Modify: `backend/financials/router.py`
- Test: `backend/tests/test_fin_router.py`

**Interfaces:**
- Consumes: `PeriodSpec`, `parse_periods` (Task 1); `financials.query.get_metric`, `available`, `Row`, `DEFAULT_DB`.
- Produces:
  - `detect_metrics(question: str) -> list[str]`: canonical metrics in order of first appearance, de-duplicated, max 3.
  - `@dataclass Series(company: str, metric: str, requested: str, basis: str, rows: list[Row])`. `requested` is the metric before bank mapping.
  - `@dataclass Lookup(metrics: list[str], period: PeriodSpec, series: list[Series], missing: list[str])`.
  - `route(question: str, companies: list[str], years: list[str], db: str = DEFAULT_DB) -> Lookup | None`.

- [ ] **Step 1: Write the failing tests** (build a fixture DB with `financials.store.write_db` and a `_c` helper, as `tests/test_fin_query.py` does, with `source_url="https://bse/x.pdf"` and page 2: TCS consolidated net_profit for quarters ending 2025-06-30, 2025-09-30 and 2025-12-31 with values 1.0, 2.0 and 3.0, plus FY 2026-03-31; ITC standalone-only net_profit; HDFCBANK interest_earned for 2 quarters; RELIANCE 1 consolidated + 3 standalone revenue quarters).

```python
def test_aliases():
    assert detect_metrics("What was TCS's PAT?") == ["net_profit"]
    assert detect_metrics("sales and EPS") == ["revenue_from_operations", "eps_basic"]
    assert detect_metrics("diluted EPS") == ["eps_diluted"]
    assert detect_metrics("gross NPA and CET1") == ["gross_npa_pct", "cet1_pct"]
    assert detect_metrics("profit before tax") == ["profit_before_tax"]   # not net_profit too
    assert detect_metrics("net profit margin") == []   # margin is ambiguous → nothing
    assert detect_metrics("NIM and ROE") == []

def test_route_basic(db):
    lk = route("TCS net profit trend", ["TCS"], [], db=db)
    assert [s.company for s in lk.series] == ["TCS"] and lk.series[0].basis == "consolidated"
    assert len(lk.series[0].rows) == 3 and lk.missing == []

def test_route_none_cases(db):
    assert route("TCS strategy", ["TCS"], [], db=db) is None        # no metric
    assert route("net profit", [], [], db=db) is None                # no company
    assert route("TCS net profit Q1 FY24", ["TCS"], [], db=db) is None   # period not in table

def test_standalone_fallback_and_more_rows_wins(db):
    assert route("ITC net profit", ["ITC"], [], db=db).series[0].basis == "standalone"
    assert route("RELIANCE revenue", ["RELIANCE"], [], db=db).series[0].basis == "standalone"
    assert route("RELIANCE consolidated revenue", ["RELIANCE"], [], db=db).series[0].basis == "consolidated"

def test_bank_revenue_maps_to_interest_earned_per_company(db):
    lk = route("HDFCBANK vs RELIANCE revenue", ["HDFCBANK", "RELIANCE"], [], db=db)
    by = {s.company: s for s in lk.series}
    assert by["HDFCBANK"].metric == "interest_earned" and by["HDFCBANK"].requested == "revenue_from_operations"
    assert by["RELIANCE"].metric == "revenue_from_operations"

def test_unknown_company_listed_missing(db):
    lk = route("TCS vs ACME net profit", ["TCS", "ACME"], [], db=db)
    assert [s.company for s in lk.series] == ["TCS"] and lk.missing == ["ACME"]

def test_fy_and_last_n(db):
    assert [r.period_type for r in route("TCS net profit FY26", ["TCS"], [], db=db).series[0].rows] == ["FY"]
    assert len(route("TCS net profit last 2 quarters", ["TCS"], [], db=db).series[0].rows) == 2
```

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement** `_ALIASES` (phrase → metric; seed list in spec §1, extend as tests need), `detect_metrics` (case-insensitive, word boundaries, longest phrase first, and mask matched spans so "profit before tax" doesn't also fire "profit"; a phrase in `_AMBIGUOUS = {"margin", "nim", "roe", "growth"}` masks its surrounding phrase, e.g. "net profit margin" yields nothing), and `route`.

  For each company and requested metric: if the company has `interest_earned` rows (`available()`) and the requested metric is `revenue_from_operations`, use `interest_earned`. Candidate bases: only the one named in the question if "standalone"/"consolidated" appears, otherwise both. Rows come from `get_metric` filtered by `PeriodSpec` (`ends` → keep matching period_ends; `last_n` → last n; else all). Pick the basis with more rows, ties going to consolidated. A company with zero rows for every metric goes to `missing`. If no series at all, return `None`.

- [ ] **Step 4: Run** the whole file. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -am "feat(router): metric aliases and per-company route()"` (add the test file if new hunks are untracked).

---

### Task 3: Context block, evidence and chart (`present.py`)

**Files:**
- Create: `backend/financials/present.py`
- Test: `backend/tests/test_fin_present.py`

**Interfaces:**
- Consumes: `Lookup`, `Series`, `route` (Task 2).
- Produces:
  - `fmt_value(value: float, unit: str) -> str`: INR → `"₹1,221.0 crore"`, pct → `"1.23%"`, ratio → `"1.85×"`, INR_per_share → `"₹12.34"`.
  - `period_label(row) -> str`: `"Q2 FY27"` / `"FY26"` (from `row.fiscal_year`, `row.fiscal_quarter`).
  - `@dataclass Prepared(lookup: Lookup, ids: dict[str, tuple[Series, Row]], block: str, evidence: list[dict])`.
  - `prepare(question: str, companies: list[str], years: list[str], db: str = DEFAULT_DB) -> Prepared | None`.
  - `build_chart(prep: Prepared) -> dict | None`.
  - `finish(prep: Prepared | None, answer: str) -> dict`: returns `{"router": {...}, "chart": ..., "numbers_check": ...}`. Uses `check_numbers` from Task 4, so in this task `finish` sets `numbers_check` to `None` and Task 4 fills it in.

- [ ] **Step 1: Write the failing tests** (reuse the Task 2 fixture shape; move `_c` and the db fixture into `tests/conftest.py` as `fin_db` if both files need it).

```python
def test_fmt_value():
    assert fmt_value(12209900000.0, "INR") == "₹1,221.0 crore"
    assert fmt_value(1.234, "pct") == "1.23%" and fmt_value(1.85, "ratio") == "1.85×"
    assert fmt_value(12.3, "INR_per_share") == "₹12.30"

def test_block_and_ids(fin_db):
    p = prepare("TCS vs ACME net profit", ["TCS", "ACME"], [], db=fin_db)
    assert list(p.ids) == ["fin_1", "fin_2", "fin_3"]          # series order, then period order
    assert p.block.startswith("VERIFIED FIGURES")
    assert "authoritative" in p.block and "not in verified table: ACME" in p.block
    assert "[fin_1] TCS | net_profit | Q1 FY26 | consolidated |" in p.block

def test_evidence_items(fin_db):
    e = prepare("TCS net profit", ["TCS"], [], db=fin_db).evidence[0]
    assert e["chunk_id"] == "fin_1" and e["pdf_url"].startswith("https://")
    assert e["page_number"] == 2 and e["document_label"].startswith("TCS results")

def test_chart_shape(fin_db):
    c = build_chart(prepare("TCS net profit", ["TCS"], [], db=fin_db))
    assert c["unit"] == "INR" and c["display_unit"] == "₹ crore" and c["period_type"] == "Q"
    s = c["series"][0]
    assert s["company"] == "TCS" and s["metric"] == "net_profit" and s["basis"] == "consolidated"
    assert [p["fin_id"] for p in s["points"]] == ["fin_1", "fin_2", "fin_3"]
    assert s["points"][0]["value"] == 1.0 / 1e7 and s["points"][0]["label"] == "Q1 FY26"

def test_no_chart_for_single_point(fin_db):
    assert build_chart(prepare("TCS net profit Q2 FY26", ["TCS"], [], db=fin_db)) is None

def test_chart_first_metric_only_and_series_name(fin_db):
    c = build_chart(prepare("HDFCBANK vs RELIANCE revenue and EPS", ["HDFCBANK", "RELIANCE"], [], db=fin_db))
    assert {s["requested"] for s in c["series"]} == {"revenue_from_operations"}
    assert any(s["name"] == "HDFCBANK (interest earned)" for s in c["series"])

def test_finish_miss():
    assert finish(None, "x") == {"router": {"hit": False}, "chart": None, "numbers_check": None}
```

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests/test_fin_present.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** Block header, exact text:
  `VERIFIED FIGURES (from company filings; these are authoritative — use these numbers exactly, prefer them over chunk text for the same metric and period, and cite [fin_N]):`
  Line format: `[fin_N] COMPANY | metric | PERIOD | basis | VALUE | SOURCE`, where SOURCE is `BSE results filing p.N` for PDFs and `NSE iXBRL filing` for `.html`.
  Series `name`: company, plus ` (<metric words>)` if the metric differs from `requested`, plus ` (standalone)` for standalone.
  Point keys: `period_end` (ISO), `label`, `value`, `source_url`, `page`, `fin_id`, `method`.
  Evidence `document_label`: `"{company} results {period_label}"`, and `page_number = row.page or 0`.
  `finish` hit: `router = {"hit": True, "metrics": lookup.metrics, "rows": len(ids), "missing": lookup.missing}`.

- [ ] **Step 4: Run.** Expected: PASS.

- [ ] **Step 5: Commit** `git add backend/financials/present.py backend/tests/test_fin_present.py backend/tests/conftest.py && git commit -m "feat(router): context block, evidence items and chart payload"`

---

### Task 4: Numbers post-check

**Files:**
- Create: `backend/financials/numcheck.py`
- Modify: `backend/financials/present.py` (`finish` fills `numbers_check`)
- Test: `backend/tests/test_fin_numcheck.py`

**Interfaces:**
- Consumes: `Prepared.ids` (Task 3).
- Produces: `check_numbers(answer: str, ids: dict[str, tuple[Series, Row]]) -> dict` → `{"checked": int, "unmatched": list[str]}`.

- [ ] **Step 1: Write the failing tests** (`ids` built by hand: one INR row of 12209900000.0 and one pct row of 1.23).

```python
def test_match_crore_lakh_and_plain_table_cell():
    assert check_numbers("Profit was ₹1,221.0 crore [fin_1].", IDS) == {"checked": 1, "unmatched": []}
    assert check_numbers("Profit was ₹1,22,099 lakh [fin_1].", IDS)["unmatched"] == []
    assert check_numbers("| Q2 FY27 | 1,221 | [fin_1] |", IDS)["unmatched"] == []   # bare INR cell = crore

def test_mismatch_flagged():
    assert check_numbers("Profit was ₹1,500 crore [fin_1].", IDS)["unmatched"] == ["₹1,500 crore"]

def test_pct_tolerance():
    assert check_numbers("GNPA was 1.2% [fin_2].", IDS)["unmatched"] == []
    assert check_numbers("GNPA was 1.4% [fin_2].", IDS)["unmatched"] == ["1.4%"]

def test_ignores_years_quarters_and_growth_pct():
    ids_inr_only = {"fin_1": IDS["fin_1"]}
    r = check_numbers("In Q2 FY27 (Sep 2026) profit rose 12% to ₹1,221 crore [fin_1].", ids_inr_only)
    assert r == {"checked": 1, "unmatched": []}

def test_uncited_sentences_ignored():
    assert check_numbers("Capex was ₹9,999 crore [chunk_4]. Profit ₹1,221 crore [fin_1].", IDS)["checked"] == 1
```

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement.** Split the answer into lines, and split non-table lines (those not starting with `|`) into sentences on `(?<=[.!?])\s+`. Keep only segments that contain `fin_\d+`. Strip `fin_N`/`chunk_N`, `Q[1-4]`, `FY\d{2,4}`, month+year, and bare 19xx/20xx years. Then extract numbers with an optional ₹ and a unit (`crore|cr|lakh|lakhs|billion|bn|million|mn|%|x|×`). Convert to a row's native unit: crore 1e7, lakh 1e5, billion 1e9, million 1e6. A unitless number counts as crore when compared with an INR row and as-is otherwise. A `%` number is checked only if some row has unit `pct`. A match is any row with relative difference ≤ 0.5% (INR) or absolute ≤ 0.05 (pct/ratio/INR_per_share). Report unmatched tokens as written. Add a `# ponytail:` comment: a regex heuristic; an LLM claim extractor if false flags show up in the eval.

- [ ] **Step 4: Run** `tests/test_fin_numcheck.py tests/test_fin_present.py`. Expected: PASS (update `test_finish_miss` only if its shape changed; it shouldn't).

- [ ] **Step 5: Commit** `git commit -m "feat(router): post-check answer numbers against cited rows"` (with the new files added).

---

### Task 5: Accept `fin_N` citations

**Files:**
- Modify: `backend/core/citation_verifier.py:24,58`, `backend/generation/prompt_builder.py:185`
- Test: `backend/tests/test_citations.py`

**Interfaces:**
- Produces: `extract_citations` and `verify_citations` accept `fin_N` ids in `chunk_ids`. `bare_chunk_id("fin_3") == "fin_3"`.

- [ ] **Step 1: Add failing tests** to `tests/test_citations.py`:

```python
def test_fin_ids_are_citations():
    ids = IDS + ["fin_1", "fin_12"]
    ans = "Profit ₹1,221 crore [fin_1]. Revenue [fin_12]. Bogus [fin_9]."
    assert extract_citations(ans, ids) == ["fin_1", "fin_12"]
    r = verify_citations(ans, ids)
    assert r["invalid_citations"] == ["fin_9"] and {"fin_1", "fin_12"} <= set(r["valid_citations"])
```

- [ ] **Step 2: Run** `tests/test_citations.py`. Expected: the new test FAILs and the old ones pass.
- [ ] **Step 3: Implement.** `_REF = re.compile(r"\b(?:chunk|fin)_\d+\b")` in `citation_verifier.py`. Use `_REF.findall` at line 58, and import `_REF` in `prompt_builder.py` for line 185 (one regex, not three).
- [ ] **Step 4: Run** the full suite `venv/Scripts/python.exe -m pytest -q`. Expected: all green (287 + new).
- [ ] **Step 5: Commit** `git commit -am "feat(citations): accept fin_N ids from the verified-figures block"`

---

### Task 6: Wire into `answer_question` and persistence

**Files:**
- Modify: `backend/main.py` (`answer_question` ~723–862, `persist_exchange` ~866)
- Modify: `docs/superpowers/specs/2026-11-18-numeric-router-charts-design.md` (§5 click target → the deviation above)
- Test: `backend/tests/test_fin_present.py` (persist shape), manual `/chat` check

**Interfaces:**
- Consumes: `prepare`, `finish` (Tasks 3–4).
- Produces: `/chat` response `metadata.router`, `metadata.chart`, `metadata.numbers_check`. Mongo assistant message `metadata.pipeline = {"chart": ..., "numbers_check": ...}`, which is the same path the frontend reads live (`message.metadata.pipeline.chart`).

- [ ] **Step 1: Extract a testable helper and write a failing test.** Add `assistant_metadata(payload: dict) -> dict` to `financials/present.py`. It returns `{"citations": …, "evidence": …, "pipeline": {"chart": payload["metadata"].get("chart"), "numbers_check": payload["metadata"].get("numbers_check")}}`. Test:

```python
def test_assistant_metadata_keeps_chart():
    p = {"citations": ["fin_1"], "evidence": [], "metadata": {"chart": {"series": []}, "numbers_check": None}}
    assert assistant_metadata(p)["pipeline"]["chart"] == {"series": []}
```

- [ ] **Step 2: Run.** Expected: FAIL. Then implement it and run again. Expected: PASS.

- [ ] **Step 3: Wire `main.py`.**
  - After each of the three retrieval branches, get `companies, years`: session/global paths from `parsed` (object or dict; `getattr`/`.get` as the existing intent line does), intelligent path from `iq.companies`/`iq.years`.
  - `fin = prepare(question, companies, years)`.
  - If `fin`: `context = fin.block + "\n\n" + context` and `chunk_ids = chunk_ids + list(fin.ids)` before the prompt is built.
  - After the evidence list is built, append `EvidenceItem(**e).model_dump() for e in fin.evidence`.
  - `metadata.update(finish(fin, answer))`.
  - `persist_exchange` uses `assistant_metadata(payload)`.
  - Wrap `prepare` in try/except that logs and continues with `fin = None`. A DuckDB problem must never fail a chat.
- [ ] **Step 4: Full suite** `venv/Scripts/python.exe -m pytest -q`. Expected: all green.
- [ ] **Step 5: Manual check.** Start the backend (`venv/Scripts/python.exe -m uvicorn main:app --port 8000`) and POST `/chat` with `{"question": "ADANIENT net profit trend"}`. Expected: `metadata.router.hit == true`, `metadata.chart.series[0].points` has 7 points equal to the DB rows ÷ 1e7, and the answer cites `fin_`. Then `{"question": "What is ADANIENT's strategy?"}`. Expected: `router.hit == false`, `chart == null`.
- [ ] **Step 6: Update the spec §5 click-target line, then commit** `git commit -am "feat(router): wire verified figures into answer_question and persistence"`

---

### Task 7: Frontend chart

**Files:**
- Modify: `frontend/package.json` (via `npm install recharts@^3`)
- Create: `frontend/src/components/chat/FinancialChart.jsx`
- Modify: `frontend/src/components/chat/MessageList.jsx` (render under the answer; `EvidenceChunk` opens `fin_` items / non-PDF-served URLs in a new tab)

**Interfaces:**
- Consumes: `message.metadata.pipeline.chart` and `.numbers_check` (Task 6 shape).
- Produces: `<FinancialChart chart={…} numbersCheck={…} />`.

- [ ] **Step 1: Install** `npm install recharts@^3` in `frontend/`. Expected: added to `dependencies`, no peer-dep errors with React 19.
- [ ] **Step 2: Implement `FinancialChart.jsx`.** Choose the chart type: every series has 1 point → grouped `BarChart` (x = company); otherwise `LineChart` (x = period label, one `Line` per series, `connectNulls`). Y axis title = `display_unit`. Tooltip shows series name, label, value (2 dp) and `method`. Clicking a point/bar runs `window.open(source_url + (page ? '#page=' + page : ''), '_blank', 'noopener')`. If `numbersCheck?.unmatched?.length`, show one muted line: `N number(s) in this answer didn't match the verified table: …`. Use the existing CSS variables from `chat.css`, no new palette. `ResponsiveContainer` height 260, so it fits at 375 px wide.
- [ ] **Step 3: Render it** in `MessageList.jsx` after the answer markdown and before the evidence toggle, when `pipeline.chart` exists. In `EvidenceChunk`, if `item.chunk_id.startsWith('fin_')`, the "Open PDF" button opens the URL in a new tab instead of `PDFViewerModal`.
- [ ] **Step 4: Verify.** `npm run build` (no errors) and `npm run lint` (no new errors). With the backend from Task 6 running and `npm run dev`, ask "ADANIENT net profit trend": a line chart with 7 points appears, the tooltip values match the `/chat` JSON, and clicking a point opens the BSE/NSE filing. Ask "HDFCBANK vs ICICIBANK gross NPA Q2 FY27": a grouped bar chart. Reload the conversation from the sidebar: the chart is still there. Check at 375 px width: no horizontal scroll.
- [ ] **Step 5: Commit** `git add frontend/package.json frontend/package-lock.json frontend/src/components/chat/FinancialChart.jsx frontend/src/components/chat/MessageList.jsx && git commit -m "feat(chat): Recharts financial chart from verified rows"`

---

### Task 8: Phase 4 eval

**Files:**
- Create: `backend/tests/router_golden.json`, `backend/tests/eval_router.py`
- Modify: `backend/tests/eval_reports/README.md` (new "Numeric router" section)

**Interfaces:**
- Consumes: `main.answer_question` (Task 6), `financials.query.get_metric`.

- [ ] **Step 1: Write `router_golden.json`** with ~40 router-only cases, `{"q", "companies", "years", "expect": {"companies", "metric", "period_type", "n_rows"} | null}`, drawn from real companies in the table. Include each alias group, each period form, a bank, an insurer, ambiguous terms → null, out-of-range → null, and 3 comparisons. Mark 15 of them `"e2e": true`.
- [ ] **Step 2: Write `eval_router.py`.** Part 1 (no LLM): run `route()` on every case and report hit rate and exact-match accuracy. Part 2 (`--e2e`, needs the LLM key): run `answer_question` on the e2e cases and assert:
  - every chart point value == `get_metric` row value ÷ 1e7 (or the raw value for non-INR)
  - report `numbers_check.unmatched` counts
  - each comparison's citations cover every company (a `fin` id from that company or a `chunk` whose evidence label names it)

  Print a markdown table.
- [ ] **Step 3: Run** `venv/Scripts/python.exe tests/eval_router.py` and then `--e2e`. Expected: Part 1 exact-match ≥ 90%; Part 2 has zero chart-value mismatches. Fix router aliases/regex for misses (re-run Tasks 1–2 tests after each fix). Report `unmatched` honestly; don't tune it to zero by loosening the tolerance.
- [ ] **Step 4: Add the results table** to `tests/eval_reports/README.md`, with date, hit rate, accuracy, chart mismatches and unmatched-number count.
- [ ] **Step 5: Commit** `git add backend/tests/router_golden.json backend/tests/eval_router.py backend/tests/eval_reports/README.md && git commit -m "eval(router): routing accuracy and end-to-end chart checks"`
