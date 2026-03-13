"""
Ask-Docs — RAG Pipeline & LLM Generation (Ollama)

Handles retrieval → prompt building → streaming generation.
Uses Ollama for both embeddings and text generation.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from app.config import settings
from app.models import Citation
from app.services.vector_store import search
from app.services.reranker import rerank
from app.utils.logger import get_logger, timing_span
from app.utils.safety import redact_pii

logger = get_logger(__name__)


# ── Prompt construction ─────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a helpful documentation assistant. Answer the user's question "
    "using ONLY the provided context excerpts. Cite sources using [Source N] "
    "notation. If the context does not contain enough information to answer "
    "confidently, say \"I don't have enough information to answer this question.\""
)


def _build_prompt(question: str, contexts: list[tuple[dict, str, float]]) -> str:
    """Build a Mistral-style instruct prompt with retrieved context."""
    context_parts: list[str] = []
    for i, (meta, text, score) in enumerate(contexts, 1):
        source = meta.get("file_path", "unknown")
        context_parts.append(f"[Source {i}] (file: {source}, score: {score:.3f})\n{text}")

    context_block = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"<s>[INST] {SYSTEM_PROMPT}\n\n"
        f"### Context:\n{context_block}\n\n"
        f"### Question:\n{question}\n[/INST]"
    )
    return prompt


# ── Retrieval helpers ────────────────────────────────────────────────────────


def _build_citations(contexts: list[tuple[dict, str, float]]) -> list[Citation]:
    """Convert retrieval results to Citation objects."""
    citations: list[Citation] = []
    for meta, text, score in contexts:
        citations.append(
            Citation(
                doc_id=meta["doc_id"],
                chunk_id=meta["chunk_id"],
                file_path=meta["file_path"],
                score=round(score, 4),
                snippet=text[:300],
            )
        )
    return citations


# ── Semantic cache (simple dict) ─────────────────────────────────────────────
# In production, replace with Redis or a proper semantic cache.
_qa_cache: dict[str, tuple[str, list[Citation]]] = {}
_QA_CACHE_MAX = 256


# ── RAG pipeline ─────────────────────────────────────────────────────────────


def retrieve_and_check(
    question: str, top_k: int = settings.top_k
) -> tuple[list[tuple[dict, str, float]], bool]:
    """
    Retrieve contexts and decide whether to abstain.
    Returns (contexts, should_abstain).
    """
    with timing_span(logger, "retrieval"):
        results = search(question, top_k=top_k)

    if not results:
        return [], True

    # Rerank if enabled
    if settings.rerank_enabled:
        results = rerank(question, results)

    # Check if best score is below threshold
    best_score = max(r[2] for r in results)
    if best_score < settings.similarity_threshold:
        logger.info(
            "abstaining — low confidence",
            extra={"best_score": best_score, "threshold": settings.similarity_threshold},
        )
        return results, True

    return results, False


async def generate_streaming(
    question: str, top_k: int = settings.top_k
) -> AsyncGenerator[str, None]:
    """
    Full RAG pipeline: retrieve → build prompt → stream tokens as SSE.
    Yields SSE-formatted strings.
    """
    # Sanitise input
    question = redact_pii(question)

    # Check semantic cache
    cache_key = question.strip().lower()
    if cache_key in _qa_cache:
        answer, citations = _qa_cache[cache_key]
        for cit in citations:
            yield f"event: citation\ndata: {cit.model_dump_json()}\n\n"
        yield f"event: token\ndata: {json.dumps({'text': answer})}\n\n"
        yield f"event: done\ndata: {json.dumps({'token_count': len(answer.split())})}\n\n"
        return

    # Retrieve
    contexts, should_abstain = retrieve_and_check(question, top_k)

    if should_abstain:
        citations = _build_citations(contexts) if contexts else []
        for cit in citations:
            yield f"event: citation\ndata: {cit.model_dump_json()}\n\n"
        abstain_msg = (
            "I don't have enough information in the indexed documents to "
            "answer this question confidently."
        )
        yield f"event: token\ndata: {json.dumps({'text': abstain_msg})}\n\n"
        yield f"event: done\ndata: {json.dumps({'abstained': True, 'token_count': 0})}\n\n"
        return

    # Emit citations first
    citations = _build_citations(contexts)
    for cit in citations:
        yield f"event: citation\ndata: {cit.model_dump_json()}\n\n"

    # Build prompt & stream via Ollama
    prompt = _build_prompt(question, contexts)

    full_answer: list[str] = []
    token_count = 0

    with timing_span(logger, "generation"):
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.llm_model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": settings.llm_temperature,
                        "num_predict": settings.llm_max_tokens,
                    },
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    text = chunk.get("response", "")
                    if text:
                        full_answer.append(text)
                        token_count += 1
                        yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
                    if chunk.get("done", False):
                        break

    # Cache the result
    answer_text = "".join(full_answer)
    if len(_qa_cache) < _QA_CACHE_MAX:
        _qa_cache[cache_key] = (answer_text, citations)

    yield f"event: done\ndata: {json.dumps({'token_count': token_count})}\n\n"
