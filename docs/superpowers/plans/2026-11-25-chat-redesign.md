# Phase 6.2 Chat App Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `/chat` on the 6.1 `--cf` tokens. Answers are shown first, and a source pane shows each cited page beside the answer. Emoji and stack names are removed, and the known chat bugs are fixed.

**Architecture:**
- Styles: a new `styles/chat-v2.css`, with classes prefixed `cx-` so they never collide with the old file. The old `chat.css` and `api.css` are deleted in the last task.
- Source state: the open source is page-level state in `ChatPage`. It is rendered as an `<aside>` on desktop, or as a native `<dialog>` sheet below 900px (the dialog gives focus trap, Escape and inert background for free).
- Pure logic: kept in `src/utils/*.js` with Node assert check scripts.

**Tech Stack:** React 19, Vite 7, react-router 7, lucide-react, pdfjs-dist, react-markdown, react-hot-toast (all installed; no new dependencies).

**Spec:** `docs/superpowers/specs/2026-11-25-chat-redesign-design.md`

## Global Constraints

- **Tokens and fonts.** Only `--cf-*` tokens from `styles/tokens.css`. Add a token there only if truly needed. Fonts are JetBrains Mono (mono: chips, figures, wordmark) and Inter (body).
- **Smoked glass** is `background: var(--cf-glass | --cf-glass-strong)` with `backdrop-filter: var(--cf-blur)`. Radii come from `--cf-r-sm/md/lg`, and there are almost no shadows.
- **Banned copy.** None of these strings may appear in the chat UI:
  - `GPT`, `gpt-`, `RAG`, `FAISS`, `BM25`, `LLM`
  - "AI-powered"
  - "Analyst Ready", "Cognifin · Analyst"
  - "Pipeline"
  - any emoji

  `/engineering` keeps its own wording.
- **No middle-dot meta strings** (`A · B`) in the chat UI. No all-caps eyebrows. No `→` appended to buttons.
- **Motion.** Only the pane slide-in, ≤ 200ms, and none under `prefers-reduced-motion: reduce`. No GSAP or Lenis in the chat.
- **Logic stays as it is.** These must keep working unchanged:
  - conversation storage and streaming
  - upload
  - the `?q=` handoff
  - the anonymous 429 → sign-in link
  - the refusal → upload card
  - `openFiling` for `fin_N` items, which opens in a new tab
- **Accessibility.**
  - a visible focus ring on every control (`outline: 2px solid var(--cf-gold)`, offset 2px)
  - icon-only buttons have `aria-label`
  - muted text uses `--cf-mute` or brighter
- **Viewports.** At 375×667 and 1280×720: no horizontal scroll, and the input is visible on load, including with the health banner showing.
- **Showcase questions.** Copy them exactly, in this order, in both `backend/main.py` `SHOWCASE_QUESTIONS` and the welcome list:
  1. "What was TCS's consolidated revenue from operations in FY2024?"
  2. "When did the amalgamation of HDFC Limited with HDFC Bank become effective?"
  3. "Which acquisitions did the Infosys board approve in fiscal 2025?"
  4. "What was Hindustan Unilever's profit after tax in FY2025?"
- **Checks on every task.** Run these from `frontend/`:
  - `npm run lint`
  - every `src/utils/*.check.mjs`, with new ones added to the CI `Unit checks` line in `.github/workflows/*.yml`
  - `VITE_API_BASE=https://api.example.invalid npm run build`

  Tasks that touch the backend also run `python -m pytest -q` from `backend/` (395 pass today).
- **Browser checks.** Check in a real browser: dev server on :5173 (CORS), backend running. Questions cost a few gpt-4o-mini calls, and the showcase questions are pre-answered.

## Review Focus

1. **A source opened while streaming or switching chats.** Switching or starting a chat must close the pane, and no stale page may stay open for another chat (Task 1 browser check; Task 2 wires `onOpenSource` only on finished messages).
2. **Two chips for the same PDF at different pages.** The pane must reuse the loaded document and only change the page, with no reload flash. Also, opening the same chip twice must not toggle it closed (Task 1).
3. **Undo after the toast is gone, or after a reload.** Once the timer fires, Undo is a no-op. `pagehide` sends pending deletes. A delete dropped by a killed tab makes the chat reappear, and no other chat is ever deleted (`deleteQueue.check.mjs`, Task 4).
4. **Evidence items that lack a page or URL.** `page_number` may be 0 and `pdf_url` may be missing (uploads). Sources grouping must not crash, and a missing page shows no `p.0` (`chatFormat.check.mjs`, Task 2).
5. **The focus path.** Focus returns to the opening chip on close (Escape, the Close button, or dialog cancel). It also returns when a chip in the Sources row opened the pane (Task 4 browser check).

