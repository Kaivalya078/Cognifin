# /engineering page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public `/engineering` page that shows the committed eval numbers from `frontend/public/metrics.json`: scorecard on top, write-up below.

**Architecture:** One React page that fetches the static `/metrics.json` at runtime and formats it with small pure helpers. No backend change, no new dependency.

**Tech Stack:** React 19, react-router-dom 7, framer-motion (already installed), plain CSS, Node `assert` check scripts.

**Spec:** `docs/superpowers/specs/2026-11-25-engineering-page-design.md`

## Global Constraints

- Numbers come only from `/metrics.json`. If it fails to load, show a plain message and never fake or placeholder numbers.
- No new dependencies. No backend change. No cache hit rate or live stats.
- Look: navy `#080d17`, gold `#d4af37`, Inter, the landing page's `--container` width. Polished; must not look like a generated dashboard template.
- At 375 px wide, no horizontal scroll (Phase 6 target).
- The weak-spots copy is static text from `backend/tests/eval_reports/README.md`, v2 baseline (2% cited; 3 of 8 quarterly figures refused although the data exists; judge about ±1 pt noisy on correctness).
- `null` values show "—".
- Frontend checks: `npm run lint` and `VITE_API_BASE=https://api.example.invalid npm run build` must pass.

## Review Focus

1. `/metrics.json` 404 or bad JSON: the page shows "Eval results are not available right now." and nothing else in the number slots. (Task 2, Step 5)
2. A field missing or `null` (e.g. `by_kind.refusal.faithfulness`): it renders "—", and the page doesn't crash. (Task 1 test)
3. 375 px wide: the reproduce command and the by-type table don't cause horizontal scroll, because the `code` wraps and the table fits. (Task 2, Step 5)
4. Loading `/engineering` directly or refreshing it: works, because `vercel.json` already rewrites to `index.html` and Vite dev does too. (Task 2, Step 5)
5. A `by_kind` key missing from a future run: that row is skipped, not shown as NaN. (Task 1 test)

---

### Task 1: Number formatting helpers

**Files:**
- Create: `frontend/src/utils/metricsFormat.js`
- Create: `frontend/src/utils/metricsFormat.check.mjs`
- Modify: `.github/workflows/ci.yml:83` (append `&& node src/utils/metricsFormat.check.mjs`)

**Interfaces:**
- Produces:
  - `pct(x: number|null|undefined, digits = 1) -> string`: `0.99441 → "99.4%"`, `1 → "100%"` (drop a trailing `.0`), `0.87 → "87%"`, `null`/`undefined`/`NaN → "—"`.
  - `secs(ms: number|null|undefined) -> string`: `9266 → "9.3 s"`, `null → "—"`.
  - `usd(x: number|null|undefined) -> string`: `0.000672 → "$0.00067"` (2 significant figures), `null → "—"`.
  - `kindRows(byKind: object|null|undefined) -> Array<{key, label, n, correctness, faithfulness}>`: fixed order `narrative, table, numeric, refusal` with labels `Narrative`, `Table figures`, `Quarterly numbers`, `Should refuse`. Keys missing from `byKind` are skipped; `byKind` null gives `[]`.

- [ ] **Step 1: Write the check** `metricsFormat.check.mjs` in the `refusal.check.mjs` style:

```js
assert.equal(pct(0.994413407821229), '99.4%');
assert.equal(pct(1), '100%');
assert.equal(pct(0.87), '87%');
assert.equal(pct(0.021052631578947368), '2.1%');
assert.equal(pct(null), '—');
assert.equal(pct(undefined), '—');
assert.equal(secs(9266), '9.3 s');
assert.equal(secs(15035.3), '15.0 s');
assert.equal(secs(null), '—');
assert.equal(usd(0.000672), '$0.00067');
assert.equal(usd(0.000708), '$0.00071');
assert.equal(usd(null), '—');
const rows = kindRows({ table: { n: 46, correctness: 0.837, faithfulness: 1 },
                        refusal: { n: 5, correctness: 1, faithfulness: null },
                        narrative: { n: 41, correctness: 0.939, faithfulness: 0.991 } });
assert.deepEqual(rows.map(r => r.key), ['narrative', 'table', 'refusal']);
assert.equal(rows[1].label, 'Table figures');
assert.equal(rows[2].faithfulness, null);
assert.deepEqual(kindRows(null), []);
console.log('metricsFormat.check: ok');
```

- [ ] **Step 2: Run** `node src/utils/metricsFormat.check.mjs` (from `frontend/`). Expected: FAIL (module not found).
- [ ] **Step 3: Implement** the four functions in `metricsFormat.js` with the signatures above. `usd` uses `toPrecision(2)` on the number, then prefixes `$`.
- [ ] **Step 4: Run** the check again. Expected: `metricsFormat.check: ok`. Then `npm run lint`. Expected: no errors.
- [ ] **Step 5: Add to CI.** Append `&& node src/utils/metricsFormat.check.mjs` to the `Unit checks` run line in `.github/workflows/ci.yml`.
- [ ] **Step 6: Commit** `git add frontend/src/utils/metricsFormat.js frontend/src/utils/metricsFormat.check.mjs .github/workflows/ci.yml && git commit -m "feat(frontend): metrics formatting helpers for /engineering"`

