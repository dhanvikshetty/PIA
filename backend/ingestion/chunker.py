"""
Document Chunker

Splits documents into chunks using doc-type-aware parameters.
Interview experiences get smaller chunks (preserve Q&A context),
JDs get medium chunks (keep skill clusters), aptitude material
gets larger chunks (longer conceptual passages).
"""

import hashlib
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from backend.config import settings
from backend.ingestion.pdf_loader import Document


def generate_chunk_id(source_file: str, chunk_index: int, text: str) -> str:
    """
    Generate a deterministic chunk ID based on source and content.
    This makes ingestion idempotent — re-ingesting the same file
    produces the same chunk IDs → upsert instead of duplicate.
    """
    content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    safe_name = source_file.replace(" ", "_").replace(".", "_")
    return f"{safe_name}_chunk_{chunk_index}_{content_hash}"


def chunk_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into chunks using doc-type-aware parameters.

    Groups documents by doc_type, applies the appropriate chunking
    config, and preserves all metadata on each chunk.

    Args:
        documents: List of Document objects from pdf_loader

    Returns:
        List of chunked Document objects with added metadata:
            - chunk_id: deterministic unique ID
            - chunk_index: position within the source file
    """
    if not documents:
        return []

    # Group documents by doc_type for type-specific chunking
    doc_groups: dict[str, list[Document]] = {}
    for doc in documents:
        doc_type = doc.metadata.get("doc_type", "unknown")
        doc_groups.setdefault(doc_type, []).append(doc)

    all_chunks = []

    for doc_type, docs in doc_groups.items():
        config = settings.get_chunk_config(doc_type)
        chunk_size = config["chunk_size"]
        chunk_overlap = config["chunk_overlap"]

        logger.info(
            f"Chunking {len(docs)} pages of type '{doc_type}' | "
            f"chunk_size={chunk_size}, overlap={chunk_overlap}"
        )

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            is_separator_regex=False,
        )

        # Group pages by source file to maintain chunk ordering
        file_groups: dict[str, list[Document]] = {}
        for doc in docs:
            source = doc.metadata.get("source_file", "unknown")
            file_groups.setdefault(source, []).append(doc)

        for source_file, file_docs in file_groups.items():
            # Sort by page number
            file_docs.sort(key=lambda d: d.metadata.get("page_number", 0))

            chunk_index = 0
            for doc in file_docs:
                text_chunks = splitter.split_text(doc.text)

                for chunk_text in text_chunks:
                    if not chunk_text.strip():
                        continue

                    chunk_id = generate_chunk_id(
                        source_file, chunk_index, chunk_text
                    )

                    chunk_doc = Document(
                        text=chunk_text,
                        metadata={
                            **doc.metadata,
                            "chunk_id": chunk_id,
                            "chunk_index": chunk_index,
                            "chunk_size": len(chunk_text),
                        },
                    )
                    all_chunks.append(chunk_doc)
                    chunk_index += 1

            logger.debug(
                f"  {source_file}: {chunk_index} chunks created"
            )

    logger.info(f"Total chunks created: {len(all_chunks)}")
    return all_chunks
