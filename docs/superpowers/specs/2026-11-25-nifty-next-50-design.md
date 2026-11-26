# Phase 5.5: NIFTY Next 50 Corpus Expansion

## Intent

Phase 5.5 roughly doubles coverage before deploy, so the public demo launches with the **NIFTY 100**: the NIFTY 50 already indexed plus the NIFTY Next 50. It uses the same method as Phase 3:
- Filings are found in-session from public sources only: NSE's public iXBRL archive files, company annual-report PDFs, and BSE filing PDFs linked from Screener.
- No paid source and no undocumented API.
- The existing parsers, the `financials` build and the index builder take the filings in.
- The evals run again afterwards.

Companies outside the corpus keep the existing "upload its annual report" card.

## Decided with the user

- **Depth per new company (option B):** the FY2025 and FY2026 annual reports, plus the same 7 quarters as the financials table (Q Mar-2025 to Sep-2026, with FY25/FY26 taken from Q4).

  This differs from the NIFTY 50, which has FY2023–FY2026 annual reports. The reason is storage: R2's free tier is 10 GB.
- **Pre-FY2025 questions about a Next 50 company (user chose A, allow):** the FY2025 annual report prints prior-year figures, and `core/corpus_manager.py::_relaxations` already drops an unindexed year filter for the same company. So an "FY2024 revenue" question is answered and cited from the FY2025 report. No per-company year check is added. `/engineering` and the eval README say "Next 50: FY2025 onward, with prior-year figures from those reports".
- **Financials precision for the Next 50 (user chose A):**
  - About 10 Next 50 filings are added to `tests/financials_golden.json`.
  - Each value is verified against its source page, as Phase 3 did.
  - The user spot-checks 5 of them in the same sitting as the golden-set check.
  - The CI financials gate then runs on the whole key. Re-pin `--min-coverage` to the new whole-key result, and ledger the old and new values.
- **Collection method (option A, the Phase 3 replay):**
  1. Quarterly iXBRL files come from `nsearchives.nseindia.com/corporate/ixbrl/…`, discovered by web search.
  2. Annual reports come from company investor-relations sites, or from BSE links shown on Screener.
  3. Every (company, quarter) gap left by iXBRL is filled with the BSE results PDF. The link is resolved through the user's logged-in Screener session in their own browser, as in Phase 3. The user expects to give the time for this.
- **Copy:** coverage is named **NIFTY 100**, for example "Ask about any NIFTY 100 company's filings." (My proposal, stated to the user; not objected to.)

## Approaches considered

1. **The Phase 3 replay with full gap-filling (picked).** It gives the financials table about the same coverage as the NIFTY 50 (around 93%), and number questions stay on the verified table. It costs user time on the Screener gaps.
2. **iXBRL only, no PDF gap-filling.** It costs no user time, but Phase 3's first pass averaged 3.2 of 7 quarters per company, so roughly half the Next 50 quarters would be missing and number questions would fall back to RAG.
3. **Phase 3 replay, capped at one sitting.** A middle ground, not chosen.

## Goals

- **Membership** (my call, after the builder check):
  - Use the NIFTY 100 list current on NSE's public index page at build time, and store a dated snapshot in the repo.
  - Any member not yet in the corpus is added at the Next 50 depth (FY2025 + FY2026 reports, 7 quarters). This includes NIFTY 50 members missing today; the corpus has 47 companies and `KWIL` is an empty folder.
  - Indexed companies that have left the NIFTY 100 stay in.
  - The coverage count shown anywhere comes from the index (`metrics.json` `index.companies`), so the copy stays true even if a company has no published report.
- **Corpus:**
  - Both annual reports indexed for every company that has published them.
  - Expected: about 100 new documents, about 2.4 GB of PDFs, and about 1.2 GB more index.
  - R2 storage stays **under 10 GB**. This is a hard check: if it fails, stop and ask. What counts (my call):
    - annual-report PDFs (`backend/data/<SYM>/<YEAR>.pdf`): about 3.2 GB today plus about 2.4 GB new
    - the compressed index tarball: about 0.44 GB today, about 0.7 GB after

    That totals about 6.3 GB. Quarterly results PDFs and iXBRL files (`data/quarterly`, `.superpowers/results-q`) are build inputs only. They are not uploaded: financials evidence links open the BSE/NSE `source_url`.
