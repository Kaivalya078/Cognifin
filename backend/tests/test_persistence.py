"""
Checks on the real on-disk index (backend/index_cache). Skipped when no
LanceDB index has been built; run after batch_ingest_annual_reports.py.
"""

import glob
import json
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402

CACHE_DIR = BACKEND / settings.INDEX_CACHE_DIR
pytestmark = pytest.mark.skipif(not (CACHE_DIR / "lancedb").is_dir(),
                                reason="no LanceDB index built in index_cache/")


@pytest.fixture(scope="module")
def corpus():
    from core.app_retrieval import open_global_corpus
    cm = open_global_corpus(str(CACHE_DIR))
    assert cm.load_registry(str(CACHE_DIR)), "registry missing, stale or inconsistent with the store"
    return cm


def test_registry_is_for_this_config(corpus):
    from core.retriever_pipeline import RetrieverPipeline
    data = json.loads((CACHE_DIR / "document_registry.json").read_text(encoding="utf-8"))
    assert data["config_fingerprint"] == RetrieverPipeline.compute_config_fingerprint()
    assert data["embedding_model"] == settings.EMBEDDING_MODEL


def test_store_matches_registry(corpus):
    assert corpus.store.count() == corpus.num_chunks > 0
    assert corpus.validate_cache_integrity()


def test_no_leftover_tmp_files():
    assert not glob.glob(str(CACHE_DIR / ".finsight_tmp_*"))


def test_scoped_retrieval_works(corpus):
    from core.lookup_index import RetrievalScope
    company = sorted(corpus.list_available_entities()["companies"])[0]
    vec = corpus.retriever.embed_query("key risk factors")
    res = corpus.search(RetrievalScope(label="t", companies=[company]), vec)
    assert res and all(r.document_label.startswith(company + "_") for r in res)
    assert all(r.page_number >= 1 for r in res)


def test_full_text_index_exists(corpus):
    hits = corpus.store.search_text("revenue", 3, None)
    assert hits
