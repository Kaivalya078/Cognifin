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