---

### Task 1: Layout shell and source pane

**Files:**
- Create:
  - `frontend/src/styles/chat-v2.css`
  - `frontend/src/components/chat/SourcePane.jsx`
- Modify:
  - `frontend/src/pages/ChatPage.jsx`
  - `frontend/src/components/chat/MessageList.jsx` (chip and evidence "Open" call `onOpenSource`)
- Delete:
  - `frontend/src/components/chat/PDFViewerModal.jsx`

**Interfaces:**
- **Produces:**
  - `SourcePane({ item, pdfUrl, onClose, titleId })`: renders the header (document label, `p.N`, prev/next, zoom −/+, "Open in new tab" link, Close) and the canvas with highlight.
  - `ChatPage` state `source: { item, anchor: HTMLElement } | null`.
  - `openSource(item, anchorEl)` passed to `MessageList` as `onOpenSource`.
  - `activeSourceId = bare(source?.item.chunk_id)` passed to `MessageList`.
  - `pdfUrlOf` and `openFiling` move from `MessageList.jsx` into `frontend/src/utils/sources.js` (exported), so `ChatPage`, `SourcePane` and `MessageList` share them.

- [ ] **Step 1: Write `SourcePane.jsx`.** Move the pdf.js code from `PDFViewerModal.jsx` and split its effects:
  - document load depends on `[pdfUrl]` only
  - `currentPage` resets from `item.page_number` in a separate effect on `[item]`
  - rendering depends on `[pdfDoc, currentPage, scale, highlightWords]`

  This way a new chip on the same PDF only changes the page. Keep the render-task cancel and the highlight code. While a page renders, show a skeleton (an empty page-shaped block). On load failure, show "Couldn't load this page." plus the "Open in new tab" link.
- [ ] **Step 2: Wire `ChatPage`.**
  - `openSource(item, anchorEl)`:
    - for `fin_N` → `openFiling(item)`, no pane
    - otherwise set `source`, remember `sidebarCollapsed` in a ref, and collapse the list
  - `closeSource()` restores the remembered state and calls `anchor?.focus()`. Ctrl+B while the pane is open updates the remembered value.
  - An `activeId` change calls `closeSource()` without focusing.
  - `useMediaQuery('(max-width: 899px)')`: a small inline hook in `ChatPage.jsx` using `matchMedia` and its change event.
    - Desktop renders `<aside className="cx-source" aria-label={label}>`.
    - Mobile renders `<dialog className="cx-sheet">`, opened with `showModal()` in an effect, with `onCancel` → `closeSource` and `aria-labelledby` pointing at the pane title.
  - Escape on desktop: a keydown listener while `source` is set calls `closeSource()`.
- [ ] **Step 3: Update `MessageList`.**
  - Chips call `onOpenSource(item, e.currentTarget)`.
  - A chip whose bare id equals `activeSourceId` gets `cx-chip is-active` and `aria-pressed="true"`.
  - Evidence "Open PDF" calls `onOpenSource` the same way.
  - Remove the per-bubble modal state (`citeItem`, `pdfOpen`).
- [ ] **Step 4: Write the layout in `chat-v2.css`.**
  - `.cx-page`: full-height grid, `--cf-bg` background, `--cf-ink` text.
  - The main area is a two-column grid when a source is open: conversation `minmax(0,1fr)` and pane `45%`.
  - The conversation column is centred with `max-width: 760px`.
  - The pane slides in from the right in 180ms; under reduced motion there is no transition.
  - The mobile sheet fills the screen, with `::backdrop` at `rgba(6,7,12,.7)`.
- [ ] **Step 5: Verify.** Run the checks in Global Constraints. Expected: lint clean, all checks ok, build succeeds.
- [ ] **Step 6: Browser-check at 1280×720.** Ask the TCS showcase question.
  - Clicking `p.56` opens the pane with page 56 highlighted, and the list folds.
  - Clicking another chip on the same PDF changes the page with no reload.
  - Escape closes the pane, the list comes back, and focus is on the chip.
  - Switching chat closes the pane.

  Then at 375×667: the chip opens the full-screen sheet, and the Back/Close button and Escape close it.
- [ ] **Step 7: Commit.**

```bash
git add -A frontend/src
git commit -m "feat(chat): source pane beside the answer (sheet on mobile) replaces the PDF modal"
```

