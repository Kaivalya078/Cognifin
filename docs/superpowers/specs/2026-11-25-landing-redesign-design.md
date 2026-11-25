# Phase 6, project 1: design system + landing page — design

Date: 2026-11-25. Branch: `phase-6-landing` (to be created from `main`).

## Intent

Phase 6 is a full visual overhaul of the site, run as three projects in this order: **(1) design system + landing page** (this doc), (2) chat app, (3) login, register, `/engineering` and 404. Phase 5.5 (NIFTY Next 50) now comes after Phase 6.

The user wants "the best possible landing page" and a professional site, in a **smoked liquid glass** look that matches their personal site, https://www.kaivalyapatel.dev/. Cognifin is a portfolio project: visitors arriving from that site should see the same designer's hand. The current landing page (a generic centred hero card, the "Unlock Your Assets Spark!" badge, glowing navy and gold cards) reads as a template.

## Goals

- A new landing page (`/`) that explains in about 5 seconds what Cognifin does differently: every answer points to its page.
- A shared set of design tokens that projects 2 and 3 will build on.
- Vendor and model mentions removed from the landing page, navbar and footer ("Powered by OpenAI/LanceDB/React/FastAPI", "powered by GPT-4"). Model names stay only on `/engineering`, where they are part of the method. The chat header's "GPT-4o-mini · RAG Pipeline · NIFTY 50 Corpus" is removed in project 2.

## Non-goals

- Restyling the chat, auth pages, `/engineering` or a 404 page; those are projects 2 and 3. `/engineering` keeps working, using the new navbar and footer and its current body styles (it already uses the landing palette variables, which this project keeps working; see Tokens).
- A light theme.
- Any backend change.

## Anti-goals

