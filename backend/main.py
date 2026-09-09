"""
PIA — Placement Intelligence Assistant
FastAPI Application Entry Point

Configures CORS, registers routes, and manages application lifecycle.
"""

import os
import sys

# Configure environment variables for Vercel serverless environment
if os.environ.get("VERCEL"):
    os.environ["HOME"] = "/tmp"
    os.environ["HF_HOME"] = "/tmp/hf_home"

# Add parent directory to sys.path to allow "backend.xxx" imports when running inside backend/ root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.config import settings
from backend.api.routes import router
from backend.auth.routes import router as auth_router
from backend.middleware.rate_limit import RateLimitMiddleware


# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
if not os.environ.get("VERCEL"):
    logger.add(
        "logs/pia_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown events."""
    # --- Startup ---
    logger.info("=" * 60)
    logger.info("PIA — Placement Intelligence Assistant")
    logger.info("=" * 60)
    logger.info(f"LLM Model: {settings.llm_model}")
    logger.info(f"Embedding Model: {settings.embedding_model}")
    logger.info(f"Reranker Model: {settings.reranker_model}")
    logger.info(f"MongoDB DB: {settings.mongodb_db_name}")
    logger.info(f"MongoDB Vector Collection: {settings.mongodb_vector_collection}")
    logger.info(f"Data Directory: {settings.data_dir}")

    # Pre-initialize vector store (loads embedding model)
    try:
        from backend.db.vector_store import vector_store
        vector_store.initialize()
        logger.info(f"Vector store initialized: {vector_store.get_stats()}")
    except Exception as e:
        logger.warning(f"Vector store initialization deferred: {e}")

    yield

    # --- Shutdown ---
    logger.info("PIA shutting down...")


# Create FastAPI app
app = FastAPI(
    title="PIA — Placement Intelligence Assistant",
    description=(
        "AI-powered placement preparation platform with hybrid RAG pipeline. "
        "Analyze JDs, retrieve interview experiences, and get cited answers."
    ),
    version="1.0.0",
    lifespan=lifespan if not os.environ.get("VERCEL") else None,
)

# Rate limiter — added BEFORE CORS so CORS stays the outermost middleware; that
# way a 429 response still carries CORS headers and the browser can read it.
app.add_middleware(RateLimitMiddleware)

# CORS — allow frontend dev server, custom domain, and Vercel domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "https://puddy.krupakara.space",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"https://.*\.(vercel\.app|krupakara\.space)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router)
app.include_router(auth_router)


from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    import traceback
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"}
    )


# Health check
@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "PIA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )
