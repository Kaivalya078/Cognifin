# Streaming Answers and Real Upload Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream chat answers (stages → tokens → final) and real upload progress over POST + SSE-format responses, and delete every fake progress effect in the UI.

**Architecture:** `answer_question`'s body becomes a generator `answer_events`; `/chat`, eval and pre-warm consume only its `final`, `/chat/stream` forwards every event. `/upload` runs ingestion in a worker thread that reports progress through a queue, which the response generator drains. The frontend reads both with one `fetch`-based SSE parser.

**Tech Stack:** FastAPI `StreamingResponse`, OpenAI SDK `stream=True`, slowapi `shared_limit`, React 18 + `fetch` `ReadableStream`.

**Spec:** `docs/superpowers/specs/2026-11-24-sse-streaming-design.md`

## Global Constraints

- Response headers on both streams: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Frame format: `event: <type>\ndata: <json>\n\n`. Event types: `stage`, `token`, `final`, `error`.
- `/chat` payloads, `/chat` tests, `tests/evaluation.py` and `prewarm_showcase` must keep producing identical payloads; `latency_breakdown` gains no new keys (no `generation` stage).
- `/chat` and `/chat/stream` share one rate-limit quota (`_chat_limit`, one scope); the anonymous "Sign in to keep asking" 429 applies to both paths.
- Pre-stream failures stay HTTP errors with JSON `detail`: 503 (no corpus / no LLM key), 429, 401, 415, 413.
- Mid-stream failures → one `error` event `{"detail", "status"}` using `/chat`'s mapping: KeyError 404, ValueError 503, RuntimeError 502, other 500.
- Nothing is cached or persisted unless the LLM stream completed.
- `[FOLLOW_UP]` lines never appear in `token` events.
- `embed_texts` without a callback must behave exactly as today; slicing (256 texts) only when a callback is passed.
- Run backend tests from `backend/`: `venv/Scripts/python.exe -m pytest tests -q`. Baseline: 325 passing.

## Review Focus

1. Client closes the tab mid-answer → generator is closed; nothing cached or saved. (Task 2 test `test_stream_closed_early_caches_nothing`.)
2. Client closes the tab mid-upload → worker finishes, session corpus is discarded, temp dir removed, nothing registered. (Task 3 test `test_upload_disconnect_discards_corpus`.)
3. LLM delta boundaries split `[FOLLOW_UP]` across chunks (`"[FOL"`, `"LOW_UP]: x"`) → still held back. (Task 1 test `test_hold_follow_ups_split_across_deltas`.)
4. A line that merely starts with `[` but isn't a follow-up (`"[fin_1] revenue…"`) → emitted, not swallowed. (Task 1 test `test_hold_follow_ups_releases_other_brackets`.)
5. Image-only / empty PDF (`ValueError` from `prepare_document`) after the stream started → `error` event with status 500 and the message, and the overlay shows it. (Task 3 test `test_upload_ingest_error_is_event`.)

---

### Task 1: Streaming primitives (LLM deltas, follow-up hold-back, SSE framing)

**Files:**
- Create: `backend/generation/streaming.py`
- Modify: `backend/generation/openai_client.py` (add `generate_stream` next to `generate`)
- Test: `backend/tests/test_streaming.py`

**Interfaces:**
- Produces:
  - `sse(event: str, data: dict) -> str` — one frame, `json.dumps(data, ensure_ascii=False)`.
  - `hold_follow_ups(deltas: Iterable[str]) -> Iterator[str]` — passes text through, buffering only while the current line (text since the last `\n`) is a prefix of `[FOLLOW_UP]` or starts with `[FOLLOW_UP]`; such a line is dropped when it completes or the stream ends. Leading newlines before a dropped line may pass through (the `final` answer is authoritative).
  - `OpenAIClient.generate_stream(system_prompt: str, user_message: str) -> Iterator[str]` — same model, `temperature=0`, `max_tokens=1000`, `stream=True`; yields non-empty `choices[0].delta.content`; same guard (`ValueError` when unconfigured) and same exception → `RuntimeError` mapping as `generate`, also for errors raised while iterating.

