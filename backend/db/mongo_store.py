"""
Structured Data Store

Stores structured/queryable facts (companies, interview questions, skills)
that don't need embedding search. Uses MongoDB when USE_MONGODB=true and the
cluster is reachable, otherwise falls back to a JSON-file store.

Why separate from vector DB: structured queries like "all SQL-tagged questions
for ProcDNA" are better served by a queryable store than by semantic search.
This is intentional hybrid storage, not redundancy.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Optional
from loguru import logger

from backend.config import settings


class JSONStore:
    """
    JSON-file-based structured store. Each collection is a JSON file.
    Works without any external database — good for local dev and demos.
    """

    def __init__(self, store_dir: Optional[str] = None):
        self.store_dir = Path(store_dir or settings.json_store_dir)
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Could not create store directory {self.store_dir}: {e}. If running on Vercel, this is expected.")
        self._cache: dict[str, list[dict]] = {}

    def _get_path(self, collection: str) -> Path:
        return self.store_dir / f"{collection}.json"

    def _load(self, collection: str) -> list[dict]:
        """Load a collection from disk (cached in memory)."""
        if collection not in self._cache:
            path = self._get_path(collection)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._cache[collection] = json.load(f)
            else:
                self._cache[collection] = []
        return self._cache[collection]

    def _save(self, collection: str):
        """Persist a collection to disk."""
        try:
            path = self._get_path(collection)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._cache.get(collection, []), f, indent=2, ensure_ascii=False)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not persist JSONStore collection '{collection}' to disk: {e}")

    def insert(self, collection: str, document: dict) -> str:
        """Insert a document into a collection. Returns the document ID."""
        data = self._load(collection)
        if "_id" not in document:
            document["_id"] = str(uuid.uuid4())
        data.append(document)
        self._cache[collection] = data
        self._save(collection)
        return document["_id"]

    def insert_many(self, collection: str, documents: list[dict]) -> list[str]:
        """Insert multiple documents. Returns list of IDs."""
        data = self._load(collection)
        ids = []
        for doc in documents:
            if "_id" not in doc:
                doc["_id"] = str(uuid.uuid4())
            ids.append(doc["_id"])
            data.append(doc)
        self._cache[collection] = data
        self._save(collection)
        return ids

    def find(
        self,
        collection: str,
        query: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Find documents matching a query dict.
        Simple key-value matching (no nested queries).

        Args:
            collection: Collection name
            query: Dict of field-value pairs to match (AND logic)
            limit: Max results
        """
        data = self._load(collection)
        if not query:
            results = data
        else:
            results = []
            for doc in data:
                match = all(
                    doc.get(k) == v
                    for k, v in query.items()
                )
                if match:
                    results.append(doc)
        if limit:
            results = results[:limit]
        return results

    def find_one(self, collection: str, query: dict) -> Optional[dict]:
        """Find a single matching document."""
        results = self.find(collection, query, limit=1)
        return results[0] if results else None

    def update(self, collection: str, query: dict, update_fields: dict) -> int:
        """Update all matching documents. Returns count of updated docs."""
        data = self._load(collection)
        count = 0
        for doc in data:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update_fields)
                count += 1
        if count > 0:
            self._save(collection)
        return count

    def delete(self, collection: str, query: dict) -> int:
        """Delete all matching documents. Returns count of deleted docs."""
        data = self._load(collection)
        original_len = len(data)
        data = [
            doc for doc in data
            if not all(doc.get(k) == v for k, v in query.items())
        ]
        deleted = original_len - len(data)
        self._cache[collection] = data
        if deleted > 0:
            self._save(collection)
        return deleted

    def count(self, collection: str, query: Optional[dict] = None) -> int:
        """Count documents matching a query."""
        return len(self.find(collection, query))

    def distinct(self, collection: str, field: str) -> list:
        """Get distinct values for a field across all documents."""
        data = self._load(collection)
        values = set()
        for doc in data:
            if field in doc:
                val = doc[field]
                if isinstance(val, list):
                    values.update(val)
                else:
                    values.add(val)
        return sorted(values)

    def aggregate_field(self, collection: str, group_field: str, count_field: Optional[str] = None) -> dict:
        """
        Simple aggregation: group by a field and count occurrences.
        If count_field is provided, count distinct values of that field per group.
        """
        data = self._load(collection)
        groups: dict[str, int] = {}
        for doc in data:
            key = doc.get(group_field, "unknown")
            if isinstance(key, list):
                for k in key:
                    groups[k] = groups.get(k, 0) + 1
            else:
                groups[key] = groups.get(key, 0) + 1
        return groups

    def drop_collection(self, collection: str):
        """Delete an entire collection."""
        path = self._get_path(collection)
        if path.exists():
            os.remove(path)
        self._cache.pop(collection, None)
        logger.warning(f"Dropped collection: {collection}")

    def list_collections(self) -> list[str]:
        """List all collection names."""
        return [
            p.stem for p in self.store_dir.glob("*.json")
        ]

    def get_stats(self) -> dict:
        """Get store statistics."""
        collections = self.list_collections()
        stats = {}
        for col in collections:
            stats[col] = self.count(col)
        return stats


