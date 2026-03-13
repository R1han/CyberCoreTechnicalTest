"""
Ask-Docs — FastAPI Application Entry Point
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.api import router as api_router
from app.services.vector_store import load_index
from app.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Ask-Docs API",
    description="Local-LLM RAG API for documentation Q&A",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request-ID + timing middleware ───────────────────────────────────────────

@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    start = time.perf_counter()

    response: Response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(elapsed_ms)

    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "path": str(request.url.path),
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    return response


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("starting Ask-Docs API")
    load_index()  # try to load persisted index


# ── Routes ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ── Health probes ────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness check — verifies index is loaded."""
    from app.services.vector_store import _faiss_index
    ready = _faiss_index is not None and _faiss_index.ntotal > 0
    return {"ready": ready}
