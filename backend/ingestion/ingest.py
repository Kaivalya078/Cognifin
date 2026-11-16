"""
FinSight AI - Document Ingestion CLI
=====================================
Offline tool for adding new documents to the corpus
without starting the server.

Usage:
    python ingest.py --file data/report.pdf --company TCS --type Annual_Report --year 2024

Chunks are written to the LanceDB store first; saving the registry is the
commit point. Rows written after the last saved registry (a crash in
between) are dropped on the next ingest run.

Author: FinSight AI Team
Stage: 2 (Manual Ingestion)
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add backend root to path so package imports work when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from core.app_retrieval import open_for_ingest


def parse_args():
    """Parse CLI arguments for document ingestion."""
    parser = argparse.ArgumentParser(
        description="FinSight AI — Ingest a document into the vector corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest.py --file data/report.pdf
  python ingest.py --file docs/tcs_annual.pdf --company TCS --type Annual_Report --year 2024
  python ingest.py --file docs/reliance_drhp.pdf --company Reliance --type DRHP --year 2025
        """,
    )
    
    parser.add_argument(
        "--file", required=True,
        help="Path to the PDF file to ingest",
    )
    parser.add_argument(
        "--company",
        default=settings.DEFAULT_COMPANY or "demo_company",
        help="Company identifier (default: from .env or 'demo_company')",
    )
    parser.add_argument(
        "--type",
        default=settings.DEFAULT_DOC_TYPE or "DRHP",
        help="Document type: DRHP, Annual_Report, etc. (default: from .env)",
    )
    parser.add_argument(
        "--year",
        default=settings.DEFAULT_YEAR or "2024",
        help="Fiscal year/period (default: from .env or '2024')",
    )
    parser.add_argument(
        "--cache-dir",
        default=settings.INDEX_CACHE_DIR,
        help="Cache directory (default: from .env or 'index_cache')",
    )
    
    return parser.parse_args()


def main():
    """
    Main ingestion entry point.
    
    Flow:
        1. Parse CLI args
        2. Validate PDF exists
        3. Init RetrieverPipeline + CorpusManager
        4. Load existing index + registry (if exists)
        5. Validate cache integrity BEFORE append
        6. Ingest document (duplicate check inside add_document)
        7. Save the registry and rebuild the full-text index
    """
    args = parse_args()
    
    pdf_path = args.file
    company = args.company
    doc_type = args.type
    year = args.year
    cache_dir = args.cache_dir
    
    # ── Step 1: Validate PDF exists ──────────────────────────────────
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    if not pdf_path.lower().endswith(".pdf"):
        print(f"⚠️  Warning: '{pdf_path}' does not have a .pdf extension")
    
    print("=" * 60)
    print("FinSight AI — Document Ingestion")
    print("=" * 60)
    print(f"  File:    {pdf_path}")
    print(f"  Company: {company}")
    print(f"  Type:    {doc_type}")
    print(f"  Year:    {year}")
    print(f"  Cache:   {cache_dir}")
    print()
    
    # ── Step 2: Open the store, resuming from the saved registry ─────
    try:
        corpus = open_for_ingest(cache_dir)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(f"📂 {len(corpus.documents)} document(s) already indexed")

    # ── Step 5: Ingest document ──────────────────────────────────────
    doc_id_preview = f"{company}_{doc_type}_{year}"
    print(f"📄 Ingesting: {doc_id_preview}")
    print(f"   Loading and chunking PDF...")
    
    import time
    t_start = time.time()
    
    try:
        num_chunks = corpus.add_document(
            pdf_path=pdf_path,
            company=company,
            document_type=doc_type,
            year=year,
        )
    except ValueError as e:
        # Duplicate protection or empty PDF
        print(f"\n❌ Ingestion aborted: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during ingestion: {e}")
        sys.exit(1)
    
    t_elapsed = time.time() - t_start
    print(f"   ✅ Indexed {num_chunks} chunks in {t_elapsed:.1f}s")
    
    # ── Step 6: Commit (rows are on disk; the registry marks them saved) ──
    corpus.save_registry(cache_dir)
    corpus.store.build_text_index()
    print("\n✅ Ingestion complete!")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Ingestion Summary")
    print("=" * 60)
    print(f"  Document:     {company}_{doc_type}_{year}")
    print(f"  Chunks added: {num_chunks}")
    print(f"  Total chunks: {corpus.num_chunks}")
    print(f"  Total documents: {len(corpus.documents)}")
    print(f"  Cache dir:    {cache_dir}")
    print(f"  Timestamp:    {datetime.now().isoformat()}")
    
    # List all documents in corpus
    print("\n📚 Corpus contents:")
    for doc_id, rec in corpus.documents.items():
        print(f"  • {doc_id} ({rec.chunk_count} chunks, "
              f"vectors {rec.vector_id_start}-{rec.vector_id_end})")
    
    print("\n🚀 Server will load the updated corpus on next restart.")


if __name__ == "__main__":
    main()