- **Financials table:** the Next 50 rows are in `financials.duckdb`. On the extended key, eval precision stays at 100%. Next 50 grid coverage (company × quarter × metric filled) is at or above 85%, reported separately.
- **Query understanding:** `COMPANY_ALIASES` gains every new symbol with its common names, so "Varun Beverages" maps to VBL.
- **Golden set:**
  - Extended with about 20 Next 50 cases across table, narrative, numeric and refusal kinds, including at least 3 near-duplicate-name cases and at least 1 pre-FY2025 prior-year case.
  - The user spot-checks 10, as in 5.3.
  - Not every company needs a case (my call). `landing.check.mjs` is re-pointed from `golden_set.companies` to `index.companies`.
- **Evals:** re-run the retrieval, financials, router and answer evals, and publish the new `metrics.json` so `/engineering` shows the NIFTY 100 run.
- **Regression gate** (my call):
  - Measured on the original 100 golden cases (v2), with the Next 50 cases reported separately.
  - If NIFTY 50 retrieval hit@3 or answer correctness drops by more than 2 points against the v3 run (hit@3 0.793, correctness 0.870), stop and ask. The judge is documented at about ±1 point of noise, so no extra baseline run is made.
- **Copy and data:**
  - "NIFTY 50" becomes "NIFTY 100" in the chat welcome, the landing Coverage section and its stat, `data/companies.js` and its comment, and the batch ingest docstring.
  - The landing coverage list shows all 100 companies.
- **Docs:** a short note on /engineering and in the eval README that Next 50 companies cover FY2025 onward.

## Non-goals

- Automated or scheduled fetching. It was dropped on 2026-11-24 because no free discovery source exists.
- FY2023 and FY2024 annual reports for the Next 50.
- New metrics or line items in the financials table.
- Deploy steps: the R2 upload, the server and rebuilding the index tarball. Those belong to the deploy phase. This phase only checks the size budget.

## Anti-goals

- Any paid API or data feed. Any use of NSE's or BSE's undocumented JSON list endpoints, which were blocked in Phase 3 and agreed against.
- A NIFTY 50 regression: retrieval hit@3, answer correctness or financials precision dropping because the corpus doubled and the retriever now competes across twice the documents.
- Wrong-company answers. With 100 companies, similar names (two Bajaj, two Tata or several Adani entities) must still route to the right symbol. Covered by the alias additions and golden cases that target near-duplicate names.
- Fetching that hammers a host. Keep Phase 3's 1 request per second, backoff, and resumable downloads.

## Constraints

- **Cost:**
  - Zero, apart from small OpenAI spend already accepted for this project: the `pdf_llm` fallback in the financials build, and eval runs.
  - **Cap: about $0.60 in total**, logged in the ledger. If the cap is hit, stop and ask.
- **Hardware:**
  - Re-indexing runs on the local RTX 3050 4 GB, with the CUDA torch already in the venv.
  - `batch_ingest_annual_reports` resumes from the registry and appends new PDFs; it does not rebuild the 186 existing documents.
- **Storage layout (unchanged):**
  - Annual reports go to `backend/data/<SYM>/<YEAR>.pdf`.
  - iXBRL candidates go in `.superpowers/xbrl-discovery/` (`manifest.csv` plus the cache).
  - Results PDFs go to `.superpowers/results-q/<SYM>/<YYYY-MM>.pdf`.
  - The financials sources import keeps its hash check.
- **OCR:** image-only PDFs go through the existing rapidocr path. Files that still fail are listed, not hand-typed.
- **Git:** PDFs and indexes stay out of git, as today. Committed: the code changes, the membership snapshot, aliases, the golden set, eval reports, `metrics.json`, and the `tests/fixtures/financials.duckdb` snapshot that CI's gates use (rebuild it if the gates read the new companies).
- **Checks:** `pytest tests/test_*.py`, `ruff`, the frontend lint/checks/build, and CI green.

## The user's part

- **Screener gap list:** after the iXBRL pass, the builder writes `missing_quarters.csv` for the Next 50 and gives the user the list. The user opens Screener while logged in, and the builder resolves each BSE PDF link through that browser session, as in Phase 3.
- **Golden set:** the user spot-checks about 10 of the new golden cases before they are committed.

## Left to the builder

- The search queries and order for iXBRL discovery, and the IR-site lookups for annual reports.
- Which Next 50 golden questions to write, within the kinds and count above. They include at least 3 near-duplicate-name cases.
- How to handle a company with only one FY annual report published (newly listed): index what exists and note it.
- Whether the landing coverage list needs a layout change to fit 100 names. It must still meet 6.1's look and stay readable at 375 px.