class MongoStore:
    """
    MongoDB-backed structured store. Implements the same interface as
    JSONStore so the rest of the app is storage-agnostic.

    Documents use a string uuid `_id` (not ObjectId) so every document
    returned from a query is JSON-serializable and can be handed straight
    to FastAPI/Pydantic without conversion.
    """

    def __init__(self, uri: str, db_name: str):
        from pymongo import MongoClient

        self._client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        # Fail fast if the cluster is unreachable — surfaces to the factory
        # which then falls back to JSONStore.
        self._client.admin.command("ping")
        self._db = self._client[db_name]
        logger.info(f"MongoStore connected: db='{db_name}'")

    def _col(self, collection: str):
        return self._db[collection]

    def insert(self, collection: str, document: dict) -> str:
        """Insert a document into a collection. Returns the document ID."""
        if "_id" not in document:
            document["_id"] = str(uuid.uuid4())
        self._col(collection).insert_one(document)
        return document["_id"]

    def insert_many(self, collection: str, documents: list[dict]) -> list[str]:
        """Insert multiple documents. Returns list of IDs."""
        if not documents:
            return []
        for doc in documents:
            if "_id" not in doc:
                doc["_id"] = str(uuid.uuid4())
        self._col(collection).insert_many(documents)
        return [doc["_id"] for doc in documents]

    def find(
        self,
        collection: str,
        query: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Find documents matching a query dict (AND logic)."""
        cursor = self._col(collection).find(query or {})
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def find_one(self, collection: str, query: dict) -> Optional[dict]:
        """Find a single matching document."""
        return self._col(collection).find_one(query)

    def update(self, collection: str, query: dict, update_fields: dict) -> int:
        """Update all matching documents. Returns count of updated docs."""
        result = self._col(collection).update_many(query, {"$set": update_fields})
        return result.modified_count

    def delete(self, collection: str, query: dict) -> int:
        """Delete all matching documents. Returns count of deleted docs."""
        result = self._col(collection).delete_many(query)
        return result.deleted_count

    def count(self, collection: str, query: Optional[dict] = None) -> int:
        """Count documents matching a query."""
        return self._col(collection).count_documents(query or {})

    def distinct(self, collection: str, field: str) -> list:
        """
        Get distinct values for a field across all documents.
        Mongo flattens array-valued fields automatically.
        """
        return sorted(v for v in self._col(collection).distinct(field) if v is not None)

    def aggregate_field(
        self, collection: str, group_field: str, count_field: Optional[str] = None
    ) -> dict:
        """Group by a field and count occurrences (array values are unwound)."""
        pipeline = [
            {"$unwind": {"path": f"${group_field}", "preserveNullAndEmptyArrays": True}},
            {"$group": {"_id": {"$ifNull": [f"${group_field}", "unknown"]}, "n": {"$sum": 1}}},
        ]
        return {doc["_id"]: doc["n"] for doc in self._col(collection).aggregate(pipeline)}

    def drop_collection(self, collection: str):
        """Delete an entire collection."""
        self._db.drop_collection(collection)
        logger.warning(f"Dropped collection: {collection}")

    def list_collections(self) -> list[str]:
        """List all collection names."""
        return self._db.list_collection_names()

    def get_stats(self) -> dict:
        """Get store statistics."""
        return {col: self.count(col) for col in self.list_collections()}


def get_structured_store():
    """
    Factory function — returns the appropriate structured store.

    Returns MongoStore when USE_MONGODB is true and the cluster is reachable;
    otherwise falls back to the file-based JSONStore so local dev and demos
    never hard-break on a bad/missing connection.
    """
    if settings.use_mongodb:
        try:
            store = MongoStore(settings.mongodb_uri, settings.mongodb_db_name)
            logger.info("Using MongoStore for structured data.")
            return store
        except ImportError:
            logger.warning("pymongo not installed. Falling back to JSONStore.")
        except Exception as e:
            logger.warning(
                f"MongoDB connection failed ({e}). Falling back to JSONStore."
            )

    return JSONStore()


# Singleton instance — lazily initialized.
#
# We DON'T call get_structured_store() at import time: with USE_MONGODB=true it
# opens a MongoClient and blocks on an 8s `ping` handshake. On serverless (Vercel)
# that runs during every cold start and can hang the first request; even locally
# it delays every process boot. The lazy proxy below defers store creation (and
# any network I/O) until the first actual DB access, so importing this module is
# instant.
class _LazyStore:
    """Transparent proxy that builds the real store on first attribute access."""

    _store = None

    def _resolve(self):
        if _LazyStore._store is None:
            _LazyStore._store = get_structured_store()
        return _LazyStore._store

    def __getattr__(self, name):
        # Only called for names not found normally (i.e. store methods),
        # so _store/_resolve never recurse here.
        return getattr(self._resolve(), name)


structured_store = _LazyStore()