- [ ] **Step 1: Write the failing tests**

```python
from generation.streaming import sse, hold_follow_ups

def test_sse_frame():
    assert sse("token", {"text": "hi ₹"}) == 'event: token\ndata: {"text": "hi ₹"}\n\n'

def test_hold_follow_ups_drops_follow_up_lines():
    out = "".join(hold_follow_ups(["Revenue rose.\n", "[FOLLOW_UP]: Why?\n", "[FOLLOW_UP]: And?"]))
    assert "FOLLOW_UP" not in out and out.startswith("Revenue rose.")

def test_hold_follow_ups_split_across_deltas():
    out = "".join(hold_follow_ups(["A\n[FOL", "LOW_UP]: x", "\n[FOLLOW", "_UP]: y"]))
    assert "FOLLOW" not in out and "x" not in out and "y" not in out and out.startswith("A")

def test_hold_follow_ups_releases_other_brackets():
    out = "".join(hold_follow_ups(["[fin", "_1] revenue 10\n", "[F", "Y26] ok"]))
    assert out == "[fin_1] revenue 10\n[FY26] ok"

def test_hold_follow_ups_streams_plain_text_unbuffered():
    assert list(hold_follow_ups(["ab", "cd"])) == ["ab", "cd"]
```

Plus `test_generate_stream_maps_errors`: a fake `client.chat.completions.create` returning an iterator that raises `openai.RateLimitError` mid-way → `RuntimeError` containing "rate limit"; build `OpenAIClient.__new__(OpenAIClient)` and set `is_configured=True`, `model`, `client` by hand.

- [ ] **Step 2: Run** `python -m pytest tests/test_streaming.py -q` — Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `streaming.py` and `generate_stream`.
- [ ] **Step 4: Run** `python -m pytest tests/test_streaming.py -q` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(stream): SSE framing, follow-up hold-back, LLM delta stream`

---

### Task 2: `answer_events` generator and `POST /chat/stream`

**Files:**
- Modify: `backend/main.py` (`answer_question` → `answer_events` + thin wrapper; `/chat` error mapping helper; new `/chat/stream`; limiter + 429 handler)
- Test: `backend/tests/test_chat_stream.py` (reuse `app_ready` / `_auth` by importing from `tests.test_security`, or move them to `tests/conftest.py` — implementer's call)

**Interfaces:**
- Consumes: `sse`, `hold_follow_ups`, `OpenAIClient.generate_stream` (Task 1).
- Produces:
  - `answer_events(question: str, session_id: Optional[str] = None, top_k: Optional[int] = None) -> Iterator[tuple[str, dict]]` — yields `("stage", {"name", "ms"})` after each `tracker.track(...)` block (ms from `tracker.get_breakdown()[name]`), `("token", {"text"})` per held-back delta, then `("final", payload)`. On cache hit: only `("final", cached_payload_with_cached_True)`. Cache write (`response_cache.set`) happens just before yielding `final`. Body is today's `answer_question` logic otherwise unchanged; `raw_answer = "".join(all raw deltas)` (raw, i.e. before hold-back, so `extract_follow_ups` still sees follow-ups).
  - `answer_question(...) -> dict` — drains `answer_events`, returns the `final` payload. Signature unchanged.
  - `_error_status(e: Exception) -> int` — KeyError 404, ValueError 503, RuntimeError 502, else 500; `/chat` uses it too.
  - `POST /chat/stream` — body `ChatRequest`, `get_optional_user`, same two 503 pre-checks as `/chat`; returns `StreamingResponse(gen, media_type="text/event-stream", headers=...)`. Generator: forwards `stage`/`token` as `sse(...)`; on `final` calls `persist_exchange` if signed in, adds `conversation_id`, emits `sse("final", ChatResponse(**payload, conversation_id=...).model_dump())`; on exception emits `sse("error", {"detail": str(e), "status": _error_status(e)})`.
  - Limiter: both `/chat` and `/chat/stream` decorated with `@limiter.shared_limit(_chat_limit, scope="chat")`; 429 handler condition becomes `request.url.path in ("/chat", "/chat/stream")`.

- [ ] **Step 1: Write the failing tests.** Fixture `fresh_pipeline(app_ready, monkeypatch)`: `is_intelligent_parsing_enabled → False`, `retrieve_global → (None, [], None)`, `_prepare_figures → None`, `llm_client = SimpleNamespace(is_configured=True, model="test", generate_stream=lambda s, u: iter(["Rev ", "up.\n", "[FOLLOW_UP]: Why?"]))`. Helper `events(text) -> list[tuple[str, dict]]` parses frames.

```python
def test_cache_hit_streams_only_final(app_ready): ...
    # response_cache.set(q, payload) ; POST /chat/stream
    # assert [t for t, _ in evs] == ["final"] and evs[0][1]["metadata"]["cached"] is True