### Task 2: Answer-first messages

**Files:**
- Create:
  - `frontend/src/utils/chatFormat.js`
  - `frontend/src/utils/chatFormat.check.mjs`
- Modify:
  - `frontend/src/components/chat/MessageList.jsx`
  - `frontend/src/components/chat/LoadingIndicator.jsx`
  - `frontend/src/components/chat/stageLabels.js`
  - `frontend/src/components/chat/FinancialChart.jsx` (class names only)
  - `frontend/src/styles/chat-v2.css`
  - `.github/workflows/*.yml` (Unit checks line)

**Interfaces:**
- **Consumes:** `onOpenSource` and `activeSourceId` from Task 1.
- **Produces:**
  - `sourceGroups(evidence, citations) -> [{ label, items }]`. It keeps only evidence whose `chunk_id` is in `citations`. It groups by `document_label` (falling back to `chunk_id`), in first-cited order, with items sorted by `page_number` ascending and deduped by page.
  - `detailsItems(pipeline) -> string[]`. It returns, in order:
    - `Confidence N%` (when `confidence` is a number)
    - `secs(latency_ms)` from `metricsFormat` (when present)
    - `Cached` (when `cached`)
    - the intent (when it is not `lookup`)
  - `stageLine(stages) -> string`. With no stages it returns `'Searching filings…'`. Otherwise it returns the plain label of the last stage, or `'Writing answer…'` once `context_assembly` is done.
  - `STAGE_LABELS` becomes `{ retrieval: 'Searching filings', reranking: 'Ranking passages', intelligent_retrieve: 'Searching filings', context_assembly: 'Reading passages' }`, with no icons.

- [ ] **Step 1: Write the failing check `chatFormat.check.mjs`.**

```js
import assert from 'node:assert/strict';
import { sourceGroups, detailsItems, stageLine } from './chatFormat.js';
const ev = [
  { chunk_id: 'chunk_2', document_label: 'TCS AR 2023-24', page_number: 112 },
  { chunk_id: 'chunk_1', document_label: 'TCS AR 2023-24', page_number: 56 },
  { chunk_id: 'chunk_3', document_label: 'TCS AR 2023-24', page_number: 56 },
  { chunk_id: 'chunk_4', document_label: 'INFY AR 2024-25', page_number: 0 },
  { chunk_id: 'chunk_5', document_label: 'Uncited', page_number: 9 },
  { chunk_id: 'chunk_6', page_number: 3 },
];
const g = sourceGroups(ev, ['chunk_2', 'chunk_1', 'chunk_3', 'chunk_4', 'chunk_6']);
assert.deepEqual(g.map((x) => x.label), ['TCS AR 2023-24', 'INFY AR 2024-25', 'chunk_6']);
assert.deepEqual(g[0].items.map((i) => i.page_number), [56, 112]);
assert.deepEqual(sourceGroups(ev, []), []);
assert.deepEqual(sourceGroups(undefined, undefined), []);
assert.deepEqual(detailsItems({ confidence: 0.751, latency_ms: 10671, cached: true, intent: 'comparison' }),
  ['Confidence 75%', '10.7 s', 'Cached', 'comparison']);
assert.deepEqual(detailsItems({ confidence: 0.5, intent: 'lookup' }), ['Confidence 50%']);
assert.deepEqual(detailsItems({}), []);
assert.equal(stageLine([]), 'Searching filings…');
assert.equal(stageLine([{ name: 'retrieval', ms: 120 }]), 'Searching filings…');
assert.equal(stageLine([{ name: 'retrieval' }, { name: 'reranking' }]), 'Ranking passages…');
assert.equal(stageLine([{ name: 'retrieval' }, { name: 'context_assembly' }]), 'Writing answer…');
assert.ok(!/FAISS|BM25|ms/.test(stageLine([{ name: 'retrieval', ms: 5 }])));
console.log('chatFormat.check: ok');
```

