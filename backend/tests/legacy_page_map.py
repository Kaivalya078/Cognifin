"""
Recover page numbers for the legacy (Colab-built, pre-Phase-2) index.

Its pickled chunks carry no page_number, so every chunk reports page 1.
Chunks are consecutive slices of each PDF's text normalised by the old
rule (all whitespace collapsed to single spaces, pages joined by a space),
so each chunk is located by a forward search in that text and assigned
the page its first character falls on.

    python -m tests.legacy_page_map --cache index_cache_baseline
        -> <cache>/legacy_page_map.json   {vector_id: page_number}

Used only by tests/eval_retrieval.py to score the baseline. Delete with the
baseline cache.
"""

import argparse
import bisect
import json
import pickle
import sys
import unicodedata
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _norm_v1(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = "".join(c for c in t if c.isprintable() or c in "\n\r\t ")
    return " ".join(t.split()).strip()


def page_starts(pages):
    """(full_text, [(start_offset, page_number), ...]) for non-blank pages."""
    parts, starts, pos = [], [], 0
    for num, text in enumerate(pages, 1):
        if not text:
            continue
        if parts:
            pos += 1  # joining space
        starts.append((pos, num))
        parts.append(text)
        pos += len(text)
    return " ".join(parts), starts


def page_of(starts, offset: int) -> int:
    i = bisect.bisect_right([s for s, _ in starts], offset) - 1
    return starts[max(i, 0)][1]


class _LegacyChunk:
    """Stand-in for the legacy pickled Chunk class (only .text is read)."""


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return _LegacyChunk if name == "Chunk" else super().find_class(module, name)


def main() -> None:
    import fitz

    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    args = ap.parse_args()
    cache = Path(args.cache)

    with open(cache / "chunks.pkl", "rb") as f:
        chunks = _Unpickler(f).load()
    docs = json.loads((cache / "document_registry.json").read_text(encoding="utf-8"))["documents"]

    page_map, missing = {}, 0
    for doc in docs.values():
        company, rest = doc["document_id"].split("_Annual_Report_")  # "TCS", "2024_v1"
        year = rest.split("_v")[0]
        with fitz.open(BACKEND / "data" / company / f"{year}.pdf") as pdf:
            full, starts = page_starts([_norm_v1(p.get_text()) for p in pdf])
        cur = 0
        for vid in range(doc["vector_id_start"], doc["vector_id_end"]):
            i = full.find(chunks[vid].text, max(0, cur - 2000))
            if i < 0:
                missing += 1
                continue
            page_map[vid] = page_of(starts, i)
            cur = i + len(chunks[vid].text)

    (cache / "legacy_page_map.json").write_text(json.dumps(page_map), encoding="utf-8")
    print(f"located {len(page_map)}/{len(chunks)} chunks ({missing} not found)")


if __name__ == "__main__":
    main()
