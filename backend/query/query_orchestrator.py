"""
FinSight AI — Query Orchestrator (Stage 6)
==========================================
Pure orchestration layer that connects:
    parse_query  →  build_plan  →  CorpusManager.execute_plan

Phase 2: Returns (results, parsed_query) tuple for metadata-aware boosting.
Phase 3: Adds query expansion, multi-query generation, and hybrid search (BM25).
Phase 4: Adds intelligent LLM parsing → multi-step retrieval → context assembly.

Pipeline (Phase 4):
    raw_query
    → llm_parse_query()          (LLM-based, 6 intents)
    → plan_execution()           (intent → retrieval steps)
    → per step (PARALLEL):
        → expand_query()         (financial synonyms)
        → FAISS + BM25           (hybrid search)
        → RRF merge              (per-step)
        → refine_results()       (rerank + dedup)
    → assemble_context()         (labeled sections)
    → return (step_results, intelligent_query)
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Tuple

import numpy as np

from config import settings
from core.corpus_manager import CorpusManager
from core.metadata_schema import RetrievalResult
from core.result_merger import merge_results
from core.retrieval_pipeline_v2 import refine_results

from .execution_planner import RetrievalStep, plan_execution
from .intelligent_parser import (
    IntelligentQuery,
    llm_parse_query,
)
from .multi_query import generate_multi_queries, is_multi_query_enabled
from .query_expander import expand_query
from .query_understanding import ParsedQuery, parse_query
from .search_plan_builder import build_plan

logger = logging.getLogger(__name__)

# Thread pool for parallel step execution
_executor = ThreadPoolExecutor(max_workers=4)


def retrieve_context(
    raw_query: str,
    corpus_manager: CorpusManager,
    embed_query: Callable[[str], np.ndarray],
    default_top_k: int = 5,
) -> Tuple[List[RetrievalResult], ParsedQuery]:
    """
    Orchestrate the full Phase 3 retrieval pipeline.

    Flow:
        1. Parse query (extract company, year, intent)
        2. Expand query with financial synonyms
        3. Generate multi-query variants (LLM)
        4. For each variant: FAISS + BM25 search
        5. Merge all result lists via RRF
        6. Return (merged_results, parsed_query)

    Returns:
        Tuple of (results, parsed_query) — results are the merged
        candidate pool for the Phase 2 refinement pipeline.
    """
    # ── Step 1: Parse query (unchanged from Phase 2) ──
    entities = corpus_manager.list_available_entities()
    companies = entities.get("companies", [])
    parsed = parse_query(raw_query, companies)

    # ── Step 2: Expand query with financial synonyms ──
    expanded_query = expand_query(parsed.cleaned_query)
    logger.debug("Phase 3: expanded query: '%s'", expanded_query[:100])

    # ── Step 3: Generate multi-query variants ──
    if is_multi_query_enabled():
        query_variants = generate_multi_queries(expanded_query)
    else:
        query_variants = [expanded_query]

    logger.debug("Phase 3: %d query variants: %s", len(query_variants), query_variants)

    # ── Step 4: Retrieve for each variant (FAISS + BM25) ──
    retrieval_k = settings.RETRIEVAL_K
    all_result_lists: List[List[RetrievalResult]] = []
    all_labels: List[str] = []

    for i, variant in enumerate(query_variants):
        # 4a: FAISS dense search (via existing plan execution)
        plan = build_plan(parsed, default_top_k)

        # For comparison/temporal intents, build_plan creates per-entity
        # sub-queries with company/year prefixes (e.g., "WIPRO {query}").
        # Preserve those prefixes — only replace the core query portion.
        if parsed.intent in ("comparison", "temporal") and len(plan.sub_queries) > 1:
            for sq in plan.sub_queries:
                # Keep the entity label prefix, replace the query body
                sq.rewritten_query = f"{sq.label} {variant}"
        else:
            for sq in plan.sub_queries:
                sq.rewritten_query = variant

        dense_results = corpus_manager.execute_plan(plan, embed_query)
        if dense_results:
            all_result_lists.append(dense_results)
            all_labels.append(f"dense_q{i}")

        # 4b: keyword (BM25) search over the same scopes
        keyword_results = corpus_manager.search_text(
            [sq.scope for sq in plan.sub_queries], variant, retrieval_k)
        if keyword_results:
            all_result_lists.append(keyword_results)
            all_labels.append(f"bm25_q{i}")

    # ── Step 5: Merge all result lists via RRF ──
    if len(all_result_lists) > 1:
        merged = merge_results(
            result_lists=all_result_lists,
            labels=all_labels,
            top_k=retrieval_k,
        )
    elif all_result_lists:
        merged = all_result_lists[0][:retrieval_k]
    else:
        merged = []

    logger.debug(
        "Phase 3 complete: %d variants × %d search types → %d lists → %d merged",
        len(query_variants),
        2 if settings.BM25_ENABLED else 1,
        len(all_result_lists),
        len(merged),
    )

    return merged, parsed


# =============================================================================
# PHASE 4: INTELLIGENT RETRIEVAL
# =============================================================================

def intelligent_retrieve(
    raw_query: str,
    corpus_manager: CorpusManager,
    embed_query: Callable[[str], np.ndarray],
    pipeline=None,
    default_top_k: int = 5,
) -> Tuple[Dict[str, List[RetrievalResult]], IntelligentQuery]:
    """
    Phase 4 intelligent retrieval pipeline.

    Flow:
        1. LLM-parse query → IntelligentQuery (6 intents, metrics, strategy)
        2. Plan execution → List[RetrievalStep]
        3. Execute steps in PARALLEL (each step uses Phase 3 pipeline)
        4. Refine per-step results (Phase 2: rerank + dedup)
        5. Return step_results dict for context assembly

    Performance optimizations:
        - Multi-query DISABLED for multi-step queries (latency control)
        - Parallel step execution via ThreadPoolExecutor
        - Reduced retrieval_k for multi-step (MULTI_STEP_RETRIEVAL_K)
        - Reranker sees fewer candidates per step

    Fallback:
        On ANY failure, falls back to Phase 3 retrieve_context().

    Args:
        raw_query:       User's original question
        corpus_manager:  Loaded CorpusManager with FAISS index
        embed_query:     Embedding function from pipeline
        pipeline:        RetrieverPipeline (for chunks/metadata access)
        default_top_k:   Results per step

    Returns:
        Tuple of:
        - step_results: Dict[label → List[RetrievalResult]]
        - iq: IntelligentQuery with parsing details
    """
    start = time.time()

    # ── Step 1: LLM Parse ──
    entities = corpus_manager.list_available_entities()
    known_companies = entities.get("companies", [])
    iq = llm_parse_query(raw_query, known_companies)

    logger.info(
        "Phase 4: intent=%s, complexity=%s, strategy=%s, "
        "companies=%s, metrics=%s (parse: %s, %.0fms)",
        iq.intent, iq.complexity, iq.retrieval_strategy,
        iq.companies, iq.metrics, iq.parse_method, iq.parse_time_ms,
    )

    # ── Step 2: Plan Execution ──
    steps = plan_execution(iq)
    is_multi_step = len(steps) > 1

    logger.debug("Phase 4: %d retrieval steps planned", len(steps))

    # ── Step 3: Execute Steps (parallel for multi-step) ──
    final_k = settings.FINAL_K

    def _execute_step(step: RetrievalStep) -> Tuple[str, List[RetrievalResult]]:
        """Execute a single retrieval step using Phase 3 pipeline."""
        try:
            step_results = _run_step_retrieval(
                step=step,
                corpus_manager=corpus_manager,
                embed_query=embed_query,
                pipeline=pipeline,
                is_multi_step=is_multi_step,
                final_k=final_k,
            )
            return step.label, step_results
        except Exception as e:
            logger.error("Step '%s' failed: %s", step.label, e)
            return step.label, []

    # Parallel execution for multi-step, sequential for single
    if is_multi_step and len(steps) > 1:
        futures = [_executor.submit(_execute_step, step) for step in steps]
        step_results_dict = {}
        for future in futures:
            label, results = future.result(timeout=30)
            step_results_dict[label] = results
    else:
        step_results_dict = {}
        for step in steps:
            label, results = _execute_step(step)
            step_results_dict[label] = results

    total_chunks = sum(len(r) for r in step_results_dict.values())
    elapsed = time.time() - start

    logger.info(
        "Phase 4 complete: %d steps → %d total chunks in %.2fs",
        len(steps), total_chunks, elapsed,
    )

    return step_results_dict, iq


def _run_step_retrieval(
    step: RetrievalStep,
    corpus_manager: CorpusManager,
    embed_query: Callable[[str], np.ndarray],
    pipeline,
    is_multi_step: bool,
    final_k: int,
) -> List[RetrievalResult]:
    """
    Execute a single retrieval step using the Phase 3 pipeline.

    For multi-step queries:
        - Multi-query generation is DISABLED (latency control)
        - Uses reduced retrieval_k (MULTI_STEP_RETRIEVAL_K)

    For single-step queries:
        - Full Phase 3 pipeline (multi-query + BM25 + RRF)
    """
    retrieval_k = step.retrieval_k

    # ── Step A: Expand query with financial synonyms ──
    expanded = expand_query(step.query)

    # ── Step B: Query variants ──
    # Multi-query DISABLED for multi-step (latency control)
    if is_multi_step or not is_multi_query_enabled():
        query_variants = [expanded]
    else:
        query_variants = generate_multi_queries(expanded)

    # ── Step C: Build scope from step filters ──
    from core.lookup_index import RetrievalScope
    scope = RetrievalScope(
        label=step.label,
        companies=step.companies,
        doc_types=step.doc_types,
        years=step.years,
        top_k=retrieval_k,
    )

    # ── Step D: Retrieve per variant (FAISS + BM25) ──
    all_result_lists: List[List[RetrievalResult]] = []
    all_labels: List[str] = []

    for i, variant in enumerate(query_variants):
        # FAISS dense search
        vector = embed_query(variant)
        dense_results = corpus_manager.search(scope, vector)
        if dense_results:
            all_result_lists.append(dense_results)
            all_labels.append(f"dense_{step.label}_q{i}")

        # Keyword (BM25) search
        keyword_results = corpus_manager.search_text([scope], variant, retrieval_k)
        if keyword_results:
            all_result_lists.append(keyword_results)
            all_labels.append(f"bm25_{step.label}_q{i}")

    # ── Step E: Merge via RRF ──
    if len(all_result_lists) > 1:
        merged = merge_results(all_result_lists, all_labels, top_k=retrieval_k)
    elif all_result_lists:
        merged = all_result_lists[0][:retrieval_k]
    else:
        merged = []

    # ── Step F: Phase 2 refinement (rerank + boost + dedup) ──
    # Build a ParsedQuery-compatible object for the refiner
    from .query_understanding import ParsedQuery
    parsed_for_refine = ParsedQuery(
        cleaned_query=step.query,
        companies=step.companies,
        years=step.years,
        document_types=step.doc_types,
        intent="single_entity" if len(step.companies) <= 1 else "comparison",
    )

    refined = refine_results(
        results=merged,
        query=step.query,
        parsed_query=parsed_for_refine,
        corpus=corpus_manager,
        final_k=final_k,
    )

    return refined
