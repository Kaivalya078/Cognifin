# Upload Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an "upload its annual report" card under a whole-answer "Not available in the provided documents." reply, opening the existing upload panel.

**Architecture:** A pure `isRefusal(text)` helper decides; `MessageList` renders the card; the upload panel's open state lifts from `ChatInput` to `ChatPage` so the card can open it.

**Tech Stack:** React 18, Vite, Node `assert` check script (the frontend has no test runner).

**Spec:** `docs/superpowers/specs/2026-11-24-upload-card-design.md`

## Global Constraints

- Trigger text, exact: `Not available in the provided documents.` (compare on trimmed content; also accept without the final period).
- Card copy: "Cognifin's filings don't cover this yet. Have the company's annual report? Upload the PDF to ask about it in this chat."
- Button: signed in → "Upload a PDF" (opens panel); signed out → "Sign in to upload" (link to `/login`).
- Frontend only. Lint must add no new problems; `VITE_API_BASE=https://api.example.test npm run build` must pass.

## Review Focus

1. A reply that *contains* the sentence plus more text (e.g. a table with "Data Not Available") → no card. (`refusal.check.mjs`)
2. The `⚠️ …` error messages and the upload-confirmation message → no card. (`refusal.check.mjs`)
3. Refusal with surrounding whitespace / no trailing period → card. (`refusal.check.mjs`)
4. Clicking the card while the panel is already open keeps it open (doesn't toggle shut). (browser check)
5. Old conversations loaded from history with a refusal show the card. (browser check: reload page, select the chat)

---

### Task 1: Refusal detector, card, and shared panel state

**Files:**
- Create: `frontend/src/utils/refusal.js`, `frontend/src/utils/refusal.check.mjs`
- Modify: `frontend/src/components/chat/MessageList.jsx`, `frontend/src/components/chat/ChatInput.jsx`, `frontend/src/pages/ChatPage.jsx`, `frontend/src/styles/chat.css`

**Interfaces:**
- Produces: `isRefusal(text: string): boolean` in `utils/refusal.js`.
- `ChatInput` props gain `showUploadForm: boolean`, `setShowUploadForm(fn|bool)` (its local state removed).
- `MessageList` props gain `onRequestUpload: () => void` and `canUpload: boolean`.

- [ ] **Step 1: Write the failing check** `refusal.check.mjs`:

```js
assert.equal(isRefusal('Not available in the provided documents.'), true);
assert.equal(isRefusal('  Not available in the provided documents \n'), true);
assert.equal(isRefusal('## Overview\n| X | Data Not Available |'), false);
assert.equal(isRefusal('Revenue rose. Not available in the provided documents.'), false);
assert.equal(isRefusal('⚠️ Server error (500)'), false);
assert.equal(isRefusal(''), false);
```

- [ ] **Step 2: Run** `node src/utils/refusal.check.mjs` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `isRefusal` (comment names `generation/prompt_builder.py:31-32`, `generation/intent_prompts.py:77,167`).
- [ ] **Step 4: Run** the check — Expected: `refusal.check: ok`.
- [ ] **Step 5: Wire the UI**: lift `showUploadForm` to `ChatPage` (both `ChatInput` renders); `MessageList` passes `onRequestUpload={() => setShowUploadForm(true)}` and `canUpload={isAuthenticated}` to assistant bubbles; bubble renders the card when `!isUser && isRefusal(message.content)`.
- [ ] **Step 6: Lint + build** — `npx eslint` on changed files: no new problems; build passes.
- [ ] **Step 7: Browser check** (Review Focus 4, 5): signed out, ask about a company outside the corpus → card with "Sign in to upload"; signed in → "Upload a PDF" opens the panel, second click keeps it open; reload and reopen the chat from the sidebar → card still shows; a normal answer shows no card. Screenshot.
- [ ] **Step 8: Commit** `feat(chat-ui): upload card on "Not available" answers`
