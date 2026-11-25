# Phase 6.3: Login, Register, /engineering and 404 Redesign

## Intent

Phase 6 is a full visual overhaul in three projects. 6.1 (design system and landing page) is merged. 6.2 (chat) is in PR #8. This is project 3, the remaining pages:
- `/login`
- `/register`
- `/auth/callback`
- `/engineering`
- a new 404 page

When it's done, every page reads as one product, a sibling of kaivalyapatel.dev. It must look professional and not AI-generated. Today:
- Login and register still use the pre-Phase-6 look: blue gradient orbs, a chart-icon logo, "Welcome Back", and "Create one →". That look lives in `auth.css` (421 lines), and none of it uses the `--cf` tokens.
- `/engineering` already has the new navbar and footer. Its body still runs on the legacy `--c-*` variables in `landing.css`, with an 800-weight sans heading and an all-caps label.
- There is no catch-all route, so an unknown URL renders a blank page.

## Decided with the user

- **Type direction A, like the landing:** JetBrains Mono headings (500 weight, tight tracking, as `.cf-h1`/`.cf-h2`) with an Inter body on all of these pages. The chat stays Inter-only; that was a separate, deliberate choice for the chat.
- **Layouts as in the mockups** (`docs/superpowers/specs/2026-11-25-pages-mockups.html`, option A), which the user approved:
  - **Login:** a split screen.
    - The left panel has:
      - the wordmark
      - the heading "Every answer points to its page."
      - one line on why to sign in
      - a sample cited answer card
    - The right panel has:
      - "Sign in"
      - "Use Google or your email."
      - Continue with Google, then "or"
      - Email, Password with a Show toggle
      - a solid Sign in button
      - "No account? Create one"
  - **Register:** the same layout. The form has Name, Email, Password and Confirm password, and ends with "Already have an account? Sign in". Register also gets Continue with Google plus "or", using the same OAuth URL as login (Google sign-in creates the account on first use). This is my call: the register page has no Google option today, and "same layout" implies it.
  - **/engineering:**
    - the landing navbar
    - a mono gold eyebrow "Evaluation" in sentence case (not all caps)
    - the h1 "How Cognifin is measured"
    - a meta row (run date, questions, companies, filings indexed) as separate spans, not middle dots
    - the four headline tiles in one glass strip with hairline dividers
    - then the existing two columns (method text and known weak spots; the by-type table and facts)
    - then Reproduce, then the footer
  - **404:**
    - the landing navbar and footer
    - a mono gold `404`
    - the h1 "This page isn't in the filings."
    - "Nothing lives at `<path>`. It may have moved, or the link has a typo." The path is shown in a mono inline box.
    - **Ask a question** (solid, to `/chat`) and **Back to home** (ghost, to `/`)
    - "Or try one of these:" followed by two showcase questions that link to `/chat?q=…`
- **Approach: reuse 6.1's primitives.** Use the existing pieces instead of a shared page-shell component:
  - `Navbar`, `Footer` and `Wordmark`
  - `.cf-h1`/`.cf-h2`, `.cf-btn-*`, `.cf-section` and the grid background from `landing-v2.css`

  Login and register get one new stylesheet on the tokens. The old `auth.css`, `landing.css` and `engineering.css` are replaced. A shell component was rejected because only two pages would use it. Restyling `auth.css` in place was rejected because it keeps about 400 lines of dead orb and gradient CSS.

## Approaches considered

1. **Reuse the 6.1 primitives, plus one new auth stylesheet (picked).** Smallest diff. Every page shares the landing's real navbar, footer, buttons and heading rules, so it can't drift.
2. **A shared `<SitePage>` shell component** wrapping navbar, footer and background. It saves a few lines on two pages, but adds a layer for no real reuse.
3. **Restyle `auth.css` in place.** This keeps the old class names and dead rules, the opposite of the cleanup this phase is for.

## Goals

- Login, register, callback, /engineering and 404 use only `--cf-*` tokens, JetBrains Mono and Inter, smoked glass and the gold accent, matching the landing page.
- Unknown URLs show the 404 page with the real path in the copy, and the page is reachable with the keyboard like every other page.
- Legacy styles are gone:
  - `auth.css`, `landing.css` (the `--c-*` variables, `.landing-page`, `.section-label`), `engineering.css`
  - plus `chat.css`/`api.css` if 6.2 hasn't already removed them on main by the time this merges. 6.2 deletes them; whichever merges second resolves this.