def test_stream_tokens_then_final_matches_chat(fresh_pipeline):
    # evs = stream("Revenue?") ; types end with "final", contain "token"
    # "".join(token texts) has no "FOLLOW_UP"
    # final["answer"] == "Rev up." and final["follow_ups"] == ["Why?"]
    # invalidate cache, POST /chat same question -> json()["answer"] == final["answer"]

def test_stream_llm_error_is_event_and_not_cached(fresh_pipeline, monkeypatch):
    # generate_stream yields "a" then raises RuntimeError("boom")
    # last event == ("error", {"detail": "boom", "status": 502}); response_cache.get(q) is None

def test_stream_closed_early_caches_nothing(fresh_pipeline):
    # g = main.answer_events("Revenue?"); next(g) until first "token"; g.close()
    # response_cache.get("Revenue?") is None

def test_stream_503_when_llm_missing(app_ready, monkeypatch):
    # llm_client.is_configured False -> POST /chat/stream status 503, JSON detail

def test_chat_and_stream_share_anonymous_quota(limited):
    # 1 x /chat + 1 x /chat/stream -> 200, 200 ; next /chat/stream -> 429 with "sign in"
```

- [ ] **Step 2: Run** `python -m pytest tests/test_chat_stream.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** the Interfaces above in `main.py`.
- [ ] **Step 4: Run** `python -m pytest tests -q` — Expected: all pass (325 + new), including the unchanged `/chat` tests in `test_security.py`.
- [ ] **Step 5: Commit** `feat(chat): stream stages and tokens from one answer pipeline`

---

### Task 3: Streaming `/upload` with real progress

**Files:**
- Modify: `backend/core/retriever_pipeline.py` (`embed_texts`), `backend/core/corpus_manager.py` (`add_document`), `backend/main.py` (`upload_document`)
- Test: `backend/tests/test_security.py` (adapt upload tests), `backend/tests/test_upload_stream.py`

**Interfaces:**
- Consumes: `sse` (Task 1).
- Produces:
  - `RetrieverPipeline.embed_texts(texts, instruction=None, progress: Optional[Callable[[int, int], None]] = None)` — `progress is None` → today's single `encode` call, untouched. Otherwise encode in slices of 256, call `progress(done, total)` after each slice, concatenate, then normalise as today.
  - `CorpusManager.add_document(..., progress: Optional[Callable[..., None]] = None)` — calls `progress("chunking")` before `prepare_document`, passes `lambda d, t: progress("embedding", done=d, total=t)` to `embed_texts`, `progress("indexing")` before `store.add`. No-op when `None`.
  - `/upload`: auth, magic-byte 415 and size 413 checks and the temp-file write stay before the response (HTTP errors). Then `StreamingResponse` over a generator that starts a `threading.Thread` running `session_corpus.add_document(..., progress=...)`, where `progress` puts `("stage", {"name": n, **info})` on a `queue.Queue`; the worker puts `("done", num_chunks)` or `("error", exc)` last. The generator yields `sse("stage", ...)` per item; on done it registers the session and yields `sse("final", UploadResponse(...).model_dump())`; on error it discards the corpus and yields `sse("error", {"detail": f"Upload error: {e}", "status": 500})` (500 for every ingest failure, as `/upload` returns today). Its `finally`: `thread.join()`; if not registered → `discard(session_corpus)`; `shutil.rmtree(tmp_dir)`. Note: the temp dir must now be removed in the generator's `finally`, not the endpoint's (the endpoint returns before ingestion runs); the endpoint's own `except`/`finally` still cleans up when it fails before returning.
  - Rate limit `5/hour` unchanged.