- [ ] **Step 2: Run the check.** `node src/utils/chatFormat.check.mjs`. Expected: FAIL, "Cannot find module … chatFormat.js".
- [ ] **Step 3: Implement `chatFormat.js`** (and update `stageLabels.js`) to the signatures above.
- [ ] **Step 4: Run the check again.** Expected: `chatFormat.check: ok`. Add it to the CI Unit checks line.
- [ ] **Step 5: Rewrite the message markup.**
  - **User message:** right-aligned `cx-q` block with the text only.
  - **Answer:** `cx-a` prose with no bubble, avatar or role label; the time is optional, muted.
  - **Chips:** `cx-chip`.
  - **Sources row:** "Sources:" then each group label followed by its pages as `cx-chip` buttons (`p.N`, or the label alone when the page is 0) calling `onOpenSource`.
  - **Actions:** Copy (lucide `Copy`/`Check`) and a **Details** toggle (`aria-expanded`) that shows `detailsItems` as separate muted spans plus the passages list. "Open page" is offered when `pdfUrlOf(item)` is truthy.
  - **Follow-ups:** plain text buttons.
  - **Delete:** `MetadataBar` and `PipelinePanel`.
  - **Restyle:** the upload card and `FinancialChart` with `cx-` classes.
- [ ] **Step 6: Update `LoadingIndicator`.** Use `stageLine(stages)` with no avatar or role label, keep the streaming cursor, and keep chips inert.
- [ ] **Step 7: Verify and browser-check.**
  - Run the checks.
  - Ask the TCS question at 1280×720. The answer shows chips, "Sources: TCS AR … p.56 …" and Details (confidence, seconds). No emoji or stack names appear while streaming or after.
- [ ] **Step 8: Commit.** Message: `"feat(chat): answer-first messages with sources row and Details; drop pipeline panel"`.

### Task 3: Sidebar, input, welcome, upload overlay, toasts, showcase questions

**Files:**
- Modify:
  - `frontend/src/components/chat/Sidebar.jsx`
  - `frontend/src/components/chat/ChatInput.jsx`
  - `frontend/src/components/chat/ChatHeader.jsx`
  - `frontend/src/pages/ChatPage.jsx`
  - `frontend/src/styles/chat-v2.css`
  - `backend/main.py:761-766`
  - `backend/tests/calibration_queries.json` (note only)

**Interfaces:**
- **Consumes:** `Wordmark` from `components/landing/Navbar.jsx`.
- **Produces:** `SHOWCASE_QUESTIONS` (the exact list in Global Constraints). The frontend constant is `SUGGESTED` in `ChatPage.jsx`, with its "Must match SHOWCASE_QUESTIONS in backend/main.py" comment.

- [ ] **Step 1: Swap the backend list.** Replace `SHOWCASE_QUESTIONS` in `backend/main.py` with the four Global Constraints questions. In `calibration_queries.json`, change the note's last sentence to "The first four were the pre-Phase-6.2 showcase questions." (the queries stay; calibration must not change).
- [ ] **Step 2: Run the backend suite.** `python -m pytest -q` from `backend/`. Expected: 395 passed (`test_showcase_questions_are_prewarmed_and_never_expire` iterates the list).
- [ ] **Step 3: Restyle the chat list.**
  - Sidebar: `Wordmark` replaces the TrendingUp icon plus "Cognifin", in a smoked glass column.
  - Collapsed: a thin rail with the toggle and New chat (icon buttons with `aria-label`).
  - The context menu and the guest/user footer are restyled.
- [ ] **Step 4: Header and input.**
  - `ChatHeader`: only the list toggle when the list is collapsed. Remove the model line and status, and drop the bar when it would be empty.
  - `ChatInput`: smoked glass bar, attach and upload form, and the PDF pill with clear, restyled.
- [ ] **Step 5: Welcome screen.**
  - The `Wordmark`, then "Ask about any NIFTY 50 company's filings."
  - `SUGGESTED` as plain text buttons.
  - The text "Shortcuts:" with `<kbd>Ctrl+N</kbd> new chat` and `<kbd>Ctrl+B</kbd> chat list`.
  - The input.
- [ ] **Step 6: Upload overlay and toasts.**
  - Upload overlay: a glass card. The title is "Analysis ready" or "Processing PDF" (no ✓). The `✅` upload message becomes `**{file}** is ready: {n} passages indexed. Ask about it in this chat.`
  - Toaster `toastOptions.style`: `--cf` values, mono 13px. Remove the `icon` options (or set `icon: null`) for the "New chat", "PDF session cleared" and "Chat deleted" toasts.
  - Error messages lose the `⚠️ ` prefix.
- [ ] **Step 7: Verify and browser-check.**
  - Run the frontend checks.
  - The welcome screen at 1280×720 and 375×667 shows the four questions, and clicking one answers instantly (pre-warmed after a backend restart).
  - The collapsed rail and the context menu work.
- [ ] **Step 8: Commit.** Message: `"feat(chat): restyle list, input and welcome; showcase questions name their company"`.

