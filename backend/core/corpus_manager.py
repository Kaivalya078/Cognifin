"""
Corpus Manager: document registry + search on top of the LanceDB ChunkStore.

    main.py → CorpusManager → ChunkStore (vectors, text, metadata, FTS)
                            → RetrieverPipeline (chunking + embedding)

Rows are keyed by vector_id, a global insertion sequence; a document's
chunks occupy the contiguous range [vector_id_start, vector_id_end), which
the registry records. Citations use "chunk_<vector_id>".
"""

import os
import json
import logging
from dataclasses import asdict, replace as dc_replace
from types import SimpleNamespace
from typing import List, Dict, Callable, Optional

import numpy as np

from config import settings
from .chunk_store import ChunkStore, scope_to_where
from .retriever_pipeline import RetrieverPipeline
from .cache_utils import atomic_write_json
from .retrieval_logger import log_retrieval_event
from .metadata_schema import ChunkMetadata, DocumentRecord, RetrievalResult, create_default_metadata
from .lookup_index import RetrievalScope
from query.search_plan import SearchPlan, MergeStrategy

logger = logging.getLogger(__name__)

REGISTRY_FILE = "document_registry.json"


def pdf_url_for(pdf_path: str) -> str:
    """
    Public URL of a source PDF, from the path it was ingested from.

    pdf_path may be a Colab or Windows path, so keep only COMPANY/YEAR.pdf.
    Served from object storage when HF_PDF_BASE_URL is set, else from this
    API's /pdfs static mount (local dev).
    """
    parts = pdf_path.replace("\\", "/").rstrip("/").split("/")
    rel = "/".join(parts[-2:])
    base = settings.HF_PDF_BASE_URL.rstrip("/") or "/pdfs"
    return f"{base}/{rel}"


class _StoreMetadata:
    """Read-only vector_id → metadata view over the store (scorer, tooling)."""

    def __init__(self, store: ChunkStore):
        self._store = store

    def get(self, vector_id: int, default=None):
        row = self._store.get(vector_id)
        return SimpleNamespace(**row) if row else default


