"""
FinSight AI - Batch Ingestion: NIFTY 50 Annual Reports
========================================================
Deterministic batch ingestion script for annual reports.

Walks backend/data/<SYMBOL>/<YEAR>.pdf and ingests each PDF
via the existing CorpusManager pipeline.

Usage:
    cd backend
    python -m ingestion.batch_ingest_annual_reports

Author: FinSight AI Team
Stage: 7 (Batch Ingestion)
Phase 1: Fixed imports, added progress logging
"""

import os
import re
import sys
import time
from pathlib import Path

from config import settings

# Add backend root to path so package imports work when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))


from core.app_retrieval import open_for_ingest

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CACHE_DIR = settings.INDEX_CACHE_DIR
YEAR_PDF_RE = re.compile(r"^\d{4}\.pdf$")


def main():
    # ── Step 1: Validate data directory ──────────────────────────────
    data_dir = os.path.abspath(DATA_DIR)
    if not os.path.isdir(data_dir):
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)

    # ── Step 2: Open the store, resuming from the saved registry ─────
    corpus = open_for_ingest(CACHE_DIR)
    pipeline = corpus.retriever
    if pipeline.model.device.type == "cuda":
        pipeline.model.half()  # document vectors only; queries embed on CPU at serve time
    print(f"🖥️  Embedding device: {pipeline.model.device}; "
          f"{len(corpus.documents)} document(s) already indexed")

    # ── Step 4: Discover company folders (sorted alphabetically) ─────
    companies = sorted(
        entry
        for entry in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, entry))
    )

    # Count total PDFs for progress tracking
    total_pdfs = 0
    for company in companies:
        company_dir = os.path.join(data_dir, company)
        total_pdfs += sum(1 for f in os.listdir(company_dir) if YEAR_PDF_RE.match(f))

    print(f"\n📊 Found {total_pdfs} PDFs across {len(companies)} companies\n")

    # ── Step 5: Ingest each PDF ──────────────────────────────────────
    ingested = 0
    skipped = 0
    batch_start = time.time()

    for company in companies:
        company_dir = os.path.join(data_dir, company)

        # Collect only valid year PDFs, sorted numerically
        pdfs = sorted(
            f
            for f in os.listdir(company_dir)
            if YEAR_PDF_RE.match(f)
        )

        for pdf_name in pdfs:
            year = pdf_name.replace(".pdf", "")
            pdf_path = os.path.join(company_dir, pdf_name)

            doc_start = time.time()
            print(f"[{ingested + skipped + 1}/{total_pdfs}] Ingesting {company} - {year}...", end=" ", flush=True)

            try:
                corpus.add_document(
                    pdf_path=pdf_path,
                    company=company,
                    document_type="Annual_Report",
                    year=year,
                )
            except ValueError as e:
                print(f"SKIPPED ({e})")
                skipped += 1
                continue
            except Exception as e:
                print(f"\n❌ Error ingesting {company}/{year}: {e}")
                sys.exit(1)

            # Rows are already on disk; the registry marks them committed.
            corpus.save_registry(CACHE_DIR)

            doc_elapsed = time.time() - doc_start
            ingested += 1

            # Progress estimate
            elapsed_total = time.time() - batch_start
            avg_per_doc = elapsed_total / ingested
            remaining = (total_pdfs - ingested - skipped) * avg_per_doc
            remaining_min = remaining / 60

            print(f"✅ ({doc_elapsed:.1f}s) | ETA: {remaining_min:.0f}min", flush=True)

    print("🔤 Building full-text index...", flush=True)
    corpus.store.build_text_index()

    elapsed = time.time() - batch_start
    print(f"\n✅ Batch ingestion complete: {ingested} ingested, {skipped} skipped in {elapsed/60:.1f}min")


if __name__ == "__main__":
    main()

