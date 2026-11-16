"""
RetrievalScope: which slice of the corpus one sub-query searches.

core.chunk_store.scope_to_where turns it into a LanceDB pre-filter. (The
FAISS-era LookupIndex of per-document vector ranges lived here; LanceDB
filters on metadata columns directly.)
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class RetrievalScope:
    """
    companies  — empty list = no company filter (search full corpus)
    doc_types  — empty list = no doc_type filter
    years      — must match ChunkMetadata.year ("2024", "2024_Q3"); empty = no filter
    top_k      — retrieval budget (informational; search uses RETRIEVAL_K)
    label      — human-readable tag for logging and result tagging
    """
    label: str
    companies: List[str] = field(default_factory=list)
    doc_types: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    top_k: int = 5
