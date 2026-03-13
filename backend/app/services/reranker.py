"""
Ask-Docs — Reranker Service

Lightweight BM25 + vector-score fusion reranker.
Re-scores retrieved chunks by combining:
  1. Original vector similarity (from FAISS)
  2. BM25-style keyword relevance (term frequency / inverse document frequency)

No external dependencies — runs purely on Python stdlib + numpy.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from app.config import settings
from app.utils.logger import get_logger, timing_span

logger = get_logger(__name__)

# ── Tokeniser (simple whitespace + punctuation split) ────────────────────────

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric."""
    return _TOKEN_RE.findall(text.lower())


# ── BM25 scoring ────────────────────────────────────────────────────────────

# Standard BM25 hyperparameters
_K1 = 1.5
_B = 0.75


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    avg_doc_len: float,
    doc_freqs: dict[str, int],
    n_docs: int,
) -> float:
    """Compute BM25 score for a single document against the query."""
    tf = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    score = 0.0

    for qt in query_tokens:
        if qt not in tf:
            continue
        # IDF with smoothing
        df = doc_freqs.get(qt, 0)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        # TF saturation
        freq = tf[qt]
        tf_norm = (freq * (_K1 + 1)) / (
            freq + _K1 * (1 - _B + _B * doc_len / max(avg_doc_len, 1))
        )
        score += idf * tf_norm

    return score


# ── Public API ───────────────────────────────────────────────────────────────


def rerank(
    query: str,
    results: list[tuple[dict, str, float]],
    vector_weight: float = settings.rerank_vector_weight,
    bm25_weight: float = settings.rerank_bm25_weight,
) -> list[tuple[dict, str, float]]:
    """
    Rerank retrieval results using BM25 + vector score fusion.

    Args:
        query: The user question.
        results: List of (meta_dict, chunk_text, vector_score) from FAISS.
        vector_weight: Weight for the normalised vector similarity score.
        bm25_weight: Weight for the normalised BM25 score.

    Returns:
        Same shape as input, re-sorted by fused score (descending).
    """
    if not results or len(results) <= 1:
        return results

    with timing_span(logger, "rerank", count=len(results)):
        query_tokens = _tokenize(query)
        if not query_tokens:
            return results

        # Tokenise all docs
        doc_token_lists = [_tokenize(text) for _, text, _ in results]

        # Build document-frequency map across the retrieved set
        doc_freqs: dict[str, int] = {}
        for tokens in doc_token_lists:
            for t in set(tokens):
                doc_freqs[t] = doc_freqs.get(t, 0) + 1

        n_docs = len(results)
        avg_doc_len = sum(len(t) for t in doc_token_lists) / n_docs

        # Compute BM25 scores
        bm25_scores = [
            _bm25_score(query_tokens, doc_tokens, avg_doc_len, doc_freqs, n_docs)
            for doc_tokens in doc_token_lists
        ]

        # Normalise both score lists to [0, 1]
        vec_scores = [r[2] for r in results]
        vec_min, vec_max = min(vec_scores), max(vec_scores)
        vec_range = vec_max - vec_min if vec_max != vec_min else 1.0

        bm25_min, bm25_max = min(bm25_scores), max(bm25_scores)
        bm25_range = bm25_max - bm25_min if bm25_max != bm25_min else 1.0

        # Fuse
        fused: list[tuple[dict, str, float]] = []
        for i, (meta, text, vec_score) in enumerate(results):
            norm_vec = (vec_score - vec_min) / vec_range
            norm_bm25 = (bm25_scores[i] - bm25_min) / bm25_range
            combined = vector_weight * norm_vec + bm25_weight * norm_bm25
            fused.append((meta, text, round(combined, 4)))

        # Sort descending by fused score
        fused.sort(key=lambda x: x[2], reverse=True)

        logger.info(
            "reranking complete",
            extra={
                "count": len(fused),
                "top_fused_score": fused[0][2] if fused else 0,
            },
        )

    return fused