class CorpusManager:
    # False for /upload session corpora: their PDF is a deleted temp file,
    # so evidence from them must not advertise a PDF link.
    public_pdfs = True

    def __init__(self, retriever: RetrieverPipeline, store: ChunkStore):
        self.retriever = retriever
        self.store = store
        self.documents: Dict[str, DocumentRecord] = {}  # document_id → record
        self.chunk_metadata = _StoreMetadata(store)
        self._total_vectors = store.count()

    # =========================================================================
    # INGESTION
    # =========================================================================

    def add_document(
        self,
        pdf_path: str,
        company: str = "demo_company",
        document_type: str = "DRHP",
        year: str = "2024",
        source_type: str = "pdf",
        authority: int = 100,
        source_class: str = "official",
    ) -> int:
        """Chunk, embed and store one PDF; returns its chunk count.

        Raises ValueError if company + document_type + year is already
        registered, or if the PDF has no extractable text.
        """
        for doc_id, rec in self.documents.items():
            m = rec.metadata
            if (m.company, m.document_type, m.year) == (company, document_type, year):
                raise ValueError(
                    f"Document for {company}/{document_type}/{year} already exists as '{doc_id}'."
                )

        version = self._get_next_version(company, document_type, year)
        document_label = f"{company}_{document_type}_{year}_v{version}"
        logger.info("Adding document to corpus: %s", document_label)

        chunks = self.retriever.prepare_document(pdf_path)
        vectors = self.retriever.embed_texts([c.text for c in chunks])
        start = self._total_vectors

        metas = []
        for i, chunk in enumerate(chunks):
            m = create_default_metadata(vector_id=start + i, display_chunk_id=f"chunk_{i}",
                                        company=company, document_type=document_type, year=year)
            m.document_label = document_label
            m.source_type, m.authority, m.source_class = source_type, authority, source_class
            m.version = version
            m.page_number = chunk.page_number
            m.section_hint = chunk.heading[:120] or None
            m.content_form = chunk.content_form
            chunk.chunk_id = f"chunk_{start + i}"
            metas.append(m)

        self.store.add(chunks, metas, vectors)
        end = start + len(chunks)
        self._total_vectors = end
        self.documents[document_label] = DocumentRecord(
            document_id=document_label, pdf_path=pdf_path, chunk_count=len(chunks),
            vector_id_start=start, vector_id_end=end, metadata=metas[0],
            source_path=os.path.abspath(pdf_path),
        )
        logger.info("Corpus updated: %s (%d chunks, vectors %d-%d)",
                    document_label, len(chunks), start, end)
        return len(chunks)

    # =========================================================================
    # SEARCH
    # =========================================================================

    def _result(self, score: float, row: dict) -> RetrievalResult:
        rec = self.documents.get(row["document_label"])
        pdf_url = pdf_url_for(rec.pdf_path) if (rec and self.public_pdfs) else ""
        return RetrievalResult(
            chunk_id=f"chunk_{row['vector_id']}", score=score, snippet=row["text"],
            page_number=row["page_number"], document_label=row["document_label"], pdf_url=pdf_url,
        )

    def search(self, scope: RetrievalScope, query_vector: np.ndarray) -> List[RetrievalResult]:
        """Dense search within scope; drops results under SIMILARITY_THRESHOLD."""
        hits = self.store.search_dense(query_vector, settings.RETRIEVAL_K, scope_to_where(scope))
        results = [self._result(s, row) for s, row in hits]

        threshold = settings.SIMILARITY_THRESHOLD
        kept = [r for r in results if r.score >= threshold]
        log_retrieval_event(query="", results=kept, filtered_count=len(results) - len(kept),
                            threshold=threshold, scope_label=scope.label)
        return kept

    def execute_plan(
        self,
        plan: SearchPlan,
        embed_query: Callable[[str], np.ndarray],
    ) -> List[RetrievalResult]:
        per_subquery: List[List[RetrievalResult]] = []

        # Keep RETRIEVAL_K candidates for the reranker; refine_results()
        # trims to FINAL_K.
        merge_limit = settings.RETRIEVAL_K

        for sub_query in plan.sub_queries:
            vector = embed_query(sub_query.rewritten_query)
            results = self.search(sub_query.scope, vector)
            per_subquery.append(results)
            logger.debug("execute_plan [%s]: %d result(s) retrieved.", sub_query.label, len(results))

        if plan.merge_strategy == MergeStrategy.SINGLE:
            return per_subquery[0][:merge_limit]

        elif plan.merge_strategy == MergeStrategy.INTERLEAVED:
            merged: List[RetrievalResult] = []
            round_idx = 0
            while len(merged) < merge_limit:
                added_this_round = False
                for results in per_subquery:
                    if round_idx < len(results):
                        merged.append(results[round_idx])
                        added_this_round = True
                        if len(merged) >= merge_limit:
                            break
                if not added_this_round:
                    break
                round_idx += 1
            return merged

        elif plan.merge_strategy == MergeStrategy.SECTIONED:
            merged = []
            for sub_query, results in zip(plan.sub_queries, per_subquery):
                for r in results:
                    if len(merged) >= merge_limit:
                        break
                    merged.append(dc_replace(r, chunk_id=f"[{sub_query.label}]:{r.chunk_id}"))
                if len(merged) >= merge_limit:
                    break
            return merged

        logger.error("execute_plan: unhandled MergeStrategy '%s' — returning [].", plan.merge_strategy)
        return []

    def neighbor_texts(self, result: RetrievalResult, window: int) -> Optional[List[str]]:
        """Texts of the chunks around a result within its own document, in order.

        None when the result's document isn't in this corpus.
        """
        rec = self.documents.get(result.document_label)
        vid = _vector_id(result.chunk_id)
        if rec is None or vid is None or not rec.vector_id_start <= vid < rec.vector_id_end:
            return None
        rows = self.store.neighbors(rec.document_id, vid - rec.vector_id_start, window)
        return [r["text"] for r in rows]

    # =========================================================================
    # INTROSPECTION
    # =========================================================================

    def list_available_entities(self) -> dict:
        docs = self.documents.values()
        return {
            "companies": sorted({d.metadata.company for d in docs}),
            "document_types": sorted({d.metadata.document_type for d in docs}),
            "years": sorted({d.metadata.year for d in docs}),
            "total_chunks": self._total_vectors,
            "documents": list(self.documents.keys()),
        }

    @property
    def is_indexed(self) -> bool:
        return self._total_vectors > 0

    @property
    def num_chunks(self) -> int:
        return self._total_vectors

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def save_registry(self, save_dir: str) -> None:
        """Atomically write the document registry (chunks live in the store)."""
        os.makedirs(save_dir, exist_ok=True)
        atomic_write_json(os.path.join(save_dir, REGISTRY_FILE), {
            "config_fingerprint": RetrieverPipeline.compute_config_fingerprint(),
            "embedding_model": settings.EMBEDDING_MODEL,
            "total_vectors": self._total_vectors,
            "document_ingestion_order": list(self.documents.keys()),
            "documents": {
                doc_id: {**{k: v for k, v in asdict(rec).items() if k != "metadata"},
                         "metadata": asdict(rec.metadata)}
                for doc_id, rec in self.documents.items()
            },
        })
        print(f"💾 Registry saved: {len(self.documents)} document(s), {self._total_vectors} vectors")

    def load_registry(self, save_dir: str) -> bool:
        """Load the registry; False if missing, built with another config, or
        inconsistent with the store."""
        path = os.path.join(save_dir, REGISTRY_FILE)
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if data.get("config_fingerprint") != RetrieverPipeline.compute_config_fingerprint():
            print(f"⚠️  Index was built with a different config "
                  f"({data.get('embedding_model')}); re-run batch_ingest_annual_reports.py")
            return False

        self.documents = {}
        for doc_id in data["document_ingestion_order"]:
            d = dict(data["documents"][doc_id])
            d["metadata"] = ChunkMetadata(**d["metadata"])
            self.documents[doc_id] = DocumentRecord(**d)
        self._total_vectors = data["total_vectors"]
        print(f"📂 Registry loaded: {len(self.documents)} document(s), {self._total_vectors} vectors")
        return self.validate_cache_integrity()

    def validate_cache_integrity(self) -> bool:
        """Registry ranges are contiguous and add up to what the store holds."""
        expected = 0
        for doc_id, rec in self.documents.items():
            if rec.vector_id_start != expected or rec.vector_id_end - rec.vector_id_start != rec.chunk_count:
                print(f"⚠️  Document '{doc_id}' range {rec.vector_id_start}-{rec.vector_id_end} is inconsistent")
                return False
            expected = rec.vector_id_end
        stored = self.store.count()
        if expected != self._total_vectors or stored != self._total_vectors:
            print(f"⚠️  Registry ({self._total_vectors}) and store ({stored}) disagree")
            return False
        return True

    def _get_next_version(self, company: str, document_type: str, year: str) -> int:
        version = 1
        while f"{company}_{document_type}_{year}_v{version}" in self.documents:
            version += 1
        return version


def _vector_id(chunk_id: str) -> Optional[int]:
    tail = chunk_id.replace("[expanded]", "").rsplit("chunk_", 1)
    return int(tail[1]) if len(tail) == 2 and tail[1].isdigit() else None
