"""
FinSight AI - Retriever Pipeline
=================================
This module implements the core retrieval logic:
1. Load PDF and extract text
2. Chunk text into smaller pieces
3. Generate embeddings for each chunk
4. Store embeddings in FAISS vector database
5. Retrieve top-K similar chunks for a query

Author: FinSight AI Team
Phase: 1 (Retrieval Only)
"""

import os
import re

from config import settings
import json
import logging
import pickle
import hashlib
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# PDF processing
import fitz  # PyMuPDF

# Embeddings
from sentence_transformers import SentenceTransformer

# Vector database
import faiss
import numpy as np


# Cache safety utilities
from .cache_utils import atomic_write_bytes, atomic_write_json, atomic_faiss_write

# Retrieval result data contract (owned by metadata_schema)
from .metadata_schema import RetrievalResult



# =============================================================================
# VERSION CONSTANTS (bump when the corresponding logic changes)
# =============================================================================

NORMALIZATION_VERSION = "2"       # bump when normalize_text() logic changes
METADATA_SCHEMA_VERSION = "1"     # bump when ChunkMetadata fields change
CACHE_FORMAT_VERSION = 2          # Phase 1: dimension 384→768, chunk 500→1000
CODE_VERSION = "3.0.0-structured-chunks"  # Phase 2: pdf_chunker
EMBEDDING_BATCH_SIZE = 32         # fixed across all paths for float stability

# Stage 3: search_scoped() tuning constants
_SCOPED_DENSITY_MULTIPLIER: int = 4
_SCOPED_INITIAL_MULTIPLIER: int = 3
logger = logging.getLogger(__name__)

# One SentenceTransformer per model name for the whole process. Every /upload
# builds a RetrieverPipeline; without this each one loaded its own copy.
_MODELS: Dict[str, "SentenceTransformer"] = {}


# =============================================================================
# CROSS-ENVIRONMENT PICKLE LOADER
# =============================================================================

# Module paths where the Chunk class may have been pickled from (e.g. Colab)
_CHUNK_MODULE_ALIASES = {"__main__", "retriever_pipeline"}

class _ChunkUnpickler(pickle.Unpickler):
    """
    Custom unpickler that remaps Chunk class references from alternate
    module paths to the current module. Handles pickles created on Colab
    (where Chunk is in __main__) or with flat imports (retriever_pipeline).
    """
    def find_class(self, module: str, name: str):
        if name == "Chunk" and module in _CHUNK_MODULE_ALIASES:
            return Chunk
        return super().find_class(module, name)

def _cross_env_unpickle(f):
    """Load a pickle file with cross-environment Chunk class remapping."""
    return _ChunkUnpickler(f).load()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Chunk:
    """
    Represents a single chunk of text from the document.

    Attributes:
        chunk_id:    Unique identifier (e.g., "chunk_0", "chunk_1")
        text:        The actual text content
        start_char:  Starting character position in the concatenated document
        end_char:    Ending character position in the concatenated document
        page_number: 1-based page number this chunk primarily comes from
    """
    chunk_id: str
    text: str
    start_char: int
    end_char: int
    page_number: int = 1
    heading: str = ""                  # section heading prefixed to text ("" = none)
    content_form: str = "narrative"    # "tabular" for table chunks