### Task 2: The page, route and links

**Files:**
- Create: `frontend/src/pages/EngineeringPage.jsx`, `frontend/src/styles/engineering.css`
- Modify: `frontend/src/App.jsx` (route), `frontend/src/components/landing/Navbar.jsx` (desktop and mobile links), `frontend/src/components/landing/Footer.jsx` (link; also fix the stale "FAISS" partner label to "LanceDB", since storage moved to LanceDB in Phase 2)

**Interfaces:**
- Consumes: `pct`, `secs`, `usd`, `kindRows` from Task 1. The `metrics.json` shape as committed: `generated_at`, `label`, `model`, `judge_model`, `golden_set.{cases,companies}`, `answers.{faithfulness, correctness, citation_validity, cited_share, refusal_accuracy, by_kind}`, `retrieval.{hit@3, hit@8}`, `latency_ms.{p50,p95}`, `cost_usd.{per_question, judge_per_question}`, `index.{documents, chunks, disk_mb}`.
- Produces: `export default function EngineeringPage()`.

- [ ] **Step 1: Route.** In `App.jsx`, add `<Route path="/engineering" element={<PageTransition><EngineeringPage /></PageTransition>} />`.
- [ ] **Step 2: Page.** `EngineeringPage` fetches `/metrics.json` once (`useEffect`, state `{status: 'loading'|'ok'|'error', data}`; any non-ok response or JSON error sets `'error'`). It renders the existing landing `Navbar` and `Footer` around:
  - **Header:** h1 "How Cognifin is measured". Meta line: "Eval run {date from generated_at, e.g. 25 Nov 2026} · {cases} questions · {companies} companies".
  - **Four tiles:** Faithfulness `pct(answers.faithfulness)`, sub "claims backed by the passages shown"; Correct answers `pct(answers.correctness)`, sub "vs a hand-checked answer key"; Retrieval hit@8 `pct(retrieval['hit@8'])`, sub "right page in the top 8"; Latency p50 `secs(latency_ms.p50)`, sub `"p95 " + secs(latency_ms.p95)`.
  - **Left column:** "How it's measured", 3 short paragraphs: (1) 100 questions over 47 companies' annual reports and quarterly filings, each answer key checked on its source page; (2) every question runs through the same pipeline the chat uses; (3) a judge model splits each answer into single claims and checks each against the exact passages the app was shown (the RAGAS faithfulness method). Below them, a "Known weak spots" box with the three static points from Global Constraints.
  - **Right column:** a by-type table from `kindRows(answers.by_kind)` (columns: Type, n, Correct, Faithful). Under it, a facts list: Refusal accuracy, Citation validity, Answers with a citation (`cited_share`), Retrieval hit@3, Cost per question (`usd(per_question)` + " + " + `usd(judge_per_question)` + " judge"), Index (`documents` docs · `chunks` in `toLocaleString('en-IN')` · `disk_mb/1024` to 1 decimal + " GB").
  - **Bottom:** "Reproduce" with `<code>PYTHONUTF8=1 python -m tests.eval_answers --label NAME</code>`; "Models: {model} (answers), {judge_model} (judge)"; links "Raw metrics.json" (`/metrics.json`) and "Eval write-up" (`https://github.com/Kaivalya078/Cognifin/blob/main/backend/tests/eval_reports/README.md`, new tab, `rel="noreferrer"`).
  - **Loading:** a quiet "Loading eval results…" line. **Error:** "Eval results are not available right now." with no tiles.
- [ ] **Step 3: Styles** in `engineering.css`. Use the landing palette variables (import `landing.css` for them). Tiles: thin gold border at 0.18 alpha, tabular numerals. The two columns sit side by side at `min-width: 860px` and stack below that. `code` gets `white-space: pre-wrap; word-break: break-all`. Motion: one framer-motion fade-up for the tile row only.
- [ ] **Step 4: Links.** Navbar: add an `Engineering` `<Link to="/engineering">` after "About" (desktop, using the same `nav-link` markup with its underline div; mobile `mobile-nav-link` with `onClick={toggleMobileMenu}`). Footer: add a `Link` "Engineering" near the copyright, and change `FAISS` to `LanceDB`.
- [ ] **Step 5: Verify in the browser** (`npm run dev`, then use Playwright or Chrome DevTools):
  - `/engineering` loaded directly shows the tiles: 99.4%, 87%, 96.6%, 9.3 s / p95 15.0 s. The table shows 4 rows, with refusal's Faithful showing "—".
  - Resize to 375 px: `document.documentElement.scrollWidth <= 375`.
  - Temporarily rename `public/metrics.json`, reload, and see the error message with no numbers. Rename it back.
  - Click the navbar "Engineering" link from `/`, and the footer link.
  - Take a screenshot at desktop and at 375 px, and show both to the user.
- [ ] **Step 6: Run** `npm run lint`, `node src/utils/metricsFormat.check.mjs`, and `VITE_API_BASE=https://api.example.invalid npm run build`. Expected: all pass.
- [ ] **Step 7: Commit** `git add frontend/src && git commit -m "feat(frontend): /engineering page from committed eval metrics"`
