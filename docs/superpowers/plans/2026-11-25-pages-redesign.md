# Phase 6.3 Pages Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `/login`, `/register`, `/auth/callback` and `/engineering` on the 6.1 `--cf` system. Add a 404 page for unknown URLs, and delete the legacy auth and landing styles.

**Architecture:**
- **Reuse:** 6.1's primitives (`Navbar`, `Footer`, `Wordmark`, `.cf-h1/.cf-h2`, `.cf-btn-*`, `.cf-section`, `.cf-link`).
- **New styles:** one new stylesheet `styles/pages.css` holds the page-specific rules, with prefixes `cf-auth-*`, `cf-eng-*` and `cf-nf-*`.
- **Logic:** auth logic and the `metrics.json` reading do not change. Only markup, class names and copy change.

**Tech Stack:** React 19, Vite 7, react-router 7, lucide-react. All are installed; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-25-pages-redesign-design.md`. The mockup is `docs/superpowers/specs/2026-11-25-pages-mockups.html`, option A.

## Global Constraints

- **Type:**
  - Headings use JetBrains Mono: weight 500, tight tracking, `.cf-h1`/`.cf-h2` or `var(--cf-font-mono)` with `letter-spacing: -0.03em`.
  - Body text is Inter.
  - Colours come only from `--cf-*` tokens.
- **Banned on these pages:**
  - the copy "Welcome Back" and "Get started with your financial analysis"
  - `→` appended to links or buttons
  - emoji, including `⚠` (use lucide `AlertTriangle` with `aria-hidden="true"` instead)
  - all-caps eyebrows (`text-transform: uppercase`)
  - middle-dot meta strings (`A · B`)
- **Kept as is:** model and method names on `/engineering`.
- **Auth logic unchanged:**
  - Google URL `${API_BASE}/auth/login`
  - `login`/`register` from `useAuth`
  - register validation ("Password must be at least 6 characters.", "Passwords do not match.") and `navigate('/login')` after register
  - the callback parsing, error map and 3s redirect
- **Accessibility:**
  - a 2px gold focus ring (`outline: 2px solid var(--cf-gold); outline-offset: 2px`) on every control
  - inputs keep their `<label>`
  - the Show/Hide button has `aria-label`
  - errors use `role="alert"`
  - each page has one `<h1>`
  - muted text uses `--cf-mute` or brighter
- **Motion:** only the existing `PageTransition` fade. Remove framer-motion from `EngineeringPage`.
- **Viewports:** no horizontal scroll at 375×667 or 1280×720.
- **Checks on every task**, run from `frontend/`:
  - `npm run lint`
  - every `src/utils/*.check.mjs`
  - `VITE_API_BASE=https://api.example.invalid npm run build`
- **Browser checks:** dev server on :5173, backend on :8000 (`backend/venv/Scripts/python -m uvicorn main:app --port 8000`).

## Review Focus

1. **A login or register error with a long server message.** It must wrap inside the form without widening the panel at 375px (Task 1 browser check: submit a wrong password).
2. **An unknown nested path** (`/foo/bar/baz`) or one with a query string. The 404 shows the pathname only (no query), and its links still work. Relative asset paths must not break on nested routes (Task 3 browser check).
3. **`/engineering` when `metrics.json` fails to load.** It shows the plain error line in the new style, with no crash and no empty tile strip (Task 2 browser check: block `/metrics.json` with a Playwright route).
4. **Keyboard-only sign-in.** Tab order goes Google, Email, Password, Show, Sign in, Create one. Every stop shows the gold ring, and Enter submits (Task 1 browser check).
5. **Leaving the 404 page.** `document.title` is restored to its previous value after navigating away (Task 3 browser check).

---

### Task 1: Login, register and callback

**Files:**
- Create: `frontend/src/styles/pages.css` (auth section)
- Modify:
  - `frontend/src/pages/LoginPage.jsx`
  - `frontend/src/pages/RegisterPage.jsx`
  - `frontend/src/pages/AuthCallbackPage.jsx`
- Delete: `frontend/src/styles/auth.css`

**Interfaces:**
- **Produces:** `styles/pages.css`, which Tasks 2 and 3 append to. Each page imports `../styles/pages.css`, and the auth pages also import `../styles/landing-v2.css` for `.cf-btn`/`.cf-h1`. `Wordmark` is imported from `../components/landing/Navbar`.

- [ ] **Step 1: Pick the sample cited answer.** Look in `backend/index_cache` (LanceDB) or the HDFC showcase answer's evidence for a real HDFC amalgamation passage and its page. If none is clean, use: "TCS reported consolidated revenue from operations of **₹2,40,893 crore** in FY2024" with chip `p.90`. Record the choice in the commit message.
- [ ] **Step 2: Rewrite `LoginPage` markup.** Keep its state and `handleSubmit` unchanged.
  - Root `.cf-auth`, a two-column grid on the `--cf-bg` grid background.
  - **Left panel** `.cf-auth-side`:
    - `<Link to="/">` wrapping `Wordmark`
    - an `<h1 className="cf-auth-title">`: "Every answer points to its page."
    - `<p>`: "Sign in to keep your chats and upload a company's annual report to ask about it."
    - the sample answer card `.cf-auth-sample`, with a mono gold page chip
  - **Right panel** `.cf-auth-main` holds a form column with max-width 340px:
    - `<h2>` "Sign in"
    - `<p>` "Use Google or your email."
    - the Google `<a>` (existing SVG, `.cf-auth-google`)
    - a divider "or"
    - Email and Password fields with visible `<label>`s and no left icons
    - the Show/Hide text button inside the password field (`aria-label` "Show password" / "Hide password")
    - the error `<p role="alert" className="cf-auth-error">` with `AlertTriangle`
    - a `.cf-btn.cf-btn-solid` submit, full width. Its label is "Sign in", or "Signing in…" while loading; drop the spinner div.
    - "No account? `<Link className="cf-link">`Create one`</Link>`"
  - No back link: the wordmark goes home.
- [ ] **Step 3: Rewrite `RegisterPage` the same way.** Copy changes:
  - `<h2>` "Create your account"
  - `<p>` "Use Google or your email."
  - Add the same Google link and "or" divider above the form.
  - Fields: Name, Email, Password, Confirm password.
  - Submit label: "Create account", or "Creating account…" while loading.
  - Footer line: "Already have an account? Sign in".
- [ ] **Step 4: Rewrite `AuthCallbackPage` markup.** Keep the logic unchanged. Root `.cf-auth-callback`, centred on the grid, containing `Wordmark` and then either:
  - **Signing in:** a `.cf-auth-spin` ring with `aria-hidden` and the text "Signing you in…" (`role="status"`). The ring is static under `prefers-reduced-motion: reduce`.
  - **Error:** `AlertTriangle`, then the error message in `role="alert"`, then "Taking you back to sign in."
- [ ] **Step 5: Write the auth section of `pages.css`.**
  - Below 900px the grid is one column and the side panel shows only the wordmark, title and line (`.cf-auth-sample { display: none }`).
  - Inputs: `--cf-bg` fill, `--cf-line` border, a `--cf-gold-line` border on focus, and the gold `:focus-visible` outline.
- [ ] **Step 6: Delete `auth.css`.** Confirm `grep -rn "auth.css\|auth-page\|auth-orb\|auth-card" src` prints nothing.
- [ ] **Step 7: Verify.** Run the Global Constraints checks. Expected: lint clean, all checks `ok`, build succeeds.
- [ ] **Step 8: Browser check at 1280×720 and 375×667.** Expected at both sizes: no horizontal scroll and no console errors.
  - **Login:**
    - a wrong password shows the server error inside the form without widening the panel (Review Focus 1)
    - the Tab order and focus rings match Review Focus 4
    - Enter submits
  - **Register:**
    - a 5-character password shows "Password must be at least 6 characters."
    - mismatched passwords show "Passwords do not match."
  - **Callback:** `/auth/callback?error=google_auth_failed` shows the message and goes to `/login` after about 3s.
- [ ] **Step 9: Commit.** Message: `"feat(auth): login, register and callback on the --cf system; drop auth.css"`.

### Task 2: /engineering

**Files:**
- Modify:
  - `frontend/src/pages/EngineeringPage.jsx`
  - `frontend/src/styles/pages.css` (engineering section)
- Delete:
  - `frontend/src/styles/engineering.css`
  - `frontend/src/styles/landing.css`

**Interfaces:**
- **Consumes:** `styles/pages.css` from Task 1; `pct`, `secs`, `usd` and `kindRows` from `utils/metricsFormat` (unchanged).

- [ ] **Step 1: Restructure the markup.** The data logic, `WEAK_SPOTS`, `README_URL` and the fetch stay as they are.
  - **Root:** `.cf-landing` (the same page background as the landing), with `Navbar`, then `<main className="cf-section cf-eng">`, then `Footer`.
  - **Header block:**
    - `<span className="cf-eng-eyebrow">Evaluation</span>`, mono 12px gold, sentence case
    - `<h1 className="cf-h1 cf-eng-title">How Cognifin is measured</h1>`. The page h1 is smaller than the landing hero; set `font-size: clamp(30px, 3.6vw, 42px)` in `.cf-eng-title`.
  - **Meta row** `.cf-eng-meta`: four `<span>`s with flex `gap`, no dots: `Eval run {date}`, `{cases} questions`, `{companies} companies`, `{index.documents} filings indexed`. Omit the last span if `index.documents` is missing.
  - **Tiles:** one `.cf-eng-tiles` strip, a 4-column grid on `--cf-glass` with hairline dividers, 2×2 below 860px. Replace `motion.div` with a plain `div` and remove the framer-motion import. The tile value uses the mono font with `tabular-nums`.
  - **Columns:** keep the two columns and the Reproduce section. `h2` uses `.cf-h2` at 20px in `.cf-eng`. The Reproduce links line drops the `·` separator span; the links sit in a flex row with `gap`.
  - **Loading and error lines:** use `.cf-eng-meta`.
- [ ] **Step 2: Write the engineering section of `pages.css`.** Bring over what `engineering.css` did (table, facts list, weak spots, repro code block) on `--cf` tokens. Delete `engineering.css` and `landing.css`. Confirm `grep -rn "landing.css\|engineering.css\|section-label\|landing-page\|--c-" src` prints nothing.
- [ ] **Step 3: Verify.** Run the checks. Expected: clean.
- [ ] **Step 4: Browser check at 1280×720 and 375×667.**
  - Tiles show the real `metrics.json` values (faithfulness 99.5%, correctness 87.0%).
  - The meta row shows "186 filings indexed".
  - No horizontal scroll.
  - With `page.route('**/metrics.json', r => r.abort())`, the page shows "Eval results are not available right now." and no tile strip (Review Focus 3).
