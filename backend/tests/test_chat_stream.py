"""/chat/stream and the answer_events generator behind /chat."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.test_security import _auth, app_ready, limited  # noqa: F401  (fixtures)

PAYLOAD = {"answer": "cached answer", "citations": [], "evidence": [],
           "metadata": {}, "follow_ups": []}


def events(text):
    out = []
    for frame in text.strip().split("\n\n"):
        lines = dict(ln.split(": ", 1) for ln in frame.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _llm(*deltas, error=None):
    def stream(system, user):
        yield from deltas
        if error:
            raise error
    return SimpleNamespace(is_configured=True, model="test", generate_stream=stream)


@pytest.fixture
def fresh_pipeline(app_ready, monkeypatch):
    main, saved = app_ready
    monkeypatch.setattr(main, "is_intelligent_parsing_enabled", lambda: False)
    monkeypatch.setattr(main, "retrieve_global", lambda *a, **k: (None, [], None))
    monkeypatch.setattr(main, "_prepare_figures", lambda q, p: None)
    monkeypatch.setattr(main, "llm_client", _llm("Rev ", "up.\n", "[FOLLOW_UP]: Why?"))
    main.limiter.reset()
    return main, TestClient(main.app)


def test_cache_hit_streams_only_final(app_ready):
    main, _ = app_ready
    main.response_cache.set("Risks?", PAYLOAD)
    evs = events(TestClient(main.app).post("/chat/stream", json={"question": "Risks?"}).text)
    assert [t for t, _ in evs] == ["final"]
    assert evs[0][1]["metadata"]["cached"] is True


def test_stream_tokens_then_final_matches_chat(fresh_pipeline):
    main, client = fresh_pipeline
    r = client.post("/chat/stream", json={"question": "Revenue?"})
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = events(r.text)
    types = [t for t, _ in evs]
    assert types[-1] == "final" and "token" in types
    assert "FOLLOW_UP" not in "".join(d["text"] for t, d in evs if t == "token")
    final = evs[-1][1]
    assert final["answer"] == "Rev up." and final["follow_ups"] == ["Why?"]

    main.response_cache.invalidate_all()
    assert client.post("/chat", json={"question": "Revenue?"}).json()["answer"] == final["answer"]


def test_stream_signed_in_final_carries_conversation_id(fresh_pipeline):
    main, client = fresh_pipeline
    evs = events(client.post("/chat/stream", json={"question": "Revenue?"},
                             headers=_auth("alice")).text)
    assert evs[-1][1]["conversation_id"] == "conv-alice"


def test_stream_llm_error_is_event_and_not_cached(fresh_pipeline, monkeypatch):
    main, client = fresh_pipeline
    monkeypatch.setattr(main, "llm_client", _llm("a", error=RuntimeError("boom")))
    evs = events(client.post("/chat/stream", json={"question": "Revenue?"}).text)
    assert evs[-1] == ("error", {"detail": "boom", "status": 502})
    assert main.response_cache.get("Revenue?", None) is None


def test_stream_closed_early_caches_nothing(fresh_pipeline):
    main, _ = fresh_pipeline
    g = main.answer_events("Revenue?")
    for kind, _ in g:
        if kind == "token":
            break
    g.close()
    assert main.response_cache.get("Revenue?", None) is None


def test_stream_503_when_llm_missing(app_ready, monkeypatch):
    main, _ = app_ready
    monkeypatch.setattr(main, "llm_client", SimpleNamespace(is_configured=False, model="t"))
    r = TestClient(main.app).post("/chat/stream", json={"question": "Revenue?"})
    assert r.status_code == 503 and "detail" in r.json()


def test_chat_and_stream_share_anonymous_quota(limited):
    client, _ = limited
    assert client.post("/chat", json={"question": "Revenue?"}).status_code == 200
    assert client.post("/chat/stream", json={"question": "Revenue?"}).status_code == 200
    r = client.post("/chat/stream", json={"question": "Revenue?"})
    assert r.status_code == 429
    assert "sign in" in r.json()["detail"].lower()


def _one_result(monkeypatch, main):
    hit = SimpleNamespace(chunk_id="chunk_7", snippet="revenue from operations 2,40,893 crore", score=1.0,
                          page_number=17, document_label="TCS AR 2024", pdf_url="")
    monkeypatch.setattr(main, "retrieve_global", lambda *a, **k: (None, [hit], None))
    monkeypatch.setattr(main, "llm_client", _llm("Revenue was ", "₹2,40,893 crore."))


def test_final_answer_gets_filled_citation(fresh_pipeline, monkeypatch):
    main, client = fresh_pipeline
    _one_result(monkeypatch, main)
    final = events(client.post("/chat/stream", json={"question": "TCS revenue FY24 fill?"}).text)[-1][1]
    assert final["answer"] == "Revenue was ₹2,40,893 crore [chunk_7]."
    assert final["metadata"]["citation_fill"] == ["chunk_7"]
    assert "chunk_7" in final["citations"]


def test_numbers_check_gets_prefill_answer(fresh_pipeline, monkeypatch):
    main, client = fresh_pipeline
    _one_result(monkeypatch, main)
    seen = []
    monkeypatch.setattr(main, "finish", lambda fin, answer: seen.append(answer) or {})
    client.post("/chat/stream", json={"question": "TCS revenue FY24 prefill?"})
    assert seen == ["Revenue was ₹2,40,893 crore."]
