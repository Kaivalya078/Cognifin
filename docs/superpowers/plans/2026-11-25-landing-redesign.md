# Phase 6.1 Design System + Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the landing page with the approved "smoked liquid glass" design (hero B, product window C, how it works, proof, coverage, final CTA) on a new shared token layer, matching kaivalyapatel.dev.

**Architecture:** Plain CSS with a `--cf-*` token file, and React components under `src/components/landing/`. GSAP drives the hero loop and scroll reveals; Lenis provides smooth scroll on `/` only. Everything is off under reduced motion. Numbers come from `public/metrics.json`. The final CTA hands a question to `/chat?q=`.

**Tech Stack:** React 19, Vite 7, react-router 7, `gsap`, `lenis` (new), lucide-react; Node assert check scripts.

**Spec:** `docs/superpowers/specs/2026-11-25-landing-redesign-design.md`

## Global Constraints

- **Look:**
  - Background `#06070c`; faint 22 px grid of hairlines at `rgba(233,230,223,.09)` (lower opacity in use).
  - Smoked glass: `rgba(9,10,16,.72–.88)` with `backdrop-filter: blur(14px) saturate(1.2)`.
  - Text `#e9e6df`, sub-text at 58% and muted at 32% alpha. Gold `#c9a24a`, soft gold `rgba(201,162,74,.14)`.
  - JetBrains Mono 400/500 for headings, wordmark, numbers, tickers and chips; Inter 400/500/600 for body.
  - Radii 6–14 px, almost no shadows. Wordmark: `cognifin` with a gold `.`.
- **Anti-goals:** no gradient headline text, no glowing rounded cards, no emoji, no sparkle badges, no koi or ASCII creatures, no three.js or Vanta, no placeholder numbers.
- **Tokens** are prefixed `--cf-*`. Never redefine `chat.css`'s generic `:root` names (`--border`, `--text`, `--bg-card`, …). Keep `.landing-page` and `.section-label`, which `/engineering` uses, and keep the `--c-*` variables, mapped onto `--cf-*`.
- **Vendor and model names** don't appear on `/`, the navbar or the footer.
- **New dependencies** are only `gsap` and `lenis`. Lenis runs on `/` only.
- **`prefers-reduced-motion: reduce`:** no Lenis, no hero loop (show its final frame, with the answer card visible), no reveals.
- **375 px:** no horizontal scroll, and the navbar fits.
- **Accessibility and Lighthouse:**
  - one h1; ordered headings; visible focus rings
  - the decorative hero animation is `aria-hidden`
  - the menu button has `aria-label` and `aria-expanded`
  - everything keyboard reachable
  - Lighthouse accessibility ≥ 90 on `/` (production build), and performance not below the baseline measured in Task 1
- **Checks:** `npm run lint`, all `src/utils/*.check.mjs` and any new check scripts (added to the CI `Unit checks` line), and `VITE_API_BASE=https://api.example.invalid npm run build`. Backend untouched.
- **Fixed content (verified 2026-11-25):**
  - **Hero:** "What was TCS's revenue in FY24?" → "Consolidated revenue from operations was ₹2,40,893 crore, up 6.8% year on year." with chip `p.56`. TCS AR 2023-24 p.56 prints both ₹2,40,893 (FY24) and ₹2,25,458 (FY23) crore.
  - **CTA chips** (golden-set questions answered correctly and cited by the model in v3):
    - label "HDFC merger date" → "When did the amalgamation of HDFC Limited with HDFC Bank become effective?"
    - label "Infosys acquisitions FY25" → "Which acquisitions did the Infosys board approve in fiscal 2025?"
    - label "HUL profit FY25" → "What was Hindustan Unilever's profit after tax in FY2025?"
  - **Coverage:** the 47 companies in `backend/tests/golden_set.json`.

## Review Focus

1. **`metrics.json` missing or bad:** the Proof section is hidden, and How-it-works step 02 falls back to wording with no count. No "undefined", "NaN" or "—" appears on the landing page. (Task 5)
2. **`/chat?q=` with an empty, whitespace-only or very long `q`, and StrictMode double effects:** a question is sent at most once, empty is ignored, and `q` is removed from the URL. (Task 7)
3. **Reduced motion:** every GSAP and Lenis path is off, and content is fully visible with nothing stuck at opacity 0. (Tasks 4 and 6)
4. **`/engineering` and `/chat` after the token and cleanup change:** both still render as before; no stale indigo, no missing variables. (Task 1)
5. **Mobile navbar sheet:** opens and closes with the button and Escape, links close it, and focus is reachable. (Task 3)

---

