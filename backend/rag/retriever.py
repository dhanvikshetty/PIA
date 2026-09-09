"""
Hybrid Retriever

Combines BM25 (keyword/exact match) with dense vector similarity
using Reciprocal Rank Fusion (RRF). Metadata filtering happens
BEFORE retrieval to cut search space.

Why hybrid: Dense retrieval captures semantic similarity (paraphrased
queries), BM25 captures exact matches (SQL keywords, error codes).
Neither alone is sufficient — combining them via RRF gives the best
of both worlds.
"""

from rank_bm25 import BM25Okapi
from typing import Optional
from loguru import logger

from backend.config import settings
from backend.db.vector_store import vector_store


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer for BM25."""
    return text.lower().split()


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    weights: list[float],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.

    RRF score for document d = Σ (weight_i / (k + rank_i(d)))

    Args:
        ranked_lists: List of ranked result lists
        weights: Weight for each list
        k: RRF constant (default 60 per original paper)

    Returns:
        Merged and re-ranked list of unique results
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank_list, weight in zip(ranked_lists, weights):
        for rank, doc in enumerate(rank_list):
            doc_id = doc["id"]
            rrf_score = weight / (k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            # Keep the version with the most metadata
            if doc_id not in doc_map:
                doc_map[doc_id] = doc

    # Sort by RRF score descending
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    results = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = scores[doc_id]
        results.append(doc)

    return results


def hybrid_retrieve(
    query: str,
    top_k: int = None,
    company: Optional[str] = None,
    doc_type: Optional[str] = None,
    dense_weight: Optional[float] = None,
    bm25_weight: Optional[float] = None,
) -> list[dict]:
    """
    Perform hybrid retrieval: dense (Atlas $vectorSearch) + BM25, merged with RRF.

    Flow:
    1. Build metadata filter (company, doc_type) — applied BEFORE search
    2. Dense retrieval via Atlas $vectorSearch → top-K candidates
    3. BM25 retrieval over the same filtered corpus → top-K candidates
    4. RRF fusion → merged ranked list

    Args:
        query: User's search query
        top_k: Number of results to return (default from settings)
        company: Filter to specific company
        doc_type: Filter to specific doc type
        dense_weight: Weight for dense retrieval (default from settings)
        bm25_weight: Weight for BM25 retrieval (default from settings)

    Returns:
        List of dicts with keys: id, text, metadata, rrf_score
    """
    top_k = top_k or settings.retrieval_top_k
    dense_weight = dense_weight if dense_weight is not None else settings.dense_weight
    bm25_weight = bm25_weight if bm25_weight is not None else settings.bm25_weight

    # --- Build metadata filter ---
    where = None
    filters = []
    if company:
        filters.append({"company": company})
    if doc_type:
        filters.append({"doc_type": doc_type})

    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    filter_desc = f"company={company}, doc_type={doc_type}" if (company or doc_type) else "none"
    logger.info(f"Hybrid retrieval | query='{query[:50]}...' | filters={filter_desc} | top_k={top_k}")

    # --- Dense retrieval (Atlas $vectorSearch) ---
    logger.debug("  Running dense retrieval...")
    dense_results = vector_store.similarity_search(
        query=query,
        top_k=top_k,
        where=where,
    )
    logger.debug(f"  Dense retrieval returned {len(dense_results)} results")

    # --- BM25 retrieval ---
    logger.debug("  Running BM25 retrieval...")
    # Get all chunks matching the metadata filter (for BM25 index)
    all_filtered_chunks = vector_store.get_all_chunks(where=where)

    bm25_results = []
    if all_filtered_chunks:
        # Build BM25 index over the filtered corpus
        corpus = [_tokenize(chunk["text"]) for chunk in all_filtered_chunks]
        bm25 = BM25Okapi(corpus)

        # Score query against corpus
        query_tokens = _tokenize(query)
        bm25_scores = bm25.get_scores(query_tokens)

        # Get top-K by BM25 score
        scored_chunks = list(zip(all_filtered_chunks, bm25_scores))
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        for chunk, score in scored_chunks[:top_k]:
            bm25_results.append({
                "id": chunk["id"],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "bm25_score": float(score),
            })

    logger.debug(f"  BM25 retrieval returned {len(bm25_results)} results")

    # --- RRF Fusion ---
    logger.debug("  Fusing with RRF...")
    fused = reciprocal_rank_fusion(
        ranked_lists=[dense_results, bm25_results],
        weights=[dense_weight, bm25_weight],
    )

    results = fused[:top_k]
    logger.info(f"  Hybrid retrieval complete: {len(results)} results after RRF fusion")

    return results


def dense_only_retrieve(
    query: str,
    top_k: int = None,
    company: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> list[dict]:
    """
    Dense-only retrieval (no BM25). Used for evaluation baseline comparison.
    """
    top_k = top_k or settings.retrieval_top_k

    where = None
    filters = []
    if company:
        filters.append({"company": company})
    if doc_type:
        filters.append({"doc_type": doc_type})
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    return vector_store.similarity_search(query=query, top_k=top_k, where=where)