- [ ] **Step 1: Write the failing tests.** Extend `upload_ready`'s `FakeCorpus.add_document(self, pdf_path, progress=None, **_)` to call `progress("chunking")`, `progress("embedding", done=2, total=3)`, `progress("indexing")` before returning 3; record `discard` calls via `monkeypatch.setattr(main, "discard", ...)`.

```python
def test_upload_streams_progress_then_final(upload_ready):
    # r = _upload(client, PDF, headers=_auth("alice")); r.status_code == 200
    # [d["name"] for t, d in evs if t == "stage"] == ["chunking", "embedding", "indexing"]
    # evs[-1][0] == "final" and evs[-1][1]["chunks"] == 3 and evs[-1][1]["session_id"]

def test_upload_ingest_error_is_event(upload_ready, monkeypatch):
    # FakeCorpus.add_document raises ValueError("PDF appears to be empty")
    # evs[-1] == ("error", {"detail": "Upload error: PDF appears to be empty", "status": 500})
    # discard called once; temp dir from seen["pdf_path"] no longer exists

def test_upload_disconnect_discards_corpus(upload_ready):
    # drive the endpoint generator directly or via client.stream(...) and close after first event
    # discard called; register_session not called; temp dir gone

def test_embed_texts_progress_matches_total():
    # RetrieverPipeline with a fake model whose encode returns np.ones((len(texts), 4))
    # 600 texts, progress records -> [(256, 600), (512, 600), (600, 600)]; result shape (600, 4)
```

Adapt `test_upload_ignores_client_filename_path`: status 200 still holds; read the body so the generator runs. 401/415/413 tests stay as they are.

