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
    def __init__(self, fail=None):
        self.fail = fail
        self.pdf_path = None

    def add_document(self, pdf_path, progress=None, **_):
        self.pdf_path = pdf_path
        progress("chunking")
        if self.fail:
            raise self.fail
        progress("embedding", done=2, total=3)
        progress("indexing")
        return 3


@pytest.fixture
def ingest(monkeypatch):
    import main
    seen = {"discarded": [], "registered": []}

    def make(fail=None):
        corpus = FakeCorpus(fail)
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
    main, make, seen = ingest
    corpus = make()
    tmp_dir = tempfile.mkdtemp(prefix="finsight_upload_")
    tmp_path = os.path.join(tmp_dir, "upload.pdf")
    open(tmp_path, "wb").write(PDF)
    g = main._ingest_events(corpus, tmp_dir, tmp_path, "ACME", "2024", "Annual_Report")
    next(g)  # first progress event, then the client goes away
    g.close()
    assert seen["discarded"] == [corpus] and seen["registered"] == []
    assert not os.path.exists(tmp_dir)


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
