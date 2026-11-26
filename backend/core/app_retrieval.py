"""
Global corpus loading and retrieval, shared by the API (main.py) and the
retrieval scorer (tests/eval_retrieval.py) so both run exactly the same path.
"""

import logging
import os

import psutil

from config import settings
from core.chunk_store import ChunkStore
from core.corpus_manager import CorpusManager
from core.reranker import init_reranker
from core.retrieval_pipeline_v2 import refine_results
from core.retriever_pipeline import RetrieverPipeline
from query.query_orchestrator import retrieve_context

logger = logging.getLogger(__name__)


STORE_SUBDIR = "lancedb"


def open_global_corpus(cache_dir: str) -> CorpusManager:
    """A CorpusManager on <cache_dir>/lancedb (created empty if absent)."""
    pipeline = RetrieverPipeline()
    store = ChunkStore(os.path.join(cache_dir, STORE_SUBDIR), pipeline.embedding_dim)
    return CorpusManager(pipeline, store)


def open_for_ingest(cache_dir: str) -> CorpusManager:
    """Global corpus ready to append to: resumes from the saved registry and
    drops store rows written after it (a crash between add and save).

    Raises RuntimeError if the existing index was built with another config.
    """
    cm = open_global_corpus(cache_dir)
    registry = os.path.join(cache_dir, "document_registry.json")
    if os.path.exists(registry):
        if not cm.load_registry(cache_dir):
            if cm.store.count() > cm.num_chunks and cm.documents:
                cm.store.truncate(cm.num_chunks)
                if cm.validate_cache_integrity():
                    print(f"↩️  Dropped rows past the last saved document; resuming at {cm.num_chunks}")
                    return cm
            raise RuntimeError(
                f"Index in '{cache_dir}' was built with a different config or is inconsistent; "
                f"delete it and re-run.")
    elif cm.store.count():
        cm.store.truncate(0)  # rows without any registry: start clean
        cm._total_vectors = 0
    return cm


def load_global_corpus(cache_dir: str):
    """Open the pre-built store + registry and load the reranker.

    Returns (pipeline, corpus_manager). Raises RuntimeError when the cache
    is missing, built with another config, or inconsistent.
    """
    if not os.path.isdir(os.path.join(cache_dir, STORE_SUBDIR)):
        raise RuntimeError(
            f"No index at '{cache_dir}/{STORE_SUBDIR}'. Run batch_ingest_annual_reports.py first."
        )
    corpus_manager = open_global_corpus(cache_dir)
    if not corpus_manager.load_registry(cache_dir):
        raise RuntimeError(
            f"Index in '{cache_dir}' is missing, stale or inconsistent. "
            f"Run batch_ingest_annual_reports.py to rebuild."
        )

    if init_reranker():
        print("🔄 Reranker loaded: " + settings.RERANKER_MODEL)
    else:
        print("⚠️  Reranker disabled or failed to load — using retrieval order")

    print(f"📈 RSS after corpus load: {rss_mb():.0f} MB")
    return corpus_manager.retriever, corpus_manager


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1e6


def retrieve_global(question: str, pipeline, corpus_manager, top_k: int, final_k: int):
    """Global-corpus retrieval: hybrid search, then rerank/boost/dedupe/enrich.

    Returns (candidates, final, parsed): the merged candidate pool, the
    final_k results the LLM sees, and the ParsedQuery.
    """
    candidates, parsed = retrieve_context(
        raw_query=question,
        corpus_manager=corpus_manager,
        embed_query=pipeline.embed_query,
        default_top_k=top_k,
    )
    final = refine_results(
        results=candidates,
        query=question,
        parsed_query=parsed,
        corpus=corpus_manager,
        final_k=final_k,
    )
    return candidates, final, parsed


def held_years(corpus_manager) -> dict:
    """{company: {report years}} in the global corpus."""
    held: dict = {}
    for d in corpus_manager.documents.values():
        held.setdefault(d.metadata.company, set()).add(str(d.metadata.year))
    return held


def outside_coverage(companies: list, years: list, held: dict) -> bool:
    """True when the question names companies and years and every asked year is older than
    each company's earliest report: answering would mean reading a later report's prior-year
    column (v4 eval: HINDZINC FY2024 from the FY2025 report, wrong). The chat then replies
    with the refusal, which shows the upload card. Future years ("2030 target") and years
    inside the held range go to the model: current reports talk about them."""
    def older(c, y) -> bool:
        return bool(held.get(c)) and str(y).isdigit() and int(y) < min(map(int, held[c]))
    return bool(companies and years) and all(older(c, y) for c in companies for y in years)
