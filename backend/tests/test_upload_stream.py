"""/upload streams real ingestion progress."""

import os
import tempfile
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.test_security import PDF, _auth, _upload
from tests.test_chat_stream import events


class FakeCorpus:
    def __init__(self, fail=None, gate=None):
        self.fail = fail
        self.gate = gate  # threading.Event: hold ingestion after "chunking"
        self.pdf_path = None
        self.finished = False

    def add_document(self, pdf_path, progress=None, **_):
        self.pdf_path = pdf_path
        progress("chunking")
        if self.gate:
            self.gate.wait(5)
        if self.fail:
            raise self.fail
        progress("embedding", done=2, total=3)
        progress("indexing")
        self.finished = True
        return 3


@pytest.fixture
def ingest(monkeypatch):
    import main
    seen = {"discarded": [], "registered": []}

    def make(fail=None, gate=None):
        corpus = FakeCorpus(fail, gate)
        seen["corpus"] = corpus
        monkeypatch.setattr(main, "new_session_corpus", lambda _r: corpus)
        return corpus

    monkeypatch.setattr(main, "RetrieverPipeline", lambda: None)
    monkeypatch.setattr(main, "discard", lambda c: seen["discarded"].append(c))
    monkeypatch.setattr(main, "corpus_router", SimpleNamespace(
        register_session=lambda sid, c: seen["registered"].append(sid)))
    main.limiter.reset()
    return main, make, seen


def test_upload_streams_progress_then_final(ingest):
    main, make, seen = ingest
    make()
    r = _upload(TestClient(main.app), PDF, headers=_auth("alice"))
    assert r.status_code == 200
    evs = events(r.text)
    assert [d["name"] for t, d in evs if t == "stage"] == ["chunking", "embedding", "indexing"]
    assert evs[1][1] == {"name": "embedding", "done": 2, "total": 3}
    kind, final = evs[-1]
    assert kind == "final" and final["chunks"] == 3 and final["session_id"]
    assert seen["registered"] == [final["session_id"]] and seen["discarded"] == []
    assert not os.path.exists(os.path.dirname(seen["corpus"].pdf_path))


def test_upload_ingest_error_is_event(ingest):
    main, make, seen = ingest
    make(fail=ValueError("PDF appears to be empty"))
    evs = events(_upload(TestClient(main.app), PDF, headers=_auth("alice")).text)
    assert evs[-1] == ("error", {"detail": "Upload error: PDF appears to be empty", "status": 500})
    assert seen["discarded"] == [seen["corpus"]] and seen["registered"] == []
    assert not os.path.exists(os.path.dirname(seen["corpus"].pdf_path))


def test_upload_disconnect_discards_corpus(ingest):
    """Client leaves mid-ingest: the stream closes without waiting on the worker,
    and the worker discards the corpus and removes the temp dir itself."""
    import threading
    main, make, seen = ingest
    gate = threading.Event()
    corpus = make(gate=gate)
    tmp_dir = tempfile.mkdtemp(prefix="finsight_upload_")
    tmp_path = os.path.join(tmp_dir, "upload.pdf")
    open(tmp_path, "wb").write(PDF)
    q, abandoned, worker = main._start_ingest(corpus, tmp_dir, tmp_path, "ACME", "2024", "Annual_Report")
    g = main._ingest_stream(q, abandoned)
    next(g)    # "chunking", then the client goes away
    g.close()  # must not block on the (still gated) worker
    assert worker.is_alive()
    gate.set()
    worker.join(5)
    assert seen["discarded"] == [corpus] and seen["registered"] == []
    assert not os.path.exists(tmp_dir)
    assert not corpus.finished  # ingestion stopped at the next progress report


def test_embed_texts_progress_matches_total():
    from core.retriever_pipeline import RetrieverPipeline
    rp = RetrieverPipeline.__new__(RetrieverPipeline)
    rp.model = SimpleNamespace(encode=lambda texts, **kw: np.ones((len(texts), 4)))
    calls = []
    out = rp.embed_texts(["t"] * 600, progress=lambda d, t: calls.append((d, t)))
    assert calls == [(256, 600), (512, 600), (600, 600)]
    assert out.shape == (600, 4)


def test_embed_texts_without_progress_is_one_encode_call():
    from core.retriever_pipeline import RetrieverPipeline
    rp = RetrieverPipeline.__new__(RetrieverPipeline)
    sizes = []
    rp.model = SimpleNamespace(encode=lambda texts, **kw: sizes.append(len(texts)) or np.ones((len(texts), 4)))
    rp.embed_texts(["t"] * 600)
    assert sizes == [600]


def test_upload_failure_after_ingest_still_ends_the_stream(ingest):
    """A failure outside add_document (here: registering the session) must
    still put a terminal error on the queue, or the stream waits forever."""
    import queue
    main, make, seen = ingest
    corpus = make()

    def boom(sid, c):
        raise RuntimeError("router full")
    main.corpus_router.register_session = boom
    tmp_dir = tempfile.mkdtemp(prefix="finsight_upload_")
    tmp_path = os.path.join(tmp_dir, "upload.pdf")
    open(tmp_path, "wb").write(PDF)
    q, _, worker = main._start_ingest(corpus, tmp_dir, tmp_path, "ACME", "2024", "Annual_Report")
    items = []
    while True:
        kind, data = q.get(timeout=5)
        items.append((kind, data))
        if kind in ("final", "error"):
            break
    assert items[-1] == ("error", {"detail": "Upload error: router full", "status": 500})
    worker.join(5)
    assert seen["discarded"] == [corpus]
    assert not os.path.exists(tmp_dir)
