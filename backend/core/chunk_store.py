"""
LanceDB chunk store: vectors, text, metadata and full-text search in one
disk-backed table (replaces FAISS + chunks.pkl + chunk_metadata.pkl + rank_bm25).

Rows are keyed by vector_id, the global insertion sequence, so citation ids
("chunk_<vector_id>") keep their meaning. chunk_seq is the position within
the chunk's document, used for neighbour (context-window) lookups.
"""

from dataclasses import fields
from typing import Dict, List, Optional, Tuple

import lancedb
import numpy as np
import pyarrow as pa
from lancedb.index import Bitmap, BTree

from core.lookup_index import RetrievalScope
from core.metadata_schema import ChunkMetadata

TABLE = "chunks"
_META_TYPES = {int: pa.int64(), str: pa.string(), bool: pa.bool_(), "Optional[str]": pa.string()}


def _schema(dim: int) -> pa.Schema:
    cols = [pa.field("vector", pa.list_(pa.float32(), dim)),
            pa.field("text", pa.string()),
            pa.field("chunk_seq", pa.int64())]
    for f in fields(ChunkMetadata):
        t = f.type if isinstance(f.type, type) else str(f.type).replace("typing.", "")
        cols.append(pa.field(f.name, _META_TYPES.get(t, pa.string())))
    return pa.schema(cols)


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def scope_to_where(scope: RetrievalScope) -> str:
    """SQL filter for a retrieval scope; only active chunks."""
    parts = ["is_active = true"]
    for col, values in (("company", scope.companies), ("year", scope.years),
                        ("document_type", scope.doc_types)):
        if values:
            parts.append(f"{col} IN ({', '.join(_quote(v) for v in values)})")
    return " AND ".join(parts)


class ChunkStore:
    def __init__(self, path: str, dim: int):
        self.path = path
        self.db = lancedb.connect(path)
        self.dim = dim
        try:
            self.table = self.db.open_table(TABLE)
        except ValueError:  # not created yet
            self.table = self.db.create_table(TABLE, schema=_schema(dim))

    def add(self, chunks, metas: List[ChunkMetadata], vectors: np.ndarray) -> None:
        if not (len(chunks) == len(metas) == len(vectors)):
            raise ValueError("chunks, metas and vectors differ in length")
        rows = []
        for seq, (c, m, v) in enumerate(zip(chunks, metas, vectors)):
            row = {f.name: getattr(m, f.name) for f in fields(ChunkMetadata)}
            row.update(vector=np.asarray(v, dtype=np.float32), text=c.text, chunk_seq=seq)
            rows.append(row)
        self.table.add(rows)

    def truncate(self, n: int) -> None:
        """Delete every row with vector_id >= n."""
        self.table.delete(f"vector_id >= {int(n)}")

    def count(self) -> int:
        return self.table.count_rows()

    def build_indexes(self) -> None:
        """Full-text index plus exact scalar indexes for the columns queries filter on
        (scope prefilters, neighbour lookups, get by id). Exact: results don't change."""
        self.table.create_fts_index("text", replace=True)
        for col in ("vector_id", "chunk_seq"):
            self.table.create_index(col, config=BTree(), replace=True)
        for col in ("document_label", "company", "year", "document_type", "is_active"):
            self.table.create_index(col, config=Bitmap(), replace=True)

    def search_dense(self, vector: np.ndarray, k: int,
                     where: Optional[str]) -> List[Tuple[float, Dict]]:
        q = self.table.search(np.asarray(vector, dtype=np.float32).ravel(),
                              vector_column_name="vector").distance_type("cosine")
        if where:
            q = q.where(where, prefilter=True)
        return [(1.0 - r.pop("_distance"), r) for r in q.limit(k).to_list()]

    def search_text(self, query: str, k: int,
                    where: Optional[str]) -> List[Tuple[float, Dict]]:
        q = self.table.search(query, query_type="fts")
        if where:
            q = q.where(where, prefilter=True)
        return [(r.pop("_score"), r) for r in q.limit(k).to_list()]

    def neighbors(self, document_label: str, chunk_seq: int, window: int) -> List[Dict]:
        rows = (self.table.search()
                .where(f"document_label = {_quote(document_label)} AND "
                       f"chunk_seq >= {int(chunk_seq) - window} AND chunk_seq <= {int(chunk_seq) + window}")
                .limit(2 * window + 1).to_list())
        return sorted(rows, key=lambda r: r["chunk_seq"])

    def get(self, vector_id: int) -> Optional[Dict]:
        rows = self.table.search().where(f"vector_id = {int(vector_id)}").limit(1).to_list()
        return rows[0] if rows else None