### Task 1: Tokens, fonts, cleanup (and the Lighthouse baseline)

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/main.jsx` (import tokens), `frontend/index.html` (fonts: add JetBrains Mono 400;500, trim Inter to 400;500;600), `frontend/src/styles/landing.css` (`:root` `--c-*` mapped onto `--cf-*`), `frontend/src/App.jsx` (drop the `App.css` import)
- Delete: `frontend/src/App.css`, `frontend/src/components/{AnswerView,EvidenceList,EvidenceItem,QuestionBox}.jsx`

**Interfaces:**
- Produces these tokens:
  - colours: `--cf-bg`, `--cf-ink`, `--cf-sub`, `--cf-mute`, `--cf-line`, `--cf-gold`, `--cf-gold-soft`, `--cf-glass`, `--cf-glass-strong`, `--cf-blur`
  - fonts: `--cf-font-mono`, `--cf-font-sans`
  - radii: `--cf-r-sm` / `--cf-r-md` / `--cf-r-lg` (6 / 10 / 14 px)
  - layout: `--cf-container` (1160px)
  - `--cf-blur` = `blur(14px) saturate(1.2)`

- [ ] **Step 1: Baseline.**
  - Run `VITE_API_BASE=https://api.example.invalid npm run build && npx vite preview --port 4173`.
  - Run Lighthouse (chrome-devtools `lighthouse_audit`, desktop) on `http://localhost:4173/` and record performance and accessibility in the ledger.
  - Take full-page screenshots of `/engineering` and `/chat` (before) into `.playwright-mcp/`.
- [ ] **Step 2: Confirm dead code.** `grep -rn "AnswerView\|EvidenceList\|EvidenceItem\|QuestionBox" frontend/src` only matches the four files themselves. `App.css` is only imported by `App.jsx`.
- [ ] **Step 3: Implement** the token file, fonts, the mapping and the deletions.
- [ ] **Step 4: Verify.**
  - lint + checks + build pass.
  - Screenshots of `/engineering` and `/chat` (after) show no regression against Step 1. Compare by eye, and with `getComputedStyle` that body background and fonts resolve, with no empty CSS variables.
- [ ] **Step 5: Commit** `feat(frontend): --cf design tokens, JetBrains Mono, drop dead App.css and components`

### Task 2: Landing data and helpers

**Files:**
- Create: `frontend/src/data/companies.js` (the 47 symbols, sorted, as `export const COMPANIES = [...]`), `frontend/src/data/examples.js` (`HERO_CASE` and `CTA_EXAMPLES` from Global Constraints), `frontend/src/utils/landing.js`, `frontend/src/utils/landing.check.mjs`
- Modify: `.github/workflows/ci.yml` (append `&& node src/utils/landing.check.mjs`)

**Interfaces:**
- Produces:
  - `chatHref(question: string) -> string`: `/chat?q=<encodeURIComponent(trimmed)>`, or `/chat` when the trimmed question is empty.
  - `proofItems(metrics) -> Array<{value: string, label: string}> | null`: faithfulness, correctness, companies and filings, formatted with `pct` from `metricsFormat.js`. Returns `null` unless all four inputs are finite numbers.

- [ ] **Step 1: Write the check.**
  - `chatHref('  What was X?  ')` gives `/chat?q=What%20was%20X%3F`; `chatHref('   ')` gives `/chat`.
  - `proofItems(<public/metrics.json read with fs>)` returns 4 items, with values `99.5%`, `87%`, `47`, `186` (read from the file, not hardcoded expectations, except asserting the count is 4 and every value is non-empty).
  - `proofItems({})` and `proofItems(null)` are both `null`.
  - `COMPANIES.length` equals `metrics.golden_set.companies`; it has no duplicates and contains no `KWIL`.
- [ ] **Step 2: Run** `node src/utils/landing.check.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement.** Get the 47 symbols from `backend/tests/golden_set.json` (`company` field, unique, sorted).
- [ ] **Step 4: Run** the check, lint and build. Expected: pass. Add the check to CI.
- [ ] **Step 5: Commit** `feat(landing): company list, example questions, chat handoff and proof helpers`

### Task 3: Navbar and Footer

**Files:**
- Rewrite: `frontend/src/components/landing/Navbar.jsx`, `frontend/src/components/landing/Footer.jsx`
- Create: `frontend/src/styles/landing-v2.css` (all new landing styles; imported by `LandingPage` and by these two components)

**Interfaces:**
- Produces: `<Navbar />` and `<Footer />` with no props. They are used by `LandingPage` and the existing `EngineeringPage`.

- [ ] **Step 1: Implement.**
  - **Navbar:** a sticky glass bar with the wordmark (→ `/`), and Product (`/#product`), How it works (`/#how`), Engineering (`/engineering`) and **Open app** (`/chat`).
  - Below 860 px it shows a menu button (`aria-label="Menu"`, `aria-expanded`) that opens a glass sheet. Escape and any link close it.
  - **Footer:** wordmark · Engineering · GitHub (`https://github.com/Kaivalya078/Cognifin`, new tab) · © year. No "Powered by".
