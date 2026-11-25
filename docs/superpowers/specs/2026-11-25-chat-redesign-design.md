# Phase 6.2: Chat app redesign

## Intent

Phase 6 is a full visual overhaul in three projects. 6.1 (design system and landing page) is merged. This is project 2, the chat app at `/chat`. It should look like the landing page and its sibling site, kaivalyapatel.dev: smoked near-black, smoked glass, JetBrains Mono and Inter, and muted gold. It must look professional and not AI-generated. Vendor and model names go ("GPT-4o-mini · RAG Pipeline", "FAISS + BM25", "Generation (gpt-4o-mini)"). The method stays told on `/engineering`.

The chat's core promise, from the landing hero, is "Every answer points to its page." The redesign makes that literal: clicking a citation chip shows the page beside the answer instead of in a modal clipped inside the bubble.

## Goals

1. **Answer first (user's pick B).** Under each finished answer:
   - the answer text with its page chips
   - a short Sources row
   - follow-up chips
   - one **Details** toggle

   Details opens confidence %, response time and the retrieved passages (today's Evidence list). It uses plain labels and no stack names. The Pipeline panel (per-stage latency bars, model name) is removed. The Copy action stays.
2. **Source pane (user's pick A).**
   - Clicking a page chip, or "Open page" in a Details passage, opens a source pane to the right of the conversation. It shows that PDF page with the passage highlighted, plus page prev/next and zoom.
   - Opening it folds the chat list away. Closing it restores the list's previous state. Ctrl+B still toggles the list.
   - Desktop split: the pane takes about 45% of the main area, and the answer column keeps a readable width.
   - Below 900px the pane is a full-screen sheet with a Back button.
   - The chip whose page is open shows an active state. Clicking another chip swaps the page in the open pane.
   - `fin_N` chips point to BSE/NSE filings we don't host, so they keep opening in a new tab (`openFiling`, unchanged).
3. **Suggested questions (user's pick A).** The empty chat offers four questions, each naming a company and each answered correctly in eval v3 with the model's own citations:
   - "What was TCS's consolidated revenue from operations in FY2024?"
   - "When did the amalgamation of HDFC Limited with HDFC Bank become effective?"
   - "Which acquisitions did the Infosys board approve in fiscal 2025?"
   - "What was Hindustan Unilever's profit after tax in FY2025?"

   `SHOWCASE_QUESTIONS` in `backend/main.py` becomes this same list (still four pre-warmed answers, so startup cost is unchanged). The frontend list keeps its "must match" comment.
4. **No emoji in the UI.** This covers:
   - the confidence dots 🟢🟡🔴 and the ⚡ and 📄 badges
   - the ⚠️ prefix on error messages and in the health banner
   - the ✅ upload message and the ✓ upload title
   - toast icons and ⌨️ in the shortcuts line
   - the stage icons in `stageLabels.js`

   Use lucide icons where an icon carries meaning, and plain text elsewhere.
5. **Copy with no stack names.**
   - Remove the chat header's model line and the fake "Analyst Ready" status.
   - The welcome text drops "AI-powered financial analyst — trained on…".
   - The live stage line while answering uses plain words. My call, a builder may tune the wording:
     - retrieval → "Searching filings"
     - reranking → "Ranking passages"
     - intelligent_retrieve → "Searching filings"
     - context_assembly → "Reading passages"
     - then "Writing answer"
   - Per-stage ms timings leave the live line.
6. **Accessibility.**
   - The mobile source sheet is a dialog (`role="dialog"`, `aria-modal`, labelled by its document title). It traps focus, closes on Escape and returns focus to the chip that opened it.
   - The desktop pane is a labelled `<aside>` (`aria-label` = document and page). Escape closes it and focus returns to the chip.
   - Every interactive element has a visible focus ring. Muted text keeps ≥ 4.5:1 (`--cf-mute`).
7. **Known bugs fixed.**
   - The "Backend unavailable" banner must not push the input below the fold. It sits inside the layout as a slim row or overlays, so the input stays visible at 375×667 and 1280×720.
   - Every delete path (Ctrl+Backspace, the sidebar's hover button, the right-click Delete) removes the chat from view at once and shows a toast with **Undo**. My call: an undo toast beats a confirm dialog, because it doesn't interrupt and still prevents loss.
     - **How it's built (my call; no API change).** The server delete (`deleteConversationApi`) is deferred.
     - `useConversations.deleteConversation` hides the chat locally and schedules the API call for when the toast expires (~5s). Undo cancels the call and restores the chat in place.
     - Pending deletes are sent on `pagehide` as a best effort.
     - If one is lost (the tab is killed), the chat reappears on the next load. That's the safe direction to fail.
     - The logic lives in the hook, so all three paths share it. Pure scheduling logic gets a check file.
   - An error boundary around the chat main area shows a plain "Something went wrong displaying this chat" message with a Reload button instead of a blank screen.
   - The source pane shows a skeleton (the page outline) while a PDF page loads, and a plain error with "Open in new tab" if it fails.

## Non-goals

- Auth pages, `/engineering` restyle, 404: project 3.
- Backend behaviour changes beyond the `SHOWCASE_QUESTIONS` list. No API or payload changes.
- Streaming chip interactivity (chips during streaming stay inert, as now). Fixing linkCitations inside URLs and code is a deferred minor from 6.0.
- New features: sharing, export, message editing, regenerate.

## Anti-goals

- **An AI-template look:**
  - the gradient-on-everything SaaS kit
  - identical rounded cards with soft grey shadows
  - all-caps eyebrows
  - an "AI assistant" avatar with sparkles
  - "Powered by …" lines
- **A three-column cramp on a laptop.** The PDF page must be readable at 1280px.
- **Motion that isn't answering an action.** The pane may slide in (≤ 200ms, none under `prefers-reduced-motion`). There is no Lenis, GSAP or scroll effects in the chat.
- **Losing a chat to one keystroke.**

## Constraints

- **Zero cost.** No paid services and no new dependencies. lucide-react, pdfjs-dist, react-markdown and react-hot-toast are already installed. No component library (approach C was rejected).
- **Tokens and fonts.** Use only the `--cf-*` tokens in `styles/tokens.css` (add a new `--cf-*` token there if one is truly needed). Fonts are JetBrains Mono and Inter, already loaded in `index.html`.
- **Test placement.** Tests go in the existing frontend check style (`*.check.mjs` run by the CI "Unit checks" line) for pure logic. The backend suite (395) must stay green after the `SHOWCASE_QUESTIONS` change.
- **Logic stays intact.** It's a visual rewrite. Conversation storage, streaming, upload, the `?q=` handoff, the anonymous 429 → sign-in link, and the refusal → upload card keep working unchanged.
- **Real-behaviour checks.** Each part is checked in a real browser before it's called done, at 1280×720 and 375×667, with the backend running.

## Approaches (user picked A)

- **A. New `chat-v2.css` on the `--cf` tokens; delete `chat.css` (2,381 lines) and `api.css` (picked).** Only `ChatPage` imports either file, and no other page uses their variables, so the rewrite touches nothing else. Components keep their logic and change class names, markup and copy where the goals need it. This is the same move 6.1 made with `landing-v2.css`.
- **B. Restyle `chat.css` in place.** It looks like a smaller diff, but it keeps the dead rules and old variables, and specificity fights come up for every component. Rejected.
- **C. Rebuild on a component library (e.g. Radix).** It gives the dialog and focus trap for free, but it's a new dependency for one pane and one sheet. Rejected (zero-dependency preference; 6.1 didn't need one).

## Decided design

### Layout

```
 desktop, source closed              desktop, source open (list folded)
┌──────┬───────────────────────┐    ┌──┬──────────────┬──────────────┐
│ list │   conversation        │    │≡ │ conversation │ TCS AR 23-24 │
│      │   (max ~760px, centred)│    │  │   [p.56]●    │ p.56  ‹ ›  − +│
│      │                       │    │  │              │  page canvas │
│      │ [ ask about a filing ]│    │  │ [ ask … ]    │  ▓ highlight │
└──────┴───────────────────────┘    └──┴──────────────┴──────────────┘
```

- **Chat list (sidebar).**
  - A smoked glass column using the landing `Wordmark` in place of the TrendingUp icon plus "Cognifin".
  - It keeps the New chat button, search, Today / Yesterday / Older groups, the right-click rename/delete menu, and the guest/user footer.
  - The collapsed state is a thin rail with the toggle and New chat.
- **Header.** Only the list toggle (when the list is collapsed). No model line, no status dot. If it's then empty on desktop, the builder may drop the header bar entirely.
- **Messages.**
  - User questions are right-aligned in a quiet raised block.
  - Answers render as full-width prose with no bubble, avatar or "Cognifin · Analyst" label. That's my call: it reads like an analyst's note rather than a chatbot. The timestamp may stay as muted text.
  - Markdown tables, headings and lists are styled for reading (mono figures in tables are allowed).
  - `FinancialChart` keeps its behaviour and gets restyled.
- **Citation chips.** A small mono "p.56" chip with a gold hairline and a gold-soft fill on hover, plus an active state while its page is open in the pane.
- **Sources row.** One entry per cited document, listing every cited page of it in page order, e.g. "Sources: TCS AR 2023-24 p.56, p.112". Only cited passages count (as now). My call: the pages are page chips that open the pane like the inline chips do, because a plain page number that doesn't open is a dead end. It should not use middle-dot meta strings.
- **Details toggle.** One text button. Expanded, it shows:
  - "Confidence 75%" and "10.7 s" as separate muted items (no middle-dot strings, no emoji)
  - "Cached" when cached
  - the question type when it isn't "lookup"
  - the passages list (label, snippet expand, and "Open page" which opens the pane, or a new tab for `fin_N`)
- **Input.** A smoked glass bar pinned at the bottom. It keeps the attach/upload flow and the PDF pill with clear, and gets restyled.
- **Welcome (empty chat).**
  - A short line in the site's voice, e.g. "Ask about any NIFTY 50 company's filings."
  - The four suggested questions as plain text buttons, not icon cards.
  - The shortcuts hint as plain text with `<kbd>`, Ctrl+N and Ctrl+B.
  - The input.
- **Upload overlay.** Same stages and progress, restyled as a glass card, no emoji.
- **Toasts.** The react-hot-toast style uses the `--cf` tokens. No emoji icons.

### Source pane

- **Component.** It replaces `PDFViewerModal` with `SourcePane`, reusing its pdf.js load, render, cancel and highlight code. `PDFViewerModal.jsx` is deleted.
- **Ownership.**
  - The open source is page-level state in `ChatPage` (`{ item, anchorId }`), so one pane serves every message.
  - Both `MessageList` chips and Details "Open page" call one `onOpenSource(item)` prop.
  - The pane and folding the chat list are coordinated there.
- **Pane header.** It shows:
  - the document label and page
  - prev/next, zoom
  - "Open in new tab"
  - Close
- **Builder calls already settled:**
  - Switching or starting a chat closes the pane.
  - Ctrl+B while the pane is open toggles the list, and that becomes the state restored on close.
  - `anchorId` is the id of the element that opened the pane, used to return focus to it.
  - The error boundary wraps the conversation and the pane.
- **Swapping pages.** Opening a different item while the pane is open swaps it in place: no close/reopen animation, and the PDF document is reused when the URL is the same.

### Files

- Create:
  - `styles/chat-v2.css`
  - `components/chat/SourcePane.jsx`
  - an error boundary (small class component, e.g. `components/chat/ChatErrorBoundary.jsx`)
- Delete:
  - `styles/chat.css`
  - `styles/api.css`
  - `components/chat/PDFViewerModal.jsx`
- Modify:
  - `pages/ChatPage.jsx`
  - `components/chat/MessageList.jsx`
  - `ChatHeader.jsx`
  - `Sidebar.jsx`
  - `ChatInput.jsx`
  - `LoadingIndicator.jsx`
  - `FinancialChart.jsx` (styles only)
  - `stageLabels.js`
  - `backend/main.py` (`SHOWCASE_QUESTIONS`)
- Pure helpers worth a check file, if extracted:
  - the sources-row dedupe
  - the Details summary formatting

### Delivery order

1. Tokens, layout shell and the source pane (incl. list fold and mobile sheet).
2. Messages with answer-first B (chips, Sources, Details, streaming line), removing the Pipeline panel.
3. Sidebar, input, welcome screen with the new questions (plus `SHOWCASE_QUESTIONS`), upload overlay, toasts.
4. Accessibility and polish: dialog and focus handling, banner fix, error boundary, pane skeleton and error, the undo toast, emoji sweep, deleting the old CSS.

## Left to the builder

- Exact spacing, the type scale within the 6.1 tokens, and the pane width between 40% and 50%.
- Whether the empty header bar is dropped.
- How the Details summary is laid out.
- The upload overlay's layout.
- The exact live stage wording, within plain words and no stack names.