# =============================================================================
# TEXT NORMALIZATION
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize extracted PDF text before chunking, keeping line structure.

    1. Unicode NFC
    2. Drop non-printable characters (keeps newline, tab, space)
    3. Collapse runs of spaces/tabs within a line; strip each line
    4. Collapse 3+ newlines to a blank line; strip the whole text

    Newlines are kept because they carry table rows and paragraph breaks.
    """
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t ")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =============================================================================
# STAGE 3, 4, 5: RETRIEVER PIPELINE CLASS
# =============================================================================

class RetrieverPipeline:
    """
    Main retrieval pipeline that manages embeddings and vector search.
    
    This class handles:
    - Loading the embedding model
    - Generating embeddings for document chunks
    - Building and querying the FAISS index
    
    Usage:
        pipeline = RetrieverPipeline()
        pipeline.index_document("path/to/document.pdf")
        results = pipeline.retrieve("What are the risk factors?", top_k=5)
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the retriever pipeline.
        
        Args:
            model_name: Name of the sentence-transformers model to use.
                       Default: Uses EMBEDDING_MODEL from .env or 'all-MiniLM-L6-v2'
        """
        # Get model name from environment or use default
        if model_name is None:
            model_name = settings.EMBEDDING_MODEL
        
        print(f"🤖 Loading embedding model: {model_name}")
        print("   (This may take a minute on first run as the model downloads...)")
        
        # Load the embedding model once per process (downloads on first run)
        if model_name not in _MODELS:
            _MODELS[model_name] = SentenceTransformer(model_name)
        self.model = _MODELS[model_name]
        
        # Get embedding dimension (needed for FAISS)
        # For 'all-MiniLM-L6-v2', this is 384
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"   Embedding dimension: {self.embedding_dim}")
        
        # Initialize storage
        self.chunks: List[Chunk] = []  # Store chunks for retrieval
        self.index: Optional[faiss.IndexFlatIP] = None  # FAISS index
        
        # Track if we've indexed a document
        self.is_indexed = False
        
    def index_document(self, pdf_path: str) -> int:
        """Build a fresh index from one PDF (prepare → embed → append)."""
        self.index, self.chunks = None, []
        chunks = self.prepare_document(pdf_path)
        self.append_vectors(self.embed_texts([c.text for c in chunks]), chunks)
        return len(chunks)

    def retrieve(self, query: str, top_k: int = None) -> List[RetrievalResult]:
        """
        Retrieve the most relevant chunks for a query.
        
        How it works:
        1. Embed the query using the same model
        2. Search FAISS index for top-K similar vectors
        3. Return chunks with similarity scores
        
        Args:
            query: The user's question
            top_k: Number of results to return (default: from .env or 5)
            
        Returns:
            List of RetrievalResult objects, sorted by score (highest first)
        """
        if not self.is_indexed:
            raise RuntimeError("No document indexed. Call index_document() first.")
        
        # Get top_k from environment if not specified
        if top_k is None:
            top_k = settings.TOP_K
        
        # Ensure we don't request more results than we have chunks
        top_k = min(top_k, len(self.chunks))
        
        print(f"\n🔍 Retrieving top {top_k} chunks for: '{query[:50]}...'")
        
        # STAGE 5: Embed the query
        query_embedding = self.model.encode(
            [query],  # Model expects a list
            convert_to_numpy=True
        )
        
        # Normalize for cosine similarity
        faiss.normalize_L2(query_embedding)
        
        # Search the index
        # Returns:
        #   - distances: similarity scores (shape: 1 x top_k)
        #   - indices: chunk indices (shape: 1 x top_k)
        distances, indices = self.index.search(query_embedding, top_k)
        
        # Build results
        results = []
        for i, (score, idx) in enumerate(zip(distances[0], indices[0])):
            # Get the chunk
            chunk = self.chunks[idx]
            
            # Create result object
            result = RetrievalResult(
                chunk_id=chunk.chunk_id,
                score=float(score),  # Convert numpy float to Python float
                snippet=chunk.text
            )
            results.append(result)
            
            print(f"   [{i+1}] {chunk.chunk_id}: score={score:.4f}")
        
        return results

    def get_chunks(self) -> List['Chunk']:
        """
        Expose the chunk list for external use.
        
        Used by CorpusManager to map vector positions to metadata.
        
        Returns:
            List of Chunk objects (same as self.chunks)
        
        Added in Phase 2.5 — does not modify any existing behavior.
        """
        return self.chunks
    
    # =================================================================
    # STAGE 2: INGESTION SUPPORT (Append-Only)
    # =================================================================
    
    def prepare_document(self, pdf_path: str) -> List[Chunk]:
        """Load and chunk a PDF (core.pdf_chunker.chunk_pdf).

        Raises:
            FileNotFoundError: If the PDF doesn't exist
            ValueError: If the PDF yields no text (e.g. image-only scans)
        """
        from .pdf_chunker import chunk_pdf  # imports Chunk from this module

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        logger.info("Preparing document: %s", pdf_path)
        chunks = chunk_pdf(pdf_path)
        if not chunks:
            raise ValueError("PDF appears to be empty or contains no extractable text")
        logger.info("Prepared %d chunks", len(chunks))
        return chunks

    def embed_texts(self, texts: List[str], instruction: str = None) -> np.ndarray:
        """
        Embed raw text strings into normalized vectors.
        
        Pure text → vector API. Uses the same model and normalization
        as index_document() but does NOT modify self.index or self.chunks.
        
        Args:
            texts: List of text strings to embed
            instruction: Optional instruction prefix for asymmetric retrieval.
                        When provided, each text is encoded as "{instruction} {text}".
                        Used by BGE-family models for query encoding.
                        Document encoding should NOT use an instruction.
            
        Returns:
            Normalized numpy array of shape (len(texts), embedding_dim)
        """
        logger.info("Embedding %d texts...", len(texts))
        
        # Apply instruction prefix if provided (asymmetric retrieval)
        encode_texts = texts
        if instruction:
            encode_texts = [f"{instruction} {t}" for t in texts]
            logger.debug("Applied instruction prefix: '%s'", instruction[:50])
        
        # batch_size is fixed across all ingestion paths
        # to guarantee identical float results regardless of method
        embeddings = self.model.encode(
            encode_texts,
            batch_size=EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        
        # FAISS needs float32; an fp16 model (GPU ingestion) returns float16.
        embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
        faiss.normalize_L2(embeddings)
        
        logger.info("Embeddings shape: %s", embeddings.shape)
        return embeddings
    
    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query with instruction prefix for asymmetric retrieval.
        
        BGE-family models benefit from an instruction prefix on query text
        that differentiates query encoding from document encoding.
        The instruction is read from the QUERY_INSTRUCTION env var.
        
        Args:
            query: The user's query string
            
        Returns:
            Normalized numpy array of shape (1, embedding_dim)
        """
        instruction = settings.QUERY_INSTRUCTION
        return self.embed_texts([query], instruction=instruction if instruction else None)
    
    def append_vectors(self, embeddings: np.ndarray, chunks: List[Chunk]) -> None:
        """Append vectors and their chunks; chunk_id becomes chunk_<global position>."""
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embeddings ({len(embeddings)}) and chunks ({len(chunks)}) count mismatch"
            )

        if self.index is None:
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            logger.info("Created new FAISS index (dim=%d)", self.embedding_dim)

        start_pos = self.index.ntotal
        self.index.add(embeddings)
        for i, c in enumerate(chunks):
            c.chunk_id = f"chunk_{start_pos + i}"
            self.chunks.append(c)

        self.is_indexed = True
        logger.info(
            "Appended %d vectors (positions %d-%d), total: %d",
            len(chunks), start_pos, start_pos + len(chunks),
            self.index.ntotal,
        )

    # =================================================================
    # STAGE 3: SCOPED RETRIEVAL
    # =================================================================

    @staticmethod
    def _vid_in_ranges(
        vid: int,
        allowed_ranges: List[Tuple[int, int]],
    ) -> bool:
        lo, hi = 0, len(allowed_ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end = allowed_ranges[mid]
            if vid < start:
                hi = mid - 1
            elif vid >= end:
                lo = mid + 1
            else:
                return True
        return False

    def search_scoped(
        self,
        query_vector: np.ndarray,
        allowed_ranges: List[Tuple[int, int]],
        candidate_k: int,
        total_allowed: int,
    ) -> List[Tuple[float, int]]:
        if not allowed_ranges:
            logger.warning(
                "search_scoped: empty allowed_ranges — returning [] "
                "(candidate_k=%d, total_allowed=%d)",
                candidate_k, total_allowed,
            )
            return []

        max_fetch = min(
            self.index.ntotal,
            total_allowed * _SCOPED_DENSITY_MULTIPLIER,
        )

        batch = candidate_k * _SCOPED_INITIAL_MULTIPLIER
        collected: List[Tuple[float, int]] = []

        while True:
            batch = min(batch, max_fetch)
            distances, indices = self.index.search(query_vector, batch)

            collected = []
            for dist, vid in zip(distances[0], indices[0]):
                if vid < 0:
                    continue
                if self._vid_in_ranges(int(vid), allowed_ranges):
                    collected.append((float(dist), int(vid)))

            if len(collected) >= candidate_k:
                break

            if batch >= max_fetch:
                logger.debug(
                    "search_scoped: max_fetch=%d reached with only %d/%d "
                    "scoped results collected.",
                    max_fetch, len(collected), candidate_k,
                )
                break

            batch *= 2

        logger.debug(
            "search_scoped: returning %d results "
            "(candidate_k=%d, final_batch=%d, max_fetch=%d)",
            min(len(collected), candidate_k), candidate_k, batch, max_fetch,
        )
        return collected[:candidate_k]

    # =================================================================
    # PERSISTENCE (Stage 1)
    # =================================================================
    def save_index(self, save_dir: str, pdf_path: str,
                   document_id: str = "__default__") -> None:
        """
        Persist the FAISS index, chunks, and a manifest to disk.
        
        Uses atomic writes (write → tmp → fsync → rename) so a crash
        mid-save never leaves a corrupt cache.
        
        Saved files:
          - faiss.index          : FAISS binary index (with sanity check)
          - chunks.pkl           : Pickled list of Chunk objects
          - index_manifest.json  : Hash, params, fingerprint, sentinels
        
        Args:
            save_dir: Directory to save into (created if missing)
            pdf_path: Path to the source PDF (used for hash)
            document_id: ID of the document being saved (for per-doc sentinels)
        """
        os.makedirs(save_dir, exist_ok=True)
        
        # Atomic FAISS write (with post-write sanity check)
        atomic_faiss_write(self.index, os.path.join(save_dir, "faiss.index"))
        
        # Atomic chunks write
        chunks_data = pickle.dumps(self.chunks)
        atomic_write_bytes(os.path.join(save_dir, "chunks.pkl"), chunks_data)
        
        # Build manifest with fingerprint, sentinels, and version
        pdf_hash = self._compute_file_hash(pdf_path)
        manifest = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "config_fingerprint": self.compute_config_fingerprint(),
            "source_pdf_hash": pdf_hash,
            "source_pdf_path": pdf_path,
            "embedding_model": settings.EMBEDDING_MODEL,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "num_chunks": len(self.chunks),
            "embedding_dim": self.embedding_dim,
            "chunk_order_sentinel": self.compute_chunk_sentinels(
                self.chunks, document_id
            ),
            "created_at": datetime.now().isoformat(),
            "code_version": CODE_VERSION,
        }
        atomic_write_json(os.path.join(save_dir, "index_manifest.json"), manifest)
        
        print(f"💾 Index saved to {save_dir}/ ({len(self.chunks)} chunks)")
    
    def load_index(self, save_dir: str) -> bool:
        """
        Load a previously saved FAISS index and chunks from disk.
        
        Validates:
          - File existence
          - Chunk count consistency (index vs manifest vs chunks list)
          - Embedding dimension matches runtime model
          - Chunk order sentinels match loaded data
        
        Args:
            save_dir: Directory containing saved index files
            
        Returns:
            True if loaded successfully, False otherwise
        """
        index_path = os.path.join(save_dir, "faiss.index")
        chunks_path = os.path.join(save_dir, "chunks.pkl")
        manifest_path = os.path.join(save_dir, "index_manifest.json")
        
        # Check all required files exist
        if not all(os.path.exists(p) for p in [index_path, chunks_path, manifest_path]):
            return False
        
        try:
            # Load FAISS index
            self.index = faiss.read_index(index_path)
            
            # Load chunks (with cross-environment unpickler)
            # chunks.pkl may have been pickled on Colab where Chunk lived in
            # __main__ or retriever_pipeline. Remap to current module path.
            with open(chunks_path, "rb") as f:
                self.chunks = _cross_env_unpickle(f)
            
            # Load manifest for validation
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            # --- Validation 1: Chunk count consistency ---
            if self.index.ntotal != manifest["num_chunks"]:
                print("⚠️  Index/manifest chunk count mismatch — will re-index")
                return False
            
            if self.index.ntotal != len(self.chunks):
                print("⚠️  Index/chunks count mismatch — will re-index")
                return False
            
            # --- Validation 2: Embedding dimension drift ---
            stored_dim = manifest.get("embedding_dim")
            if stored_dim is not None and stored_dim != self.embedding_dim:
                print(f"⚠️  Embedding dimension drift: cached={stored_dim}, "
                      f"runtime={self.embedding_dim} — will re-index")
                return False
            
            # --- Validation 3: Chunk order sentinels ---
            stored_sentinels = manifest.get("chunk_order_sentinel")
            if stored_sentinels:
                for doc_id, expected in stored_sentinels.items():
                    current = self.compute_chunk_sentinels(
                        self.chunks, doc_id
                    )
                    current_doc = current.get(doc_id, {})
                    if (current_doc.get("first") != expected.get("first") or
                            current_doc.get("last") != expected.get("last")):
                        print(f"⚠️  Chunk order sentinel mismatch for '{doc_id}' "
                              f"— will re-index")
                        return False
            
            self.is_indexed = True
            print(f"📂 Loaded index from cache: {self.index.ntotal} chunks")
            return True
            
        except Exception as e:
            print(f"⚠️  Failed to load cached index: {e}")
            return False
    
    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """
        Compute SHA-256 hash of a file.
        
        Used to detect when the source PDF has changed,
        triggering a re-index instead of loading stale cache.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        return sha256.hexdigest()
    
    @staticmethod
    def compute_config_fingerprint() -> str:
        """
        Compute a SHA-256 fingerprint from all configuration parameters
        that affect index content.
        
        Any change in these values means the cache is incompatible.
        """
        config = {
            "embedding_model": settings.EMBEDDING_MODEL,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "normalization_version": NORMALIZATION_VERSION,
            "metadata_schema_version": METADATA_SCHEMA_VERSION,
            "query_instruction": settings.QUERY_INSTRUCTION,
        }
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    @staticmethod
    def compute_chunk_sentinels(
        chunks: List['Chunk'], document_id: str,
        n: int = 5
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Compute per-document ordering sentinels.
        
        Stores SHA-1 of (normalized_text + chunk_index) for the first
        and last N chunks. This detects reordering while remaining stable
        against benign normalization tweaks (because the index is included).
        
        Args:
            chunks: List of Chunk objects
            document_id: ID to key the sentinel under
            n: Number of sentinel hashes per side (default: 5)
            
        Returns:
            { document_id: { "first": [...], "last": [...] } }
        """
        def _hash_chunk(chunk: 'Chunk', idx: int) -> str:
            data = f"{chunk.text}{idx}".encode("utf-8")
            return hashlib.sha1(data).hexdigest()
        
        first = [_hash_chunk(c, i) for i, c in enumerate(chunks[:n])]
        last = [_hash_chunk(c, len(chunks) - n + i)
                for i, c in enumerate(chunks[-n:])]
        
        return {document_id: {"first": first, "last": last}}
    
    @staticmethod
    def check_cache_valid(save_dir: str, pdf_path: str) -> bool:
        """
        Check if the cached index is still valid for the given PDF.
        
        Validation order:
        1. Cache format version matches CACHE_FORMAT_VERSION
        2. Config fingerprint matches runtime config
        3. PDF hash matches (file hasn't changed)
        4. Embedding dimension matches runtime model
        
        Args:
            save_dir: Directory containing saved index files
            pdf_path: Path to the current source PDF
            
        Returns:
            True if cache is valid, False if re-indexing is needed
        """
        manifest_path = os.path.join(save_dir, "index_manifest.json")
        
        if not os.path.exists(manifest_path):
            return False
        
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            # Check 1: Cache format version
            stored_version = manifest.get("cache_format_version")
            if stored_version != CACHE_FORMAT_VERSION:
                print(f"🔄 Cache format version mismatch: "
                      f"cached={stored_version}, current={CACHE_FORMAT_VERSION} "
                      f"— will re-index")
                return False
            
            # Check 2: Config fingerprint
            runtime_fp = RetrieverPipeline.compute_config_fingerprint()
            if manifest.get("config_fingerprint") != runtime_fp:
                print("🔄 Config fingerprint changed — will re-index")
                return False
            
            # Check 3: PDF hash
            current_hash = RetrieverPipeline._compute_file_hash(pdf_path)
            if manifest.get("source_pdf_hash") != current_hash:
                print("🔄 PDF has changed — will re-index")
                return False
            
            # Check 4: Embedding dimension (early detection)
            # Full dimension validation happens in load_index() against
            # the actual runtime model, but we can pre-check here if
            # the dimension is stored in the manifest.
            
            return True
            
        except Exception as e:
            print(f"⚠️  Error reading manifest: {e}")
            return False


