"""
Ask-Docs — API Routers: /index and /query
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models import IndexRequest, IndexResponse, QueryRequest
from app.services.ingestion import ingest_all
from app.services.vector_store import build_index
from app.services.rag import generate_streaming
from app.utils.logger import get_logger, timing_span, make_request_id
from app.utils.rate_limit import rate_limiter
from app.utils.safety import validate_question

logger = get_logger(__name__)

router = APIRouter()


# ── POST /index ──────────────────────────────────────────────────────────────

@router.post("/index", response_model=IndexResponse)
async def index_docs(body: IndexRequest, request: Request):
    """Ingest documents from the docs directory and build vector index."""
    request_id = make_request_id()
    start = time.perf_counter()

    logger.info("index request received", extra={"request_id": request_id})

    try:
        with timing_span(logger, "ingestion", request_id=request_id):
            chunks = ingest_all(body.docs_dir)

        with timing_span(logger, "index_build", request_id=request_id):
            vectors_count = build_index(chunks)

        elapsed = round(time.perf_counter() - start, 2)
        return IndexResponse(
            status="ok",
            documents_processed=len({c[1].doc_id for c in chunks}),
            chunks_created=len(chunks),
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        logger.exception("index failed", extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}")


# ── POST /query ──────────────────────────────────────────────────────────────

@router.post("/query")
async def query_docs(body: QueryRequest, request: Request):
    """
    RAG query — retrieves relevant chunks, generates answer,
    and streams tokens + citations via SSE.
    """
    request_id = make_request_id()

    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    # Validate
    err = validate_question(body.question)
    if err:
        raise HTTPException(status_code=422, detail=err)

    top_k = min(body.top_k, settings.top_k_cap)

    logger.info(
        "query received",
        extra={"request_id": request_id, "question": body.question[:100], "top_k": top_k},
    )

    async def event_stream():
        try:
            async for event in generate_streaming(body.question, top_k=top_k):
                yield event
        except Exception as exc:
            logger.exception("generation error", extra={"request_id": request_id})
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
        },
    )
