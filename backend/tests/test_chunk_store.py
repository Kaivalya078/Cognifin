import numpy as np
import pytest

from core.chunk_store import ChunkStore
from core.metadata_schema import create_default_metadata
from core.retriever_pipeline import Chunk

DIM = 4


def _doc(company, year, texts, start, page=1):
    chunks = [Chunk(chunk_id=f"chunk_{start + i}", text=t, start_char=0, end_char=len(t),
                    page_number=page + i) for i, t in enumerate(texts)]
    metas = []
    for i in range(len(texts)):
        m = create_default_metadata(vector_id=start + i, display_chunk_id=f"chunk_{i}",
                                    company=company, document_type="Annual_Report", year=year)
        m.document_label = f"{company}_Annual_Report_{year}_v1"
        m.page_number = page + i
        metas.append(m)
    return chunks, metas


def _vecs(n, seed):
    v = np.random.default_rng(seed).normal(size=(n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture
def store(tmp_path):
    s = ChunkStore(str(tmp_path / "db"), DIM)
    c, m = _doc("TCS", "2024", ["TCS revenue grew", "TCS CASA ratio", "TCS margins"], 0)
    s.add(c, m, _vecs(3, 1))
    c, m = _doc("INFY", "2024", ["Infosys revenue grew", "Infosys attrition", "Infosys deals"], 3)
    s.add(c, m, _vecs(3, 2))
    s.build_text_index()
    return s


def test_add_and_count(store):
    assert store.count() == 6


def test_dense_prefilter_only_returns_scope(store):
    hits = store.search_dense(_vecs(1, 9)[0], k=50, where="company = 'TCS'")
    assert len(hits) == 3 and {row["company"] for _, row in hits} == {"TCS"}
    scores = [s for s, _ in hits]
    assert scores == sorted(scores, reverse=True) and all(-1.0 <= s <= 1.0 for s in scores)


def test_dense_score_is_cosine(store):
    v = store.get(4)["vector"]
    score, row = store.search_dense(np.asarray(v, dtype=np.float32), k=1, where=None)[0]
    assert row["vector_id"] == 4 and abs(score - 1.0) < 1e-5


def test_text_search_finds_exact_term(store):
    hits = store.search_text("CASA", k=10, where=None)
    assert [row["vector_id"] for _, row in hits] == [1]


def test_text_search_respects_where(store):
    hits = store.search_text("revenue", k=10, where="company = 'INFY'")
    assert [row["company"] for _, row in hits] == ["INFY"]


def test_neighbors_stay_in_document(store):
    rows = store.neighbors("TCS_Annual_Report_2024_v1", chunk_seq=2, window=1)
    assert [r["vector_id"] for r in rows] == [1, 2]   # seq 3 would be INFY's first chunk


def test_reopen_persists(store, tmp_path):
    again = ChunkStore(str(tmp_path / "db"), DIM)
    assert again.count() == 6 and again.get(5)["text"] == "Infosys deals"


# =============================================================================
# scope_to_where
# =============================================================================

from core.chunk_store import scope_to_where
from core.lookup_index import RetrievalScope


def test_where_quotes_special_symbols(tmp_path):
    s = ChunkStore(str(tmp_path / "db"), DIM)
    start = 0
    for co in ["M&M", "BAJAJ-AUTO", "O'Brien_upload", "TCS"]:
        c, m = _doc(co, "2024", [f"{co} a", f"{co} b"], start)
        s.add(c, m, _vecs(2, start))
        start += 2
    for co in ["M&M", "BAJAJ-AUTO", "O'Brien_upload"]:
        where = scope_to_where(RetrievalScope(label="t", companies=[co], years=["2024"]))
        hits = s.search_dense(_vecs(1, 99)[0], k=20, where=where)
        assert {row["company"] for _, row in hits} == {co} and len(hits) == 2


def test_where_empty_scope_is_active_only():
    assert scope_to_where(RetrievalScope(label="all")) == "is_active = true"


def test_where_multi_company_multi_year():
    w = scope_to_where(RetrievalScope(label="c", companies=["TCS", "INFY"], years=["2023", "2024"]))
    assert w == "is_active = true AND company IN ('TCS', 'INFY') AND year IN ('2023', '2024')"


# =============================================================================
# CorpusManager on ChunkStore
# =============================================================================

from tests.pdf_fixtures import make_pdf

SENT = " ".join(f"Sentence {i} reports steady revenue growth." for i in range(40))


def _report(tmp_path, name):
    return make_pdf(tmp_path / name, [
        [("heading", "Directors Report"), ("para", SENT)],
        [("heading", "Segment Revenue"), ("table", [["Particulars", "FY24", "FY23"],
                                                    ["Revenue", "231456", "198234"],
                                                    ["Other income", "5432", "4321"]])],
    ])


@pytest.fixture
def corpus(tmp_path):
    from core.corpus_manager import CorpusManager
    from core.retriever_pipeline import RetrieverPipeline
    p = RetrieverPipeline()
    cm = CorpusManager(p, ChunkStore(str(tmp_path / "db"), p.embedding_dim))
    cm.add_document(_report(tmp_path, "a.pdf"), company="TCS", document_type="Annual_Report", year="2024")
    cm.add_document(_report(tmp_path, "b.pdf"), company="INFY", document_type="Annual_Report", year="2024")
    return cm


def test_corpus_search_is_scoped_and_carries_pages(corpus):
    vec = corpus.retriever.embed_query("segment revenue table")
    res = corpus.search(RetrievalScope(label="t", companies=["INFY"], years=["2024"]), vec)
    assert res and {r.document_label for r in res} == {"INFY_Annual_Report_2024_v1"}
    assert {r.page_number for r in res} <= {1, 2} and 2 in {r.page_number for r in res}
    assert all(r.chunk_id.startswith("chunk_") for r in res)


def test_registry_round_trip_and_fingerprint_guard(corpus, tmp_path, monkeypatch):
    from core.corpus_manager import CorpusManager
    corpus.save_registry(str(tmp_path / "cache"))
    again = CorpusManager(corpus.retriever, corpus.store)
    assert again.load_registry(str(tmp_path / "cache"))
    assert again.num_chunks == corpus.store.count() and again.is_indexed
    monkeypatch.setattr("core.retriever_pipeline.RetrieverPipeline.compute_config_fingerprint",
                        staticmethod(lambda: "different-model"))
    assert CorpusManager(corpus.retriever, corpus.store).load_registry(str(tmp_path / "cache")) is False


def test_enrich_uses_chunk_seq_and_expanded_ids(corpus):
    from core.metadata_schema import RetrievalResult
    from core.result_refiner import enrich_context
    first_infy = corpus.documents["INFY_Annual_Report_2024_v1"].vector_id_start
    hit = RetrievalResult(chunk_id=f"[expanded]chunk_{first_infy}", score=1.0, snippet="x",
                          document_label="INFY_Annual_Report_2024_v1")
    out = enrich_context([hit], corpus, window=1)[0]
    tcs_last = corpus.store.get(first_infy - 1)["text"]
    assert out.chunk_id.startswith("[expanded]") and tcs_last not in out.snippet  # never crosses documents
    assert corpus.store.get(first_infy + 1)["text"][:40] in out.snippet


def test_enrich_skips_results_from_other_corpora(corpus):
    from core.metadata_schema import RetrievalResult
    from core.result_refiner import enrich_context
    foreign = RetrievalResult(chunk_id="chunk_0", score=1.0, snippet="session text",
                              document_label="UPLOAD_Annual_Report_2024_v1")
    assert enrich_context([foreign], corpus, window=1)[0] == foreign


def test_keyword_search_respects_scope(corpus):
    corpus.store.build_text_index()
    hits = corpus.search_text([RetrievalScope(label="t", companies=["TCS"])], "231456", k=10)
    assert hits and {r.document_label for r in hits} == {"TCS_Annual_Report_2024_v1"}
    assert all(r.page_number == 2 for r in hits)


def test_orchestrator_keyword_hits_respect_scope(corpus, monkeypatch):
    from query.query_orchestrator import retrieve_context
    corpus.store.build_text_index()
    monkeypatch.setattr(corpus, "search", lambda scope, vec: [])   # keyword results only
    merged, parsed = retrieve_context("INFY revenue 231456 in 2024", corpus_manager=corpus,
                                      embed_query=corpus.retriever.embed_query)
    assert parsed.companies == ["INFY"]
    assert merged and {r.document_label for r in merged} == {"INFY_Annual_Report_2024_v1"}
