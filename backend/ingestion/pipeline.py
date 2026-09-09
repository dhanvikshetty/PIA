"""
Ingestion Pipeline

Orchestrates: PDF loading → chunking → embedding → structured extraction.
Idempotent: tracks ingested files by hash to skip duplicates.

Usage:
    python -m backend.ingestion.pipeline --data-dir ./data
"""

import hashlib
import sys
import argparse
from pathlib import Path
from loguru import logger

from backend.ingestion.pdf_loader import load_pdfs_from_directory, load_pdf
from backend.ingestion.chunker import chunk_documents
from backend.ingestion.embedder import embed_and_store
from backend.ingestion.structured_extractor import extract_and_store
from backend.db.mongo_store import structured_store
from backend.config import settings


def compute_file_hash(file_path: Path) -> str:
    """Compute MD5 hash of a file for deduplication."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            hasher.update(block)
    return hasher.hexdigest()


def is_already_ingested(file_path: Path) -> bool:
    """Check if a file has already been ingested (by hash)."""
    file_hash = compute_file_hash(file_path)
    existing = structured_store.find_one(
        "ingested_files",
        {"file_hash": file_hash},
    )
    return existing is not None


def mark_as_ingested(file_path: Path, num_chunks: int):
    """Record that a file has been ingested."""
    structured_store.insert("ingested_files", {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "file_hash": compute_file_hash(file_path),
        "num_chunks": num_chunks,
    })


def run_pipeline(
    data_dir: str | Path,
    skip_extraction: bool = False,
    force: bool = False,
) -> dict:
    """
    Run the full ingestion pipeline.

    Args:
        data_dir: Path to data directory with subdirectories
        skip_extraction: Skip LLM-based structured extraction (faster, no API calls)
        force: Force re-ingestion even if files were already processed

    Returns:
        Summary dict with processing counts
    """
    data_dir = Path(data_dir)
    logger.info(f"Starting ingestion pipeline | data_dir={data_dir}")

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return {"error": f"Directory not found: {data_dir}"}

    # Find all PDFs
    pdf_files = sorted(data_dir.rglob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files")

    if not pdf_files:
        logger.warning("No PDF files found in data directory.")
        return {"files_found": 0, "files_processed": 0}

    # Filter out already-ingested files (unless force=True)
    if not force:
        new_files = [f for f in pdf_files if not is_already_ingested(f)]
        skipped = len(pdf_files) - len(new_files)
        if skipped > 0:
            logger.info(f"Skipping {skipped} already-ingested files")
        pdf_files = new_files

    if not pdf_files:
        logger.info("All files already ingested. Use --force to re-ingest.")
        return {"files_found": 0, "files_processed": 0, "skipped": "all"}

    # Step 1: Load all PDFs
    logger.info("=" * 60)
    logger.info("STEP 1: Loading PDFs...")
    all_documents = []
    for pdf_path in pdf_files:
        try:
            docs = load_pdf(pdf_path)
            all_documents.extend(docs)
        except Exception as e:
            logger.error(f"Failed to load {pdf_path.name}: {e}")

    logger.info(f"Loaded {len(all_documents)} pages from {len(pdf_files)} files")

    # Step 2: Chunk documents
    logger.info("=" * 60)
    logger.info("STEP 2: Chunking documents...")
    chunks = chunk_documents(all_documents)
    logger.info(f"Created {len(chunks)} chunks")

    # Step 3: Embed and store in vector DB
    logger.info("=" * 60)
    logger.info("STEP 3: Embedding and storing chunks...")
    num_stored = embed_and_store(chunks)

    # Step 4: Structured extraction (optional, requires API key)
    extraction_summary = {"questions": 0, "companies": 0}
    if not skip_extraction:
        if settings.google_api_key and settings.google_api_key != "your_google_api_key_here":
            logger.info("=" * 60)
            logger.info("STEP 4: Extracting structured data...")
            extraction_summary = extract_and_store(chunks)
        else:
            logger.warning(
                "STEP 4: Skipping structured extraction — "
                "GOOGLE_API_KEY not configured. Set it in .env to enable."
            )
    else:
        logger.info("STEP 4: Structured extraction skipped (--skip-extraction)")

    # Mark files as ingested
    for pdf_path in pdf_files:
        file_chunks = [
            c for c in chunks
            if c.metadata.get("source_path") == str(pdf_path)
        ]
        mark_as_ingested(pdf_path, len(file_chunks))

    # Summary
    summary = {
        "files_processed": len(pdf_files),
        "pages_loaded": len(all_documents),
        "chunks_created": len(chunks),
        "chunks_stored": num_stored,
        "questions_extracted": extraction_summary.get("questions", 0),
        "companies_extracted": extraction_summary.get("companies", 0),
    }

    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    for k, v in summary.items():
        logger.info(f"  {k}: {v}")

    return summary


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="PIA Ingestion Pipeline")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=settings.data_dir,
        help="Path to data directory containing PDFs",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip LLM-based structured extraction",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion of all files",
    )

    args = parser.parse_args()
    run_pipeline(
        data_dir=args.data_dir,
        skip_extraction=args.skip_extraction,
        force=args.force,
    )


if __name__ == "__main__":
    main()
