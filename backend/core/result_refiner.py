"""
Cognifin — Result Refiner (Phase 2: Retrieval Precision)
=============================================================
Post-reranking result refinement: metadata boosting, deduplication,
and context enrichment.

All functions are pure (no state, no I/O, no model inference).
They operate on List[RetrievalResult] and return refined lists.

Phase: 2 (Retrieval Precision Layer)
"""

import logging
from collections import Counter
from dataclasses import replace as dc_replace
from typing import List, Optional

from config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# METADATA-AWARE BOOSTING
# =============================================================================

def boost_by_metadata(
    results: list,
    query_company: Optional[str] = None,
    query_year: Optional[str] = None,
    query_doc_type: Optional[str] = None,
    intent: str = "",
) -> list:
    """
    Boost results that match the query's metadata filters.

    Additive boost: score += company_boost + year_boost + doctype_boost.
    Results are re-sorted after boosting.

    Boost is DISABLED for 'comparison' intent to avoid over-favoring
    one company in cross-company comparison queries.

    Args:
        results:        List of RetrievalResult objects
        query_company:  Company from parsed query (e.g. "RELIANCE")
        query_year:     Year from parsed query (e.g. "2025")
        query_doc_type: Document type from parsed query (e.g. "Annual_Report")
        intent:         Query intent — boost disabled for "comparison"

    Returns:
        Re-sorted list of RetrievalResult with boosted scores
    """
    if not results:
        return results

    # Disable boost for comparison queries — we need balanced results
    if intent == "comparison":
        logger.debug("boost_by_metadata: skipped (comparison intent)")
        return results

    # Read boost weights from env (user-approved defaults)
    company_boost = settings.BOOST_COMPANY
    year_boost = settings.BOOST_YEAR
    doctype_boost = settings.BOOST_DOCTYPE

    boosted = []
    for r in results:
        boost = 0.0

        # Company match — case-insensitive
        if query_company and hasattr(r, "document_label"):
            if query_company.upper() in r.document_label.upper():
                boost += company_boost

        # Year match
        if query_year and hasattr(r, "document_label"):
            if query_year in r.document_label:
                boost += year_boost

        # Document type match
        if query_doc_type and hasattr(r, "document_label"):
            if query_doc_type.upper() in r.document_label.upper():
                boost += doctype_boost

        if boost > 0:
            updated = dc_replace(r, score=round(r.score + boost, 4))
            boosted.append(updated)
        else:
            boosted.append(r)

    # Re-sort by boosted score (descending)
    boosted.sort(key=lambda x: x.score, reverse=True)

    boosted_count = sum(1 for i, (a, b) in enumerate(zip(results, boosted)) if a.chunk_id != b.chunk_id)
    if boosted_count > 0:
        logger.debug(
            "boost_by_metadata: %d position changes (company=%s, year=%s, doc=%s)",
            boosted_count, query_company, query_year, query_doc_type,
        )

    return boosted


# =============================================================================
# DEDUPLICATION & DIVERSITY
# =============================================================================

def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Compute Jaccard similarity between two texts using word tokens.

    Fast approximation of text similarity — O(n) where n is token count.
    Suitable for detecting near-duplicate chunks (paragraphs that overlap
    due to chunking overlap).

    Returns:
        Float in [0, 1] where 1.0 = identical token sets
    """
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    return len(intersection) / len(union)


def deduplicate(
    results: list,
    similarity_threshold: Optional[float] = None,
    max_from_one_doc: Optional[float] = None,
) -> list:
    """
    Remove near-duplicate chunks and enforce document diversity.

    Two-pass algorithm:
    1. Near-duplicate removal: If two chunks have Jaccard similarity
       above threshold, keep the one with higher score.
    2. Document diversity: Cap results from any single document at
       max_from_one_doc fraction of total results.

    Args:
        results:              Sorted list of RetrievalResult (by score, descending)
        similarity_threshold: Jaccard threshold for duplicate detection (default: env)
        max_from_one_doc:     Max fraction from one document (default: env)

    Returns:
        Deduplicated, diversity-enforced list of RetrievalResult
    """
    if not results:
        return results

    threshold = similarity_threshold or settings.DEDUP_THRESHOLD
    max_frac = max_from_one_doc or settings.MAX_FROM_ONE_DOC

    # ── Pass 1: Near-duplicate removal ──
    # Iterate in score order; skip chunks too similar to any already-accepted chunk
    unique: List = []
    removed_ids: List[str] = []

    for candidate in results:
        is_dup = False
        for accepted in unique:
            sim = _jaccard_similarity(candidate.snippet, accepted.snippet)
            if sim >= threshold:
                is_dup = True
                removed_ids.append(candidate.chunk_id)
                break
        if not is_dup:
            unique.append(candidate)

    # ── Pass 2: Company-level diversity enforcement ──
    # Use company name extracted from document_label to prevent one
    # company from dominating results in comparison queries.
    total = len(unique)
    max_per_company = max(1, int(total * max_frac))

    company_counts: Counter = Counter()
    diverse: List = []

    for r in unique:
        doc_label = r.document_label or "unknown"
        # Extract company: "WIPRO_Annual_Report_2024_v1" → "WIPRO"
        company_key = doc_label.split("_")[0]
        if company_counts[company_key] < max_per_company:
            diverse.append(r)
            company_counts[company_key] += 1
        else:
            removed_ids.append(r.chunk_id)

    if removed_ids:
        logger.debug(
            "deduplicate: removed %d chunks (dup=%d, diversity=%d). IDs: %s",
            len(removed_ids),
            len(results) - len(unique),
            len(unique) - len(diverse),
            removed_ids[:5],
        )

    return diverse


# =============================================================================
# CONTEXT ENRICHMENT
# =============================================================================

def enrich_context(results: list, corpus, window: Optional[int] = None) -> list:
    """
    Expand each result with its neighbouring chunks from the same document.

    corpus: the CorpusManager the results came from. Results whose document
    isn't in it (e.g. session uploads when the global corpus is passed) are
    left as they are. Expanded results get an "[expanded]" chunk_id prefix.
    """
    ctx_window = window if window is not None else settings.CONTEXT_WINDOW
    if ctx_window == 0 or not results or corpus is None:
        return results

    max_merged_chars = settings.CHUNK_SIZE * 2
    enriched = []
    for r in results:
        texts = corpus.neighbor_texts(r, ctx_window)
        merged = "\n".join(texts)[:max_merged_chars] if texts else ""
        if len(merged) > len(r.snippet):
            chunk_id = r.chunk_id if r.chunk_id.startswith("[expanded]") else f"[expanded]{r.chunk_id}"
            enriched.append(dc_replace(r, snippet=merged, chunk_id=chunk_id))
        else:
            enriched.append(r)

    expanded = sum(1 for a, b in zip(results, enriched) if a is not b)
    if expanded:
        logger.debug("enrich_context: expanded %d/%d chunks (window=%d)", expanded, len(enriched), ctx_window)
    return enriched
