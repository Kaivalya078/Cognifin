# Phase 4 part 2 — Streaming answers and real upload progress

Date: 2026-11-24 · Branch: `phase-4-sse` · Roadmap: Phase 4 item 4

## Intent

Today every "live" signal in the chat UI is fake:

- `answer_question` (`backend/main.py`) makes one blocking `llm_client.generate()` call;
  the frontend then replays the finished text word by word (`MessageList.jsx`,
  `WORD_INTERVAL_MS` typewriter).
- `LoadingIndicator.jsx` cycles canned messages on a 1.5 s timer.
- `/upload` blocks until chunk + embed are done while `ChatPage.jsx` walks a progress
  bar through five `UPLOAD_STAGES` on `setTimeout`s.

The user wants both made real: tokens appear as the model produces them, the pipeline
stages shown are the ones that actually ran, and upload progress reflects real work.
Both were declared necessary (2026-11-18). Why it matters: a demoable, honest product —
the fakes are a "demo tell", and `PipelinePanel`/`LatencyTracker` already exist to be fed
real events.

## Goals

1. `POST /chat/stream`: stage events as retrieval/reranking/etc. finish, token events as
   the LLM streams, one final event carrying everything `/chat` returns today.
2. `POST /upload` streams progress events: reading/chunking, embedding N of M chunks,
   done with `session_id`.
3. Frontend renders those events; the fake typewriter, `LoadingIndicator` message cycle
   and `UPLOAD_STAGES` timers are deleted.

## Non-goals

- No change to retrieval, prompts, router, citations or the number check logic.
- No resumable uploads or upload jobs (approach C, rejected). A dropped connection
  mid-upload means the user retries.