- Copy is plain and free of AI tells:
  - no "Welcome Back"
  - no "Get started with your financial analysis"
  - no `→` appended to links
  - no emoji (the `⚠` in errors goes, replaced by a lucide `AlertTriangle` icon with `aria-hidden`)
  - no all-caps eyebrows

## Non-goals

- Any change to how auth works:
  - Google OAuth URL and flow, email/password login, register validation (6+ characters, passwords match)
  - register then redirect to `/login` (pre-existing; kept)
  - `AuthContext`, the callback's token and user parsing and its error map, and the 3s redirect to `/login` on error
- New /engineering content or metrics. The page reads `metrics.json` exactly as today, and model and method names stay on this page by design.
- Landing-page or chat changes.

## Anti-goals

- A login page that looks like a template: a centred card on a gradient, an icon-in-a-box logo, glow.
- Losing a working sign-in path, or breaking keyboard use of the forms.
- Visible layout shift at 375px, or horizontal scroll at any width.

## Constraints

- **Reuse:**
  - `Wordmark`, `Navbar` and `Footer` from `components/landing/`
  - `.cf-h1`, `.cf-h2`, `.cf-btn`, `.cf-btn-solid`, `.cf-btn-ghost`, `.cf-section` and `.cf-link` from `landing-v2.css`
  - tokens from `tokens.css`

  Add a token only if truly needed.
- **New styles** go in `styles/pages.css` with prefixes `cf-auth-*`, `cf-eng-*` and `cf-nf-*`.
- **Accessibility:**
  - a visible 2px gold focus ring on every control
  - inputs keep their `<label>`, and the Show/Hide password button keeps its `aria-label`
  - errors use `role="alert"`
  - muted text uses `--cf-mute` or brighter (≥ 4.5:1)
  - the 404 page has a single `<h1>`
- **Viewports:** at 375×667 and 1280×720, no horizontal scroll. On narrow screens the login/register left panel collapses to wordmark, heading and line (the sample answer card hides), and the form is visible without scrolling past a hero.
- **Motion:** the existing `PageTransition` fade only. No new animation. The /engineering tiles drop their framer-motion entrance, so the page is complete at rest.
- **Checks:**
  - `npm run lint`
  - every `src/utils/*.check.mjs`
  - `VITE_API_BASE=https://api.example.invalid npm run build`
  - the backend suite is untouched

## The 404 route

- `<Route path="*">` inside `AnimatedRoutes`, wrapped in `PageTransition`, lazy-loaded like the others (`pages/NotFoundPage.jsx`).
- It sets `document.title` to "Page not found · Cognifin" while mounted, restoring the previous title on unmount.

  A static host returns 200 for every path (the SPA fallback), so there is no real 404 status. That's acceptable for this project and noted for deploy: Vercel rewrites send everything to `index.html`.
- The two example questions are the first and fourth showcase questions (TCS revenue FY2024, HUL PAT FY2025). They are copied from `SUGGESTED` in `ChatPage.jsx`, and the copy is kept in sync by a comment naming it. My call: `SUGGESTED` only exists once PR #8 merges, so the two strings are hard-coded in `NotFoundPage.jsx`, with the comment pointing at `SUGGESTED` and at `backend/main.py` `SHOWCASE_QUESTIONS`.

## /auth/callback

- A centred minimal state on the grid background:
  - the wordmark
  - "Signing you in…" with a small spinner, which stops under reduced motion
  - on error: the mapped message, an `AlertTriangle` icon, and "Taking you back to sign in." while the 3s redirect runs
- Logic unchanged.

## Left to the builder

- Exact spacing and sizes within the mockup's proportions.
- The sample cited answer on the login panel: use a real fact with a real page from the index. Look one up from the HDFC showcase answer's evidence; the mockup's `p.14` is a placeholder. If no clean one is found, use the TCS FY2024 revenue answer (`p.90`, verified in the 6.2 browser check).
- How the `/engineering` "Loading eval results…" and error states look, as long as they stay plain text in the new style.
- Whether `Footer` appears on login and register. The mockup shows none; the builder may leave it off.