- Looking AI-generated or templated: no gradient headline text, no glowing rounded feature cards, no emoji, no stock "sparkle" badges.
- Copying the personal site: Cognifin is a **sibling** (user's choice A), with the same base language, a muted gold accent of its own, and its own hero motif. No koi or ASCII creatures.
- Hardcoded or flattering numbers: every figure on the page comes from `public/metrics.json` or is a real golden-set case.
- Heavy 3D: no three.js or Vanta (about 600 KB, against the Lighthouse ≥ 90 target).

## Visual language (from kaivalyapatel.dev, measured in the browser 2026-11-25)

- Background `#06070c` with a faint 22 px grid of hairlines at `rgba(233,230,223,.09)` (lower opacity in practice).
- Smoked glass: `background: rgba(9,10,16,.72–.88)`, `backdrop-filter: blur(14px) saturate(1.2)`, 1 px hairline border. Small radii (6–14 px), and almost no shadows.
- Type: **JetBrains Mono** (500) for headings, the wordmark, numbers, tickers and citation chips; **Inter** (400/500/600) for body text. Text is a warm off-white `#e9e6df`, with sub and muted tiers at 58% and 32% alpha.
- Accent: muted gold `#c9a24a`, plus a soft fill `rgba(201,162,74,.14)` used for highlights and citations.
- Wordmark: lowercase `cognifin` in mono, followed by a gold `.`

## Approaches

- **Restyle in place with plain CSS plus a tokens file (picked, my call).** Keep React, Vite and the plain CSS the project uses today. Add `styles/tokens.css` and rewrite the landing components. The only new dependencies are `gsap` and `lenis`.
- Adopt Tailwind or a component kit (e.g. shadcn). Rejected: it means a new styling system across about 4,000 lines of existing CSS for a mostly bespoke look, and a second system during the migration.
- ReactBits glass components through its MCP server. Rejected as a base, because those components are generic and some use WebGL. Their glass recipe is matched by the CSS above. They may be consulted for reference only.

Hero layout (user's choice, from three mockups): **B "Filing scan"** as the hero, with **C "Product window"** as the section under it. A's ask bar is reused as the final CTA.

## Page structure (approved with the user)

1. **Navbar:** sticky smoked glass. `cognifin.` · Product (→ #product) · How it works (→ #how) · Engineering (→ /engineering) · **Open app** (→ /chat). Mobile: wordmark plus a menu button that opens a glass sheet with the same links. It must fit at 375 px with no overlap.
2. **Hero (B):**
   - Left: mono eyebrow `FINANCIAL FILINGS · NIFTY 50`; h1 "Every answer points to its page."; a paragraph ("Ask about any NIFTY 50 company. Cognifin reads the annual reports and quarterly results, answers in plain language, and shows you the exact line it used."); buttons **Try a question** (→ /chat) and **See how it's measured** (→ /engineering).
   - Right: a stylised filing page (TCS · Annual Report 2023-24 · p.17). A gold scan line sweeps down, "Revenue from operations 2,40,893" highlights, then an answer card slides up: "What was TCS's revenue in FY24?" → "Consolidated revenue from operations was ₹2,40,893 crore, up 6.8% year on year." with a `p.17` citation chip.
   - These are real figures: `tcs-2024-revenue` in the golden set; FY23 was ₹2,25,458 crore, so the growth is 6.8%. The builder confirms the page number against `golden_set.json` `answer_pages`.
   - The GSAP timeline loops about every 8 s.
   - Mobile: the text comes first, the animation below it, scaled down.
3. **Product window (C), id `product`:**
   - A frosted app window. Left: a user question bubble, the answer with citation chips, and a small gold line chart. Right: the cited filing page with the sentence highlighted.
   - It uses one real case. The builder picks one whose figures are verifiable in `index_cache/financials.duckdb` or the golden set; the mockup's HDFC NPA figures were placeholders.
   - It rises in once on scroll (GSAP ScrollTrigger).
   - It is static markup, not a live app embed.
4. **How it works, id `how`:**
   - Three mono-numbered rows separated by hairlines: `01 Ask` (plain-language question about any covered company); `02 Search` ("186 filings: annual reports and quarterly results, searched by meaning and keyword, then reranked"); `03 Answer` ("figures checked against the financials table; every claim cites its page").
   - The "186" comes from `metrics.json` `index.documents`.
5. **Proof:**
   - Four mono figures from `metrics.json`: faithfulness, correctness, companies (`golden_set.companies`), filings (`index.documents`). Each has a short label, reusing the 5.4 wording: "claims backed by the passages shown", "vs the answer key; partial counts ½".
   - A link "How it's measured →" to /engineering.
   - If the fetch fails, the section is hidden. It never shows placeholder numbers.
6. **Coverage:**
   - A wall of the covered company tickers in mono (47 today), with the heading "47 NIFTY 50 companies covered" (count from the list).
   - Below it: "Company not listed? Upload its annual report in the app." linking to /chat.
   - Source: a static `src/data/companies.js` array of symbols (my call: there is no backend endpoint, and the list changes only when the corpus is rebuilt, next in Phase 5.5).
   - A check script asserts its length equals `public/metrics.json` `golden_set.companies`, so the two cannot drift silently. `KWIL` is excluded because it has no reports.
7. **Final CTA:**
   - Heading "Ask your first question." and a smoked-glass input (the hero A ask bar) with an **Ask** button, plus three example chips (real questions the app answers well, taken from the golden set).
   - Enter, a click on Ask, or a click on a chip navigates to `/chat?q=<question>`.
8. **Footer:** `cognifin.` · Engineering · GitHub (repo link) · © year. No "Powered by" list.

## Dependency: citations must be real first (user's decision, builder check)

The page's promise ("Every answer points to its page", the citation chips in the hero and product window, and how-it-works step 03 "every claim cites its page") is **not true today**: `metrics.json` `cited_share` is 0.021, so about 98% of answers show no "Sources:" chips. Each answer still shows its Evidence list, which gives document, page and Open PDF for the passages it was given, not the lines it used. The user chose to **fix citations first** (a separate project, *Phase 6.0 citations*, its own design) and keep this copy.

This project must not merge until the eval rerun after Phase 6.0 shows citations are reliable. The target is set in the Phase 6.0 design. If that target isn't met, the copy falls back to evidence wording ("Answers built from the filings, with the source pages one click away") before merging, never to an untrue claim.

## Chat handoff (small, needed by section 7)

`ChatPage` reads `?q=` once on mount. If present and non-empty, it sends that question through the existing `handleSend` and removes `q` from the URL (`replace`), so a refresh doesn't resend. My call: auto-send rather than pre-fill, because the visitor already pressed Enter once. The anonymous trial cap still applies on the backend.

## Tokens

- New `src/styles/tokens.css` (imported once in `main.jsx`) defines the palette, the two font stacks, radii, glass recipe values and spacing.
- The landing page uses only these tokens.
- The old `--c-*` variables in `landing.css` are kept, mapped onto the new tokens, until projects 2 and 3 move `/engineering` and the rest. Example: `--c-gold: var(--accent)`.
- `App.css` (dead, leaks a stale indigo palette) and the four dead components (`AnswerView`, `EvidenceList`, `EvidenceItem`, `QuestionBox`) are deleted here, because they collide with the new global tokens. The builder confirms they are unreferenced before deleting.
- Fonts: add JetBrains Mono (400/500) to the existing Google Fonts link in `index.html`, and trim Inter to 400/500/600.

## Motion and libraries

- `gsap` (free, including ScrollTrigger) for the hero loop and scroll reveals.
- `lenis` for smooth scrolling on the landing page only, not the chat, where nested scroll areas would conflict.
- `prefers-reduced-motion: reduce` turns off Lenis, the hero loop (it shows the final frame, with the answer card visible) and all reveals.
- The faint grid background is CSS only.

## Constraints

- Zero cost; no new paid service. `gsap` and `lenis` are the only new dependencies.
- At 375 px wide: no horizontal scroll, and the navbar fits.
- Lighthouse on `/` (production build): accessibility ≥ 90, as the Phase 6 target, and performance not below today's.
- Accessibility basics:
  - one h1, ordered headings, and visible focus rings on every interactive element
  - the decorative hero animation is `aria-hidden`, with its message carried by the text
  - the mobile menu button has `aria-label` and `aria-expanded`
  - every interactive element is keyboard reachable
- `npm run lint`, the existing check scripts and `VITE_API_BASE=https://api.example.invalid npm run build` pass. New check script(s) are added to the CI `Unit checks` line.

## Calls made after the builder check (mine)

- New token names must not clash with `chat.css`'s generic `:root` variables (`--border`, `--text`, `--bg-card`, ...), which stay loaded after a visit to `/chat`. Use a prefix, e.g. `--cf-*`. Keep the `.landing-page` and `.section-label` rules that `/engineering` still uses.
- Company list for the coverage wall: the 47 companies in `tests/golden_set.json`, which match `golden_set.companies` and `index.companies`.
- Hero figures: p.17 is in `tcs-2024-revenue` `answer_pages`. Check the FY23 ₹2,25,458 crore figure behind "up 6.8%" in `index_cache/financials.duckdb` or the FY24 report; if it can't be verified, drop the growth clause.
- `?q=` handoff: `activeId` starts as `null`, so the question opens a new chat. Guard against StrictMode's double-run sending it twice.

## Left to the builder

- Exact spacing, sizes, easing curves and timings.
- The product-window case and the three CTA example questions, picked from real, verified cases.
- Component and file split under `src/components/landing/`.
- Whether the grid fades toward the edges.