- [ ] **Step 2: Verify in the browser** at 1366 px and 375 px, on `/` (old body still in place) and `/engineering`:
  - nothing overlaps
  - the sheet opens and closes by button, Escape and link click
  - keyboard Tab reaches every link with a visible focus ring
  - `scrollWidth <= 375`
- [ ] **Step 3: Run** lint and build. Commit `feat(landing): smoked-glass navbar and footer`.

### Task 4: Hero (B, filing scan)

**Files:**
- Rewrite: `frontend/src/components/landing/Hero.jsx`
- Modify: `frontend/src/styles/landing-v2.css`; `package.json` (`npm i gsap lenis`)

**Interfaces:**
- Consumes `HERO_CASE` (Task 2).
- Produces `<Hero />`.

- [ ] **Step 1: Install** with `npm i gsap lenis`. Record the versions in the ledger.
- [ ] **Step 2: Implement.**
  - **Left:** the eyebrow `FINANCIAL FILINGS · NIFTY 50`; h1 "Every answer points to its page."; the paragraph from the spec; buttons **Try a question** (`/chat`) and **See how it's measured** (`/engineering`).
  - **Right (`aria-hidden="true"`):**
    - a stylised filing page: "TCS · ANNUAL REPORT 2023-24", "p. 56", grey text lines, rows "Revenue from operations 2,40,893", "Other income", "Total expenses"
    - a gold scan line
    - an answer card with the question, the answer and a `p.56` chip
  - Show only real labels and values. Use grey bars for the other text, and for the two other rows draw a bar instead of a figure, unless the builder verifies their FY24 figures on p.56.
  - **GSAP timeline** (`useLayoutEffect` with `gsap.context`, reverted on unmount): the scan line sweeps down the page; the row highlights when the line passes it; the answer card fades and rises in; it holds about 3 s, then resets. It repeats with about an 8 s period.
  - Under `matchMedia('(prefers-reduced-motion: reduce)')`, skip the timeline and render the final state.
  - **Mobile:** the text first, the visual below it, scaled to fit 335 px.
- [ ] **Step 3: Verify in the browser.**
  - The loop runs. Use an `evaluate` reading the card's opacity at two times.
  - With `emulate` set to reduced motion, the card is visible immediately and nothing is animating.
  - No horizontal scroll at 375 px.
- [ ] **Step 4: Run** lint and build. Commit `feat(landing): filing-scan hero`.

### Task 5: Product window, How it works, Proof, Coverage, Final CTA

**Files:**
- Create: `frontend/src/components/landing/{ProductWindow,HowItWorks,Proof,Coverage,AskCta}.jsx`. `HowItWorks.jsx` is rewritten in place.
- Modify: `frontend/src/styles/landing-v2.css`

**Interfaces:**
- Consumes: `COMPANIES`, `CTA_EXAMPLES`, `chatHref` and `proofItems` (Task 2); `metrics` (one fetch of `/metrics.json` in `LandingPage`, Task 6, passed down as a prop that is `null` until it loads or when it fails).
- Produces: `<ProductWindow />`, `<HowItWorks metrics />`, `<Proof metrics />`, `<Coverage />`, `<AskCta />`.

- [ ] **Step 1: Pick and verify the product-window case.**
  - Use HDFC Bank gross NPA over the last 4 quarters in `backend/index_cache/financials.duckdb`. Query it with the venv Python (read-only), and record the query and values in the ledger.
  - If fewer than 3 quarters exist, use `hdfcbank-2024-gnpa` (1.24%, its answer page) with a 2-point FY comparison from the same table.
  - The answer text cites `fin` (chip "table") and the page chip of the filing page highlighted on the right. Use the BSE filing page if the table row has one; otherwise use the annual-report sentence "Gross NPAs were 1.24% of gross advances" with its golden-set page.
  - The chart is a small inline SVG polyline drawn from those values (no recharts on the landing page).
- [ ] **Step 2: Implement.**
  - **ProductWindow** (`id="product"`):
    - a static frosted window: left, the user bubble, the cited answer and the chart; right, the page with the highlight
    - `aria-label` on the figure describing it: "Example answer with its cited filing page"
  - **HowItWorks** (`id="how"`):
    - three mono-numbered rows, from the spec: 01 Ask / 02 Search / 03 Answer
    - step 02 uses `metrics.index.documents` when it's a number; otherwise "the annual reports and quarterly results"
  - **Proof:**
    - `proofItems(metrics)` gives the four figures with the spec labels, plus "How it's measured →" (`/engineering`)
    - renders nothing when `null`
  - **Coverage:**
    - the heading "{COMPANIES.length} NIFTY 50 companies covered"
    - the ticker wall in mono; a muted line "Company not listed? Upload its annual report in the app." → `/chat`
  - **AskCta:**
    - h2 "Ask your first question."
    - a `<form>` with a labelled input (visually hidden `<label>`), an Ask button, and the three chip buttons
    - submit or a chip click calls `navigate(chatHref(q))`; an empty submit does nothing
