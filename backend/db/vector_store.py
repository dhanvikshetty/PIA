"""
MongoDB Atlas Vector Search Wrapper

Provides a unified interface for storing and querying document chunks
with embeddings and metadata in MongoDB Atlas. Supports metadata pre-filtering.
"""

import time
from typing import Optional
from loguru import logger
from pymongo import MongoClient

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

from backend.config import settings


class VectorStore:
    """Wrapper around MongoDB Atlas Vector Search for chunk storage and similarity search."""

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._embedding_model: Optional[SentenceTransformer] = None

    def initialize(self):
        """Initialize MongoDB client and embedding model."""
        logger.info(f"Connecting to MongoDB Vector Store at: {settings.mongodb_uri[:35]}...")
        try:
            self._client = MongoClient(settings.mongodb_uri)
            self._db = self._client[settings.mongodb_db_name]
            self._collection = self._db[settings.mongodb_vector_collection]
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

        logger.info(f"Loading embedding model: {settings.embedding_model}")
        if SentenceTransformer is not None:
            try:
                self._embedding_model = SentenceTransformer(settings.embedding_model)
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer: {e}")
                self._embedding_model = None
        else:
            logger.warning("SentenceTransformer is not installed. Dense retrieval will fail.")
            self._embedding_model = None

        logger.info(
            f"Vector store ready. Collection '{settings.mongodb_vector_collection}' has {self._collection.count_documents({})} chunks."
        )

    @property
    def collection(self):
        if self._collection is None:
            self.initialize()
        return self._collection

    @property
    def embedding_model(self) -> Optional[SentenceTransformer]:
        if self._embedding_model is None and SentenceTransformer is not None:
            try:
                self.initialize()
            except Exception:
                pass
        return self._embedding_model

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        if self.embedding_model is not None:
            return self.embedding_model.encode(text).tolist()
        raise RuntimeError("Embedding model is unavailable. Make sure sentence-transformers is installed.")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings."""
        if self.embedding_model is not None:
            return self.embedding_model.encode(texts).tolist()
        raise RuntimeError("Embedding model is unavailable. Make sure sentence-transformers is installed.")

    def _map_filter(self, where: dict) -> dict:
        """Map a dict-style `where` query into MongoDB dot-notation filters."""
        if not where:
            return {}
        mapped = {}
        for k, v in where.items():
            if k in ("$and", "$or"):
                mapped[k] = [self._map_filter(item) for item in v]
            else:
                mapped[f"metadata.{k}"] = v
        return mapped

    def add_chunks(
        self,
        chunk_ids: list[str],
        texts: list[str],
        metadatas: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ):
        """
        Add document chunks to the MongoDB collection.

        Args:
            chunk_ids: Unique IDs for each chunk
            texts: Raw text content of each chunk
            metadatas: Metadata dicts (company, doc_type, page, source_file)
            embeddings: Pre-computed embeddings (computed if not provided)
        """
        if embeddings is None:
            embeddings = self.embed_texts(texts)

        operations = []
        for cid, txt, meta, emb in zip(chunk_ids, texts, metadatas, embeddings):
            operations.append({
                "_id": cid,
                "text": txt,
                "metadata": meta,
                "embedding": emb,
            })

        from pymongo import UpdateOne
        bulk_ops = [
            UpdateOne({"_id": op["_id"]}, {"$set": op}, upsert=True)
            for op in operations
        ]

        if bulk_ops:
            self.collection.bulk_write(bulk_ops)
        logger.info(f"Added/updated {len(chunk_ids)} chunks in MongoDB vector store.")

    def similarity_search(
        self,
        query: str,
        top_k: int = 20,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        Perform dense similarity search using MongoDB Atlas Vector Search.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Metadata filters

        Returns:
            List of dicts with keys: id, text, metadata, distance
        """
        # Graceful degradation: if the embedding model can't load (e.g.
        # sentence-transformers/torch not installed on a small prod instance),
        # skip dense search and let the caller fall back to BM25-only. This keeps
        # Ask Puddy answering instead of returning a hard 500.
        if self.embedding_model is None:
            logger.warning(
                "Dense retrieval skipped — embedding model unavailable "
                "(sentence-transformers not installed). Using BM25-only retrieval."
            )
            return []

        query_embedding = self.embed_text(query)
        mongo_filter = self._map_filter(where) if where else {}

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": max(top_k * 10, 100),
                    "limit": top_k,
                }
            }
        ]

        if mongo_filter:
            pipeline[0]["$vectorSearch"]["filter"] = mongo_filter

        pipeline.append({
            "$project": {
                "_id": 1,
                "text": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        })

        results = self.collection.aggregate(pipeline)

        chunks = []
        for doc in results:
            chunks.append({
                "id": str(doc["_id"]),
                "text": doc.get("text", ""),
                "metadata": doc.get("metadata", {}),
                "distance": 1.0 - doc.get("score", 0.0),  # Cosine distance
            })
        return chunks

    def get_all_chunks(
        self,
        where: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Get all chunks matching metadata query (for BM25 indexing).

        Args:
            where: Metadata filter query
            limit: Maximum number of chunks to return

        Returns:
            List of dicts with keys: id, text, metadata
        """
        mongo_filter = self._map_filter(where) if where else {}

        cursor = self.collection.find(mongo_filter)
        if limit:
            cursor = cursor.limit(limit)

        chunks = []
        for doc in cursor:
            chunks.append({
                "id": str(doc["_id"]),
                "text": doc.get("text", ""),
                "metadata": doc.get("metadata", {}),
            })
        return chunks

    def delete_by_source(self, source_file: str):
        """Delete all chunks from a specific source file."""
        res = self.collection.delete_many({"metadata.source_file": source_file})
        logger.info(f"Deleted {res.deleted_count} chunks from source: {source_file}")

    def get_stats(self) -> dict:
        """Get collection statistics."""
        count = self.collection.count_documents({})
        return {"total_chunks": count}

    def reset(self):
        """Delete all vector search documents."""
        res = self.collection.delete_many({})
        logger.warning(f"Vector store reset — deleted {res.deleted_count} chunks.")


# Singleton instance
vector_store = VectorStore()
