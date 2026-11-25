# /engineering page (Phase 5, piece 4) — short design

Date: 2026-11-25. Branch: `phase-5-engineering`.

## Intent

A public page that shows, honestly, how well Cognifin works. Readers are recruiters and interviewers looking at a portfolio project. Numbers come from the committed eval run (piece 3), so anyone can regenerate them with one command.

## Goals / non-goals / anti-goals

- Goal: a 10-second skim of the headline numbers, plus a short explanation of how they're measured, for readers who keep scrolling.
- Non-goal: live traffic numbers. No cache hit rate, no live latency, no new backend endpoint (user's choice: approach A).
- Anti-goal: a page that flatters. The weak spots from the README (2% cited, 3/8 quarterly refused, judge ±1 pt) are shown on the page, not hidden.
- Anti-goal: looking like a generated dashboard template (brief: polished, must not look AI-made).

## Approaches

- **A, eval snapshot only (picked).** Every number comes from `frontend/public/metrics.json`, the committed v2 baseline. Free, and works the moment the frontend is deployed.
- B, snapshot plus a live `/stats` strip (cache hit rate, recent latency). Rejected for now: needs the backend deployed, resets on every restart, and adds a public endpoint.
- C, B with the stats kept in Atlas. Rejected: most work, premature before deploy.

Layout (user's pick from three mockups): **hybrid**. Scorecard on top, then a write-up underneath. The other two were scorecard-only and write-up-only.

## Design

- Route `/engineering` in `App.jsx`, page `pages/EngineeringPage.jsx`, styles in `styles/engineering.css`. Reuses the landing page's look: navy `#080d17`, gold `#d4af37`, Inter, `--container`.
- **Data:** fetch `/metrics.json` at runtime (my call: the eval runner already writes it to `frontend/public/`, and the raw file is linked on the page as "raw data"). If the fetch fails, show a plain message. Never show fake numbers.
- **Top:** a line with the run date, question count and company count. Then four tiles: faithfulness, correctness, retrieval hit@8, latency p50 (with p95 underneath).
- **Below, two columns** (stacked on mobile, no horizontal scroll at 375 px):
  - Left: "How it's measured", 3–4 short paragraphs on the golden set, the real pipeline, the claim-by-claim judge, and what each tile means. Then a "Known weak spots" box.
  - Right: a by-type table (narrative / table figures / quarterly numbers / should-refuse: n, correct, faithful), then a small facts list (refusal accuracy, citation validity, cited share, hit@3, cost per question with and without judge, index size: docs, chunks, disk).
- **Footer of page:** the reproduce command `PYTHONUTF8=1 python -m tests.eval_answers --label NAME`, the models (generation and judge), and links to the raw `metrics.json` and the GitHub eval README.
- **Weak-spots text** is static copy in the page (my call), written from the v2 README. It gets updated by hand when a new run changes it. It's short, and generating it from data would be guesswork.
- **Link:** "Engineering" added to the landing navbar (desktop and mobile) and the footer.
- No new dependencies. Percentages are formatted from the raw fractions in `metrics.json`; null values show "—".

## Left to the builder

Exact copy wording, spacing and motion (framer-motion is available; keep it subtle). One small check script for the number formatting, following the existing `utils/*.check.mjs` pattern.
