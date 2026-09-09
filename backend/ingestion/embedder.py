"""
Embedder

Computes embeddings for document chunks using sentence-transformers
and stores them into the MongoDB Atlas vector store with full metadata.
"""

from loguru import logger

from backend.ingestion.pdf_loader import Document
from backend.db.vector_store import vector_store


def embed_and_store(chunks: list[Document]) -> int:
    """
    Embed document chunks and store in the Atlas vector store.

    Args:
        chunks: List of chunked Document objects with metadata

    Returns:
        Number of chunks stored
    """
    if not chunks:
        logger.warning("No chunks to embed.")
        return 0

    # Prepare data for batch insertion
    chunk_ids = []
    texts = []
    metadatas = []

    for chunk in chunks:
        chunk_id = chunk.metadata.get("chunk_id", "")
        if not chunk_id:
            logger.warning(f"Chunk missing chunk_id, skipping: {chunk.text[:50]}...")
            continue

        chunk_ids.append(chunk_id)
        texts.append(chunk.text)

        # Keep metadata to scalar types (strings, ints, floats, bools)
        clean_meta = {}
        for k, v in chunk.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean_meta[k] = v
            elif v is None:
                clean_meta[k] = ""
            else:
                clean_meta[k] = str(v)
        metadatas.append(clean_meta)

    logger.info(f"Embedding {len(texts)} chunks...")

    # Compute embeddings in batch
    embeddings = vector_store.embed_texts(texts)

    # Store in the Atlas vector store
    vector_store.add_chunks(
        chunk_ids=chunk_ids,
        texts=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    logger.info(f"Successfully embedded and stored {len(chunk_ids)} chunks.")
    return len(chunk_ids)
