"""
PIA — Centralized Configuration
Loads from .env, provides typed access to all settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- API Keys ---
    google_api_key: str = Field(default="", description="Google Gemini API key")
    groq_api_key: str = Field(default="", description="Groq API key (primary for non-grounded text)")

    def model_post_init(self, __context):
        super().model_post_init(__context)
        import os
        if not self.google_api_key:
            self.google_api_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if not self.groq_api_key:
            self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        if not self.redis_url:
            self.redis_url = os.environ.get("REDIS_URL", "")
        if not self.jwt_secret:
            self.jwt_secret = os.environ.get("JWT_SECRET", "")
        if os.environ.get("VERCEL"):
            self.json_store_dir = "/tmp/json_data"
            self.data_dir = "/tmp/data"

    # --- MongoDB ---
    use_mongodb: bool = Field(default=True)
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_db_name: str = Field(default="pia_db")
    mongodb_vector_collection: str = Field(default="vector_chunks")

    # --- JSON Store (fallback) ---
    json_store_dir: str = Field(default="./json_data")

    # --- Redis cache (optional — degrades to no-op if redis_url is unset) ---
    # Caches grounded dossiers (24h ± jitter), stampede lock, JWT refresh tokens.
    # Mirrors the Mongo→JSON fallback pattern: absent Redis never breaks the app.
    redis_url: str = Field(default="")
    cache_ttl_hours: int = Field(default=24)

    # --- Auth / JWT ---
    # jwt_secret MUST be set in prod (env JWT_SECRET). When blank, security.py
    # falls back to a dev-only secret and logs a warning — fine for local dev,
    # never for a real deploy. Refresh-token revocation needs Redis; without it
    # refresh degrades to stateless (signature+expiry only), mirroring the
    # cache's no-op fallback.
    jwt_secret: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)

    # --- Rate limiting (per-client fixed window) ---
    # Uses Redis when available (shared across all gunicorn workers / instances),
    # else an in-process counter (per-worker). Protects the expensive LLM/grounded
    # routes and auth endpoints from abuse. Set rate_limit_enabled=false to disable.
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_window_seconds: int = Field(default=60)
    rate_limit_default: int = Field(default=60)      # normal routes, per window
    rate_limit_expensive: int = Field(default=12)    # LLM/grounded/auth, per window

    # --- Models ---
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    # Non-grounded answer generation (Ask Puddy). Groq is tried first (see
    # llm_client.py); this Gemini model is the fallback. Lite = 500 RPD vs the
    # old 2.5-flash 20 RPD, so even the fallback path has 25x more headroom.
    llm_model: str = Field(default="gemini-3.5-flash-lite")
    # Fast model for structured JSON extraction (resume analyzer, ingestion).
    # Thinking models (2.5-flash / flash-latest) burn 30-50s of internal reasoning
    # on mechanical extraction tasks and hit 504 DEADLINE_EXCEEDED — a lite model
    # returns in ~2s with equal JSON quality for this workload.
    llm_extraction_model: str = Field(default="gemini-3.5-flash-lite")
    llm_temperature: float = Field(default=0.2)

    # --- Groq (primary for non-grounded text: Ask Puddy, extraction) ---
    # Separate quota from Google, high free-tier RPD on open models. Grounded
    # features stay on Gemini (Groq has no Google Search grounding).
    # gpt-oss-20b: fast, production-tier, not on Groq's deprecation list.
    groq_model: str = Field(default="openai/gpt-oss-20b")

    # Grounded company research (About Company, Top Asked). Google Search
    # grounding draws from a SEPARATE tool quota (~1.5K RPD), so lite models
    # now work here too — 500 RPD vs the old 2.5-flash 20 RPD.
    llm_grounding_model: str = Field(default="gemini-3.5-flash-lite")

    # --- Retrieval ---
    dense_weight: float = Field(default=0.5)
    bm25_weight: float = Field(default=0.5)
    retrieval_top_k: int = Field(default=20)
    rerank_top_k: int = Field(default=5)

    # --- Chunking (doc-type-aware) ---
    chunk_size_interview: int = Field(default=512)
    chunk_overlap_interview: int = Field(default=64)
    chunk_size_jd: int = Field(default=768)
    chunk_overlap_jd: int = Field(default=128)
    chunk_size_aptitude: int = Field(default=1024)
    chunk_overlap_aptitude: int = Field(default=128)

    # --- Server ---
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000)
    frontend_url: str = Field(default="http://localhost:5173")

    # --- Data ---
    data_dir: str = Field(default="./data")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def get_chunk_config(self, doc_type: str) -> dict:
        """Return chunk_size and chunk_overlap for a given doc type."""
        configs = {
            "interview_experience": {
                "chunk_size": self.chunk_size_interview,
                "chunk_overlap": self.chunk_overlap_interview,
            },
            "job_description": {
                "chunk_size": self.chunk_size_jd,
                "chunk_overlap": self.chunk_overlap_jd,
            },
            "aptitude_material": {
                "chunk_size": self.chunk_size_aptitude,
                "chunk_overlap": self.chunk_overlap_aptitude,
            },
        }
        return configs.get(doc_type, {
            "chunk_size": self.chunk_size_interview,
            "chunk_overlap": self.chunk_overlap_interview,
        })

    @property
    def json_store_path(self) -> Path:
        return Path(self.json_store_dir)

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)


# Singleton settings instance
settings = Settings()
