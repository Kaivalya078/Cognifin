"""
Global corpus loading and retrieval, shared by the API (main.py) and the
retrieval scorer (tests/eval_retrieval.py) so both run exactly the same path.
"""

import os
import logging

import psutil

from config import settings
from core.cache_utils import has_leftover_tmp, clean_cache
from core.corpus_manager import CorpusManager
from core.retriever_pipeline import RetrieverPipeline
from core.reranker import init_reranker
from core.bm25_retriever import init_bm25
from core.retrieval_pipeline_v2 import refine_results
from query.query_orchestrator import retrieve_context

logger = logging.getLogger(__name__)


def load_global_corpus(cache_dir: str):
    """Load the pre-built index + registry and the reranker/BM25 on top of it.

    Returns (pipeline, corpus_manager). Raises RuntimeError when the cache
    is missing or inconsistent.
    """
    pipeline = RetrieverPipeline()
    corpus_manager = CorpusManager(pipeline)

    if not os.path.exists(cache_dir):
        raise RuntimeError(
            f"Cache directory '{cache_dir}' does not exist. "
            f"Run batch_ingest_annual_reports.py first."
        )
    if has_leftover_tmp(cache_dir):
        clean_cache(cache_dir)

    if not pipeline.load_index(cache_dir):
        raise RuntimeError(
            f"Failed to load FAISS index from '{cache_dir}'. "
            f"Run batch_ingest_annual_reports.py to rebuild."
        )
    if not corpus_manager.load_registry(cache_dir):
        raise RuntimeError(
            f"Failed to load document registry from '{cache_dir}'. "
            f"Run batch_ingest_annual_reports.py to rebuild."
        )
    if not corpus_manager.validate_cache_integrity(pipeline.index.ntotal):
        raise RuntimeError(
            "Cache integrity check failed. "
            "Run batch_ingest_annual_reports.py to rebuild."
        )
    corpus_manager.init_lookup_index(cache_dir, pipeline.index.ntotal)

    if init_reranker():
        print("🔄 Reranker loaded: " + settings.RERANKER_MODEL)
    else:
        print("⚠️  Reranker disabled or failed to load — using FAISS-only ranking")

    if init_bm25(pipeline.chunks):
        print(f"🔍 BM25 index built: {len(pipeline.chunks)} documents")
    else:
        print("⚠️  BM25 disabled or failed — using dense search only")

    print(f"📈 RSS after corpus load: {rss_mb():.0f} MB")
    return pipeline, corpus_manager


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
        all_chunks=pipeline.chunks,
        chunk_metadata=corpus_manager.chunk_metadata,
        final_k=final_k,
    )
    return candidates, final, parsed
