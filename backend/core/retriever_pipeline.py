"""
Chunking + embedding: turns a PDF into Chunks (core.pdf_chunker) and text
into normalised vectors. Storage and search live in core.chunk_store.
"""

import os
import re
import json
import hashlib
import logging
import unicodedata
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer

from config import settings

NORMALIZATION_VERSION = "2"       # bump when normalize_text() logic changes
METADATA_SCHEMA_VERSION = "1"     # bump when ChunkMetadata fields change
CODE_VERSION = "4.0.0-lancedb"    # bump when chunking output changes
EMBEDDING_BATCH_SIZE = 32         # fixed across all paths for float stability

logger = logging.getLogger(__name__)

# One SentenceTransformer per model name per process: /upload builds a
# RetrieverPipeline per request and must not load another copy.
_MODELS: Dict[str, "SentenceTransformer"] = {}


@dataclass
class Chunk:
    """A piece of a document. text already carries the heading prefix."""
    chunk_id: str
    text: str
    start_char: int
    end_char: int
    page_number: int = 1
    heading: str = ""                  # section heading prefixed to text ("" = none)
    content_form: str = "narrative"    # "tabular" for table chunks


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


class RetrieverPipeline:
    def __init__(self, model_name: str = None):
        model_name = model_name or settings.EMBEDDING_MODEL
        if model_name not in _MODELS:
            print(f"🤖 Loading embedding model: {model_name}")
            _MODELS[model_name] = SentenceTransformer(model_name)
        self.model = _MODELS[model_name]
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

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
        """L2-normalised float32 vectors, shape (len(texts), embedding_dim).

        instruction: query prefix for asymmetric models (bge); never for documents.
        """
        if instruction:
            texts = [f"{instruction} {t}" for t in texts]
        vectors = self.model.encode(texts, batch_size=EMBEDDING_BATCH_SIZE,
                                    show_progress_bar=False, convert_to_numpy=True)
        # float32 even when an fp16 model (GPU ingestion) returns float16.
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def embed_query(self, query: str) -> np.ndarray:
        """One query vector, shape (1, embedding_dim), with QUERY_INSTRUCTION."""
        return self.embed_texts([query], instruction=settings.QUERY_INSTRUCTION or None)

    @staticmethod
    def compute_config_fingerprint() -> str:
        """SHA-256 of every setting that changes index content; a mismatch
        means the stored index must be rebuilt."""
        config = {
            "embedding_model": settings.EMBEDDING_MODEL,
            "chunk_size": settings.CHUNK_SIZE,
            "normalization_version": NORMALIZATION_VERSION,
            "metadata_schema_version": METADATA_SCHEMA_VERSION,
            "code_version": CODE_VERSION,
            "query_instruction": settings.QUERY_INSTRUCTION,
        }
        return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
