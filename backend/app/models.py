"""
Ask-Docs Backend — Pydantic models / schemas
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request / Response ───────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    docs_dir: str | None = Field(None, description="Override docs directory")


class IndexResponse(BaseModel):
    status: str
    documents_processed: int
    chunks_created: int
    elapsed_seconds: float


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)


class Citation(BaseModel):
    doc_id: str
    chunk_id: str
    file_path: str
    score: float
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    abstained: bool = False
    token_count: int = 0


# ── Internal ─────────────────────────────────────────────────────────────────

class ChunkMeta(BaseModel):
    doc_id: str
    chunk_id: str
    file_path: str
    content_hash: str
    embedding_model: str
    embedding_version: str = "1.0"
    start_char: int = 0
    end_char: int = 0


class SSEEvent(BaseModel):
    """Wrapper for a single SSE data frame."""
    event: str = "token"          # token | citation | done | error
    data: str