### Task 4: Accessibility and polish (undo delete, banner, error boundary, emoji sweep, old CSS deleted)

**Files:**
- Create:
  - `frontend/src/utils/deleteQueue.js`
  - `frontend/src/utils/deleteQueue.check.mjs`
  - `frontend/src/components/chat/ChatErrorBoundary.jsx`
- Modify:
  - `frontend/src/hooks/useConversations.js`
  - `frontend/src/pages/ChatPage.jsx`
  - `frontend/src/components/chat/Sidebar.jsx` (unchanged API: still calls `onDelete(id)`)
  - `.github/workflows/*.yml`
- Delete:
  - `frontend/src/styles/chat.css`
  - `frontend/src/styles/api.css`

**Interfaces:**
- **Produces:**
  - `createDeleteQueue({ delayMs, commit, timers = { setTimeout, clearTimeout } }) -> { schedule(id), undo(id) -> boolean, flush() }`
    - `schedule` starts a timer that calls `commit(id)` once.
    - `undo` cancels it and returns `true` if still pending, else `false`.
    - `flush` commits every pending id now and clears their timers.
  - `useConversations` returns:
    - `deleteConversation(id)`, which hides the chat and schedules it with `delayMs: 5000` and `commit: deleteConversationApi`
    - a new `undoDelete(id)`, which restores the hidden conversation at its old index
  - `pagehide` calls `flush()`.

- [ ] **Step 1: Write the failing check `deleteQueue.check.mjs`.** Use fake timers: an object whose `setTimeout` stores callbacks and whose `clearTimeout` deletes them.
  - `schedule('a')`, then fire the timers → `commit` called with `['a']`.
  - `schedule('b')`, `undo('b')` → `true`, fire → `commit` not called for `b`; `undo('b')` again → `false`.
  - `schedule('c')`, `schedule('d')`, `flush()` → commits `c` and `d`, and firing afterwards commits nothing more.
  - `undo('zzz')` → `false`, and `commit` is never called for an id that was not scheduled.
- [ ] **Step 2: Run the check.** `node src/utils/deleteQueue.check.mjs`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `deleteQueue.js`.** Run the check again. Expected: `deleteQueue.check: ok`. Add it to the CI line.
- [ ] **Step 4: Wire it in.**
  - `useConversations` keeps hidden conversations in a ref map `id → { conv, index }`. `commit` failures are logged and the chat is restored.
  - Every delete path in `ChatPage` (Ctrl+Backspace and the sidebar's `onDelete`) shows `toast((t) => <span>Chat deleted <button onClick={() => { undoDelete(id); toast.dismiss(t.id); }}>Undo</button></span>, { duration: 5000 })`.
- [ ] **Step 5: Error boundary.** `ChatErrorBoundary` is a class component with `getDerivedStateFromError`. It renders "Something went wrong displaying this chat." and a **Reload** button (`location.reload()`), and wraps the main conversation and the source pane.
- [ ] **Step 6: Health banner.** It becomes a slim row inside the main column's grid (above the messages, not above the whole page). The input must stay visible at 375×667 with the banner showing. Its copy is "Can't reach the server. It may still be starting up." with a lucide `AlertTriangle` icon and a Dismiss button (`aria-label="Dismiss"`). It no longer shows the raw API URL.
- [ ] **Step 7: Delete the old CSS and sweep.**
  - Delete `chat.css` and `api.css` and their imports.
  - Make sure every class still used in the chat has a `cx-` rule. This command must print nothing:

    ```bash
    grep -rnoE "className=\"[^\"]*\"" src/pages/ChatPage.jsx src/components/chat | grep -v cx-
    ```

  - Emoji and banned-copy sweep: this command must print nothing:

    ```bash
    grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]|GPT|FAISS|BM25|RAG Pipeline|AI-powered|Analyst" src/pages/ChatPage.jsx src/components/chat
    ```

- [ ] **Step 8: Verify and browser-check.**
  - Run all checks and the build.
  - Ctrl+Backspace hides the chat, and Undo restores it. Without Undo it is gone after reload.
  - A delete followed by an immediate reload brings the chat back or deletes it (`pagehide` flush), and never deletes a different chat.
  - The mobile sheet traps Tab and Escape returns focus to the chip.
  - With the backend stopped, the banner shows and the input is visible at both viewports.
  - Keyboard: Tab through the welcome, sidebar, input and chips, and every control shows the gold focus ring.
- [ ] **Step 9: Commit.** Message: `"feat(chat): undo delete, error boundary, banner keeps input visible; drop legacy chat CSS"`.