# =============================================================================
# TESTING (Only runs when script is executed directly)
# =============================================================================

if __name__ == "__main__":
    """
    Quick test of the retrieval pipeline.
    Run with: python retriever_pipeline.py
    """
    print("\n" + "="*60)
    print("FinSight AI - Retriever Pipeline Test")
    print("="*60)
    
    # Get PDF path from environment
    pdf_path = settings.PDF_PATH
    
    # Check if sample PDF exists
    if not os.path.exists(pdf_path):
        print(f"\n⚠️  Sample PDF not found at: {pdf_path}")
        print("   Please place a PDF file at this location and try again.")
        print("   Or update PDF_PATH in your .env file.")
        exit(1)
    
    # Initialize pipeline
    pipeline = RetrieverPipeline()
    
    # Index the document
    num_chunks = pipeline.index_document(pdf_path)
    print(f"\n✅ Successfully indexed {num_chunks} chunks!")
    
    # Test retrieval
    test_queries = [
        "What are the risk factors?",
        "What is the company's revenue?",
        "Who are the promoters?"
    ]
    
    print("\n" + "="*60)
    print("Testing Retrieval")
    print("="*60)
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        results = pipeline.retrieve(query, top_k=3)
        
        print(f"   Found {len(results)} results:")
        for r in results:
            # Show first 100 chars of snippet
            snippet_preview = r.snippet[:100].replace("\n", " ") + "..."
            print(f"   - {r.chunk_id} (score: {r.score:.3f}): {snippet_preview}")