- [ ] **Step 3: Verify in the browser** (dev server, with the old landing body replaced by these components in a temporary `LandingPage` composition, or wait for Task 6 and verify there):
  - the sections render with real numbers
  - with `metrics.json` renamed, Proof disappears and step 02 falls back, with no "undefined", "NaN" or "—" text on the page
  - a chip click lands on `/chat?q=…`
- [ ] **Step 4: Run** lint and build. Commit `feat(landing): product window, how it works, proof, coverage, ask CTA`.

### Task 6: Assemble the page, smooth scroll, reveals

**Files:**
- Rewrite: `frontend/src/pages/LandingPage.jsx`
- Delete: `frontend/src/components/landing/Features.jsx`
- Modify: `frontend/src/styles/landing-v2.css` (page background and grid)

**Interfaces:**
- Consumes all section components.
- Produces the `/` page.

- [ ] **Step 1: Implement.**
  - `LandingPage` order: Navbar, Hero, ProductWindow, HowItWorks, Proof, Coverage, AskCta, Footer.
  - It fetches `/metrics.json` once (any failure → `null`).
  - Background `--cf-bg` with the CSS grid; the builder decides whether it fades at the edges.
  - **Lenis:** create it on mount, drive it from `gsap.ticker`, call `ScrollTrigger.update` on scroll, and destroy it on unmount. Skip it under reduced motion.
  - Keep the existing hash scroll (`/#product`, `/#how`), using `lenis.scrollTo` when Lenis is active.
  - **Reveals:** each section below the hero fades up once with ScrollTrigger (`once: true`). Under reduced motion, no reveal runs and sections start visible: never set initial opacity 0 in CSS, only from GSAP.
  - Remove the old `landing.css` landing-only rules that no longer match any element. Keep the `.landing-page`, `.section-label` and `--c-*` rules that `/engineering` uses.
- [ ] **Step 2: Verify in the browser:**
  - a full-page screenshot at 1366 px and 375 px
  - `scrollWidth <= 375`
  - `/#how` from `/engineering` scrolls to the section
  - with reduced motion emulated, every section is visible (computed opacity 1)
  - console clean
- [ ] **Step 3: Run** lint, checks and build. Commit `feat(landing): assemble new landing with smooth scroll and reveals`.

### Task 7: `/chat?q=` handoff

**Files:**
- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/utils/landing.js` (+ check)

**Interfaces:**
- Produces `readQuestionParam(search: string) -> string | null`: the trimmed `q`, capped at 500 characters, or `null` when absent or empty.

- [ ] **Step 1: Add checks.**
  - `readQuestionParam('?q=Hi%20there')` gives `'Hi there'`.
  - `readQuestionParam('?q=%20%20')` and `readQuestionParam('')` give `null`.
  - A 600-character `q` comes back with length 500.
- [ ] **Step 2: Run** the check. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `ChatPage` reads it once on mount, behind a `useRef` guard so StrictMode's double effect sends at most once.
  - It calls `navigate('/chat', { replace: true })` to remove `q`, then calls `handleSend(question)`.
- [ ] **Step 4: Verify in the browser** (real backend on :8000, dev server on :5173). The CTA chip "HDFC merger date" leads to `/chat`, the question is sent once (one user bubble), and an answer arrives with chips. Reloading doesn't resend.
- [ ] **Step 5: Run** lint and checks. Commit `feat(chat): open with a question from /chat?q=`.

### Task 8: Final verification and the user's look check

- [ ] **Step 1: Production build plus preview.**
  - Lighthouse on `/`: accessibility ≥ 90, and performance not below the Task 1 baseline. Record both.
  - If a check fails, fix it (for example font `display=swap`, image sizes or contrast) and re-measure.
- [ ] **Step 2: Remove vendor mentions.** `grep -rn -i "gpt\|openai\|powered by\|lancedb\|fastapi" frontend/src/components/landing frontend/src/pages/LandingPage.jsx` finds nothing.
- [ ] **Step 3: Screenshots for the user:**
  - full-page `/` at 1366 px and 375 px
  - the hero mid-animation
  - `/engineering`

  Send the paths and a short note.
- [ ] **Step 4: HARD STOP.** The user reviews the look. Apply their feedback (each change verified in the browser, then committed), and repeat until they're happy. Ledger each round.