- [ ] **Step 5: Commit.** Message: `"feat(engineering): restyle on the --cf system; drop legacy landing and engineering CSS"`.

### Task 3: 404 page

**Files:**
- Create: `frontend/src/pages/NotFoundPage.jsx`
- Modify:
  - `frontend/src/App.jsx`
  - `frontend/src/styles/pages.css` (404 section)

**Interfaces:**
- **Consumes:** `Navbar`, `Footer`, `.cf-btn-*` and `.cf-link`.
- **Produces:** `NotFoundPage()`, the default export, lazy-loaded in `App.jsx` as `<Route path="*">` wrapped in `PageTransition`. It must be the last route.

- [ ] **Step 1: Write `NotFoundPage`.**
  - **Root:** `.cf-landing`, then `Navbar`, then `<main className="cf-section cf-nf">`, then `Footer`.
  - **Content:**
    - `<span className="cf-nf-code">404</span>`
    - `<h1 className="cf-h2">This page isn't in the filings.</h1>`
    - `<p>Nothing lives at <code>{location.pathname}</code>. It may have moved, or the link has a typo.</p>`
    - buttons `<Link className="cf-btn cf-btn-solid" to="/chat">Ask a question</Link>` and `<Link className="cf-btn cf-btn-ghost" to="/">Back to home</Link>`
    - "Or try one of these:", then two `<Link>`s to `/chat?q=${encodeURIComponent(q)}`
  - **Questions:**
    ```js
    // Keep in sync with SUGGESTED in pages/ChatPage.jsx and SHOWCASE_QUESTIONS in backend/main.py.
    const TRY = [
      "What was TCS's consolidated revenue from operations in FY2024?",
      "What was Hindustan Unilever's profit after tax in FY2025?",
    ];
    ```
  - **Title:** a `useEffect` saves `document.title`, sets "Page not found · Cognifin", and restores the saved title on cleanup.
  - Long paths wrap: `.cf-nf code { overflow-wrap: anywhere; }`.
- [ ] **Step 2: Add the route** in `App.jsx`: `const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));`, then `<Route path="*" element={<PageTransition><NotFoundPage /></PageTransition>} />` after `/chat`.
- [ ] **Step 3: Verify.** Run the checks. Expected: clean.
- [ ] **Step 4: Browser check.**
  - `/pricing` shows the page with `/pricing` in the copy.
  - `/foo/bar/baz?x=1` shows `/foo/bar/baz`; fonts and styles load (Review Focus 2).
  - "Ask a question" goes to `/chat`. A "try" link opens `/chat` and asks that question.
  - After navigating to `/`, `document.title` is the landing title again (Review Focus 5).
  - At 375×667: no horizontal scroll, and the buttons wrap.
  - Then run a final sweep. It must print nothing:

    ```bash
    grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]|Welcome Back|→|uppercase" src/pages/LoginPage.jsx src/pages/RegisterPage.jsx src/pages/AuthCallbackPage.jsx src/pages/EngineeringPage.jsx src/pages/NotFoundPage.jsx src/styles/pages.css
    ```

- [ ] **Step 5: Commit.** Message: `"feat: 404 page for unknown URLs"`.