- [ ] **Step 2: Run** `python -m pytest tests/test_upload_stream.py tests/test_security.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** the Interfaces above.
- [ ] **Step 4: Run** `python -m pytest tests -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(upload): stream real chunking/embedding progress`

---

### Task 4: Frontend — SSE client and streamed chat

**Files:**
- Modify: `frontend/src/api.js`, `frontend/src/pages/ChatPage.jsx`, `frontend/src/components/chat/MessageList.jsx`, `frontend/src/components/chat/LoadingIndicator.jsx`

**Interfaces:**
- Consumes: `/chat/stream` events (Task 2).
- Produces:
  - `streamPost(path: string, body: object | FormData, onEvent: (type, data) => void, timeoutMs: number): Promise<object>` in `api.js` — auth header as today (no `Content-Type` for `FormData`); non-OK → `handle401`, throw `Error(detail)` with `.status`, same as `askQuestion`; reads `response.body` with `TextDecoder`, splits frames on `\n\n`, parses `event:`/`data:` lines, calls `onEvent`; an `error` event throws `Error(detail)` with `.status`; resolves with the `final` data; stream ending without `final` throws `Error("Connection lost")`.
  - `askQuestionStream(question, sessionId, conversationId, onEvent)` → `streamPost("/chat/stream", …, 120000)`.
- Behaviour:
  - `ChatPage` keeps a `streaming` state `{ stages: [{name, ms}], text: "" }` (null when idle), set on send, updated from `stage` / `token` events, cleared in `finally`. On `final`: the existing `setConversationId` + `addMessage(…, data.answer, {citations, evidence, pipeline: data.metadata, follow_ups})` code, unchanged. Errors: existing message + toast, unchanged.
  - `MessageList` gets a `streaming` prop instead of `lastQuery`. While `streaming` is set: if `text` is empty, `LoadingIndicator` shows the received stages (e.g. `Retrieval ✓ 412 ms · Reranking ✓ 88 ms`, or "Searching filings…" before the first stage); once text arrives, render a live assistant bubble with the markdown renderer the normal bubble uses. Auto-scroll while it grows.
  - Delete: `WORD_INTERVAL_MS`, the typewriter state/effect (`displayedCount`, `isStreaming` derived from it), `LoadingIndicator`'s `buildMessages`/`DEFAULT_MESSAGES` cycle and its interval. Bubbles render `message.content` directly.
  - `askQuestion` stays exported only if something still imports it; otherwise delete it.

- [ ] **Step 1: Implement** the above.
- [ ] **Step 2: Build** `cd frontend && npm run build` — Expected: succeeds, no new warnings from these files; `npm run lint` if the script exists — no new errors.
- [ ] **Step 3: Verify in the running app** (backend `uvicorn main:app --port 8000`, frontend `npm run dev`; use the `run` skill or Playwright): ask a fresh question → stage line appears, then text grows, then citations/follow-ups/chart attach and no `[FOLLOW_UP]` text ever showed; click a showcase question → answer appears at once; stop the backend mid-answer → error message + toast. Screenshot the streaming state.
- [ ] **Step 4: Commit** `feat(chat-ui): render streamed stages and tokens; drop typewriter`

---

### Task 5: Frontend — upload overlay from real events

**Files:**
- Modify: `frontend/src/api.js` (`uploadPdf`), `frontend/src/pages/ChatPage.jsx` (`handleUpload`, `UploadProgressOverlay`)

**Interfaces:**
- Consumes: `streamPost` (Task 4), `/upload` events (Task 3).
- Produces:
  - `uploadPdf(file, companyName, year, onEvent)` → `streamPost("/upload", formData, onEvent, 300000)`; resolves with `UploadResponse`.
  - Overlay stages, in order: `Uploading`, `Reading & chunking` (`chunking`), `Embedding` (`embedding`, bar = `done/total`, label `Embedding 64 / 480`), `Indexing` (`indexing`), `Ready` (final). Percent: Uploading 0 (indeterminate), chunking 10, embedding `10 + 80*done/total`, indexing 95, final 100.
  - Delete `UPLOAD_STAGES` percentages, `stageTimer`, `advanceStage` and the `delays` array. Done/error/auto-close behaviour and the confirmation message stay as today.

- [ ] **Step 1: Implement** the above.
- [ ] **Step 2: Build** `npm run build` — Expected: succeeds.
- [ ] **Step 3: Verify in the running app:** upload a real annual report from `backend/data/<SYM>/2026.pdf` → stages advance with a moving embedding count, overlay closes, a question about the PDF is answered from it; upload a renamed `.txt` → 415 message in the overlay; upload an image-only PDF (e.g. the SBIN 2025-03 results PDF) → error shown, not a hang.
- [ ] **Step 4: Commit** `feat(upload-ui): real progress from the upload stream`

---

### Task 6: Whole-branch check

- [ ] **Step 1:** `python -m pytest tests -q` from `backend/` — all pass; report the count.
- [ ] **Step 2:** from `backend/`: `venv/Scripts/python.exe tests/eval_router.py` (no LLM) — same numbers as the 2026-11-18 table in `tests/eval_reports/README.md`. Then, with the server running, `venv/Scripts/python.exe tests/eval_router.py --e2e` — same pass count, proving `/chat` payloads didn't change.
- [ ] **Step 3:** Update `ROADMAP.md` Phase 4 item 4 as done; commit `docs: mark Phase 4 streaming done`.
