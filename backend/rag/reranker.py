"""
Cross-Encoder Re-ranker

Takes top-K chunks from hybrid retrieval and re-scores each
(query, chunk) pair using a cross-encoder model for precise relevance.

Why re-ranking: Bi-encoder retrieval (used in the first stage) encodes
query and document independently — fast but imprecise. A cross-encoder
processes the query-document pair jointly with full attention, catching
subtle relevance signals that bi-encoders miss.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 — production-proven,
fast enough for top-20 re-ranking on CPU.
"""

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None

from typing import Optional
from loguru import logger

from backend.config import settings


# Lazy-loaded singleton
_reranker: Optional[CrossEncoder] = None


def get_reranker() -> Optional[CrossEncoder]:
    """Load the cross-encoder model (lazy singleton)."""
    global _reranker
    if CrossEncoder is None:
        logger.warning("sentence-transformers is not installed. Reranking will be disabled.")
        return None
    if _reranker is None:
        logger.info(f"Loading reranker model: {settings.reranker_model}")
        _reranker = CrossEncoder(settings.reranker_model)
        logger.info("Reranker model loaded.")
    return _reranker


def rerank(
    query: str,
    chunks: list[dict],
    top_k: int = None,
) -> list[dict]:
    """
    Re-rank retrieved chunks using cross-encoder scoring.

    Flow:
        top-20 (from hybrid retrieval)
        → cross-encoder scores each (query, chunk_text) pair
        → sorted by relevance score
        → return top-5

    Args:
        query: The user's query
        chunks: List of chunk dicts from retriever (must have 'text' key)
        top_k: Number of top results to return (default from settings)

    Returns:
        Re-ranked list of chunk dicts with added 'rerank_score' key
    """
    top_k = top_k or settings.rerank_top_k

    if not chunks:
        return []

    if len(chunks) <= top_k:
        logger.debug(f"Only {len(chunks)} chunks — skipping re-ranking")
        for chunk in chunks:
            chunk["rerank_score"] = 1.0
        return chunks

    model = get_reranker()
    if model is None:
        for chunk in chunks:
            if "rerank_score" not in chunk:
                chunk["rerank_score"] = 1.0
        return chunks[:top_k]

    # Create (query, document) pairs for cross-encoder
    pairs = [(query, chunk["text"]) for chunk in chunks]

    logger.debug(f"Re-ranking {len(pairs)} chunks...")
    scores = model.predict(pairs)

    # Attach scores and sort
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)

    # Log score distribution for debugging
    if reranked:
        top_score = reranked[0]["rerank_score"]
        bottom_score = reranked[-1]["rerank_score"]
        logger.debug(
            f"Re-ranking complete. Score range: [{bottom_score:.4f}, {top_score:.4f}] "
            f"→ returning top {top_k}"
        )

    return reranked[:top_k]