- No byte-level upload progress (`fetch` can't report it). Show "Uploading…" until the
  first server event.
- No WebSockets, no `EventSource`.

## Anti-goals (failure even if it "works")

- Two code paths for answering. `/chat`, the eval suite and `prewarm_showcase` must keep
  getting byte-identical payloads from the same pipeline the stream uses.
- Login token in a URL (that's why `EventSource` is out).
- `[FOLLOW_UP]: …` lines flashing in the answer bubble before vanishing.
- A partial / failed answer being cached or saved to the conversation.

## Constraints

- FastAPI sync code; the pipeline is synchronous (sentence-transformers, LanceDB,
  OpenAI SDK). `StreamingResponse` over a sync generator runs it in the threadpool — fine.
- Caddy `reverse_proxy` flushes `text/event-stream` immediately; no config change.
- slowapi limits (`_chat_limit`, upload `5/hour`) must still apply to the streaming
  endpoints, including the anonymous-trial 429. `/chat` and `/chat/stream` share **one**
  quota (my call; separate per-route counters would double the anonymous free trial):
  use slowapi `shared_limit` with one scope on both, and widen the 429 handler's
  `request.url.path == "/chat"` check to include `/chat/stream`.
- `EMBEDDING_BATCH_SIZE = 32` is fixed for float stability of the **global** index.
  sentence-transformers `encode` length-sorts its whole input before batching, so
  slicing for progress changes batch membership and can shift floats slightly. Accepted
  (my call): slicing happens **only** when a progress callback is passed, i.e. session
  uploads, which are temporary corpora where ~1e-6 drift is irrelevant. Ingestion,
  the global index and `tests/evaluation.py` keep calling `embed_texts` without a
  callback and are byte-identical to today.

## Approaches

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| **A** | POST + streamed response (SSE wire format), read with `fetch` + a ~30-line parser, for both chat and upload | One mechanism, least new code; upload lost if connection drops | **Picked by the user** |
| B | Browser `EventSource` | GET only, no `Authorization` header → token in URL/logs | Rejected |
| C | Stream chat; upload as a job + 1 s polling | Survives disconnects; needs job state, cleanup, a second pattern | Rejected — uploads finish well under a minute |

## Design

### Wire format

Standard SSE framing, `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`X-Accel-Buffering: no`. Each event: `event: <type>\ndata: <json>\n\n`.

Chat events:

| event | data | when |
|---|---|---|
| `stage` | `{"name": "retrieval", "ms": 412.3}` | each `tracker.track(...)` block finishes |
| `token` | `{"text": "..."}` | each streamed LLM delta (follow-up lines held back, below) |
| `final` | the full `/chat` `ChatResponse` JSON incl. `conversation_id` | after post-processing + persistence |
| `error` | `{"detail": "...", "status": 502}` | failure after the stream started |

Upload events:

| event | data |
|---|---|
| `stage` | `{"name": "chunking"}` then `{"name": "embedding", "done": 64, "total": 480}` (repeated), `{"name": "indexing"}` |
| `final` | the current `UploadResponse` JSON |
| `error` | `{"detail": "...", "status": 500}` |

### Backend: one pipeline, two consumers

- Refactor the body of `answer_question` into a generator
  `answer_events(question, session_id, top_k)` that yields `("stage", …)`,
  `("token", …)` and finally `("final", payload)`. All existing logic moves unchanged.
- `answer_question()` becomes: run `answer_events`, ignore everything but `final`,
  return the payload. `/chat`, eval and `prewarm_showcase` are untouched callers.
- Stage events: `LatencyTracker.track` gets an optional `on_done(stage, ms)` callback
  (or the generator yields right after each `with` block — builder's call). Generation
  is **not** added to the tracker or as a stage event (my call): the payload and
  `latency_breakdown` stay exactly as today, and `PipelinePanel` keeps computing
  generation as total minus tracked stages. Tokens arriving already show generation live.
- `OpenAIClient.generate_stream(system, user)` yields text deltas (`stream=True`), same
  model/temperature/max_tokens and the same error mapping as `generate()`.
  `answer_events` joins the deltas into `raw_answer` and the rest
  (`extract_follow_ups`, citations, confidence, `finish(fin, answer)`) runs exactly as now.
- **Cache hit:** `answer_events` yields only `final` (no stages, no tokens); the frontend
  shows it at once. `metadata.cached = True` as today.
- **Follow-up hold-back** (my call): tokens are emitted line-buffered at line starts —
  text is emitted immediately unless the current line so far is a prefix of
  `[FOLLOW_UP]`; such a line is held until newline/end and dropped if it matches.
  The `final` event's `answer` (cleaned by `extract_follow_ups`) is authoritative; the
  frontend replaces the streamed text with it.
- Cache write and persistence happen only after the LLM stream completes, so a failure
  or client disconnect mid-stream caches/saves nothing.

### Backend: endpoints

- `POST /chat/stream` (new, my call; `/chat` stays for eval/tests). Same `ChatRequest`,
  auth dependency and limiter as `/chat`. Pre-stream checks (corpus not indexed, LLM not
  configured, rate limit) return the normal HTTP status + JSON, not a stream (my call —
  the frontend's existing 429/503 handling keeps working). Pipeline exceptions after the
  stream starts become an `error` event with the status `/chat` would have used
  (KeyError 404, ValueError 503, RuntimeError 502, other 500), then the stream closes.
  `persist_exchange` runs inside the stream before `final`, so `final` carries
  `conversation_id`.
- `POST /upload` (changed in place, my call — the frontend is its only client; tests
  updated). The PDF magic-byte check (415) and size cap (413) stay **before** the stream
  starts, as HTTP errors. Chunking, embedding and indexing run inside the stream.
  `CorpusManager.add_document` gets an optional `progress(name, **info)` callback;
  `RetrieverPipeline.embed_texts` encodes in slices of 256 and reports
  after each slice when a callback is given. Temp-dir cleanup and `discard(session_corpus)`
  on failure must still run when the generator finishes or the client disconnects
  (`try/finally` inside the generator).

### Frontend

- `api.js`: one helper `streamPost(url, body|formData, onEvent)` — `fetch`, check
  `response.ok` (non-OK → throw with `status` and `detail`, same as today, incl. 401 →
  `handle401`), then read `response.body` with a `TextDecoder`, split on blank lines,
  parse `event:`/`data:`, call `onEvent(type, data)`; an `error` event throws. Keep the
  existing 120 s / 300 s abort timeouts.
- `askQuestionStream(question, sessionId, conversationId, onEvent)` and
  `uploadPdf(file, companyName, year, onEvent)` built on it. `askQuestion` stays
  (unused by the UI, harmless; builder may delete if nothing imports it).
- `ChatPage.handleSend`: add an empty assistant message on the first `stage`/`token`;
  append tokens to it; on `final`, replace content with `final.answer` and attach
  citations/evidence/pipeline/follow_ups exactly as today; on error, same error message
  and toast as today.
- Loading state: before the first token, show the stages received so far (e.g.
  "Retrieval ✓ 412 ms · Reranking…") in place of `LoadingIndicator`'s canned cycle.
  Delete the canned message list.
- `MessageList`: delete the typewriter (`WORD_INTERVAL_MS`, `displayedCount`); render
  `message.content` directly; keep auto-scroll while the latest message grows.
- Upload overlay: driven by events. Stages shown: Uploading → Reading & chunking →
  Embedding (bar = done/total) → Indexing → Ready. Delete `UPLOAD_STAGES` percentages
  and `stageTimer`.

### Tests

- Backend: `answer_events` on a cache hit yields only `final`; a fake streaming LLM
  yields tokens and the final payload equals `answer_question`'s; follow-up lines never
  appear in `token` events; an LLM error mid-stream yields `error` and caches nothing;
  `/chat/stream` returns 503/429 as HTTP before streaming; `/upload` still returns
  415/413 as HTTP and streams `embedding` progress then `final` (existing
  `test_security.py` upload tests adapted).
- Frontend: no test framework exists; verify by running the app (chat, cached showcase
  question, upload, error case).

## Left to the builder

- Exact event-yield mechanism for stages (callback vs. yielding after each block).
- Embedding slice size (256 suggested; only affects upload progress granularity).
- Exact copy/layout of the stage line and upload overlay (Phase 6 restyles anyway).
- Whether to delete the now-unused `askQuestion`.
