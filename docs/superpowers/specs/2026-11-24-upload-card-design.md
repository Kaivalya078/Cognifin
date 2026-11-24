# Upload card on "Not available" answers

Date: 2026-11-24 · Branch: `upload-card` · Size: small change

## Intent

When someone asks about a company Cognifin hasn't indexed, the answer today is a dead end
("Not available in the provided documents."). Offer the way forward that already exists:
upload that company's annual report into this chat. This replaces the planned automated
fetching, which the user dropped (demo project, no added cost; the only discovery source
that works for any company, a search API, needs a card). Coverage grows separately through
Phase 5.5 (NIFTY Next 50).

## Goals / non-goals

- Goal: a whole-answer refusal shows a card with an action that opens the existing upload panel.
- Non-goal: detecting company names that aren't in the corpus; fetching anything; backend changes.
- Anti-goal: the card appearing on normal answers, or on answers with only a partial gap.

## Approaches

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | Automated fetching via a web search API | Covers any company; needs a paid/card-backed key | Dropped by the user (cost) |
| B | Hand-kept list of company IR pages + cron scraper | No key; covers only listed companies, brittle | Not chosen |
| **C** | **Upload card on a "Not available" answer** | **Almost no code; not automatic** | **Picked by the user** |

## Design

- **Trigger (my call):** the assistant message's trimmed content equals the refusal sentence
  `Not available in the provided documents.` — the exact text all three prompts mandate
  (`generation/prompt_builder.py:31-32`, `generation/intent_prompts.py:77,167`). One
  constant in the frontend, with a comment naming those files. Detecting from text (not a
  new backend flag) makes it work for cached answers and conversations loaded from history.
- **Card** under the reply: "Cognifin's filings don't cover this yet. Have the company's
  annual report? Upload the PDF to ask about it in this chat." plus a button.
- **Button:** signed in → "Upload a PDF", opens the same panel as the paperclip.
  Signed out → "Sign in to upload", links to `/login` (uploads require an account).
- **Wiring:** the upload panel's open/closed state moves up from `ChatInput` to `ChatPage`
  so both the paperclip and the card can open it.
- **Check:** asking about a company outside the corpus in a fresh chat shows the card; the
  button opens the panel; a normal answer never shows it.

## Left to the builder

Card styling (reuse existing chat CSS tokens; Phase 6 restyles anyway).
