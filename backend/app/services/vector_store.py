"""
Ask-Docs — Embedding Service (Ollama) + FAISS Vector Store

Uses Ollama's /api/embeddings endpoint for `nomic-embed-text`.
Stores vectors in FAISS and persists metadata as JSON alongside.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from functools import lru_cache

import faiss
import httpx
import numpy as np

from app.config import settings
from app.models import ChunkMeta
from app.utils.logger import get_logger, timing_span

logger = get_logger(__name__)

# ── Embedding via Ollama ─────────────────────────────────────────────────────

_embed_cache: dict[str, np.ndarray] = {}   # simple in-memory LRU-ish cache


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Get embeddings for a batch of texts via Ollama.
    Returns shape (n, embedding_dim) float32 array.
    """
    vectors: list[np.ndarray] = []
    with timing_span(logger, "embed_texts", count=len(texts)):
        for text in texts:
            cache_key = text[:256]  # use prefix as key to cap memory
            if cache_key in _embed_cache:
                vectors.append(_embed_cache[cache_key])
                continue

            resp = httpx.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
                timeout=60.0,
            )
            resp.raise_for_status()
            vec = np.array(resp.json()["embedding"], dtype=np.float32)
            _embed_cache[cache_key] = vec
            vectors.append(vec)

    return np.vstack(vectors)


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string. Returns shape (1, dim)."""
    return embed_texts([text])


# ── FAISS index management ───────────────────────────────────────────────────

_faiss_index: faiss.IndexFlatIP | None = None
_chunk_metadata: list[dict] = []
_chunk_texts: list[str] = []

INDEX_FILE = "index.faiss"
META_FILE = "metadata.json"
TEXTS_FILE = "texts.json"


def _index_dir() -> Path:
    p = Path(settings.index_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def build_index(chunks: list[tuple[str, ChunkMeta]]) -> int:
    """
    Build FAISS index from (chunk_text, meta) pairs and persist to disk.
    Returns number of vectors indexed.
    """
    global _faiss_index, _chunk_metadata, _chunk_texts

    if not chunks:
        logger.warning("no chunks to index")
        return 0

    texts = [c[0] for c in chunks]
    metas = [c[1].model_dump() for c in chunks]

    with timing_span(logger, "build_embeddings", count=len(texts)):
        # Batch in groups of 32 to avoid huge single requests
        all_vecs: list[np.ndarray] = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vecs = embed_texts(batch)
            all_vecs.append(vecs)
        vectors = np.vstack(all_vecs)

    # Normalize for cosine similarity via inner-product
    faiss.normalize_L2(vectors)

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    _faiss_index = index
    _chunk_metadata = metas
    _chunk_texts = texts

    # Persist
    out = _index_dir()
    with timing_span(logger, "persist_index"):
        faiss.write_index(index, str(out / INDEX_FILE))
        (out / META_FILE).write_text(json.dumps(metas, default=str))
        (out / TEXTS_FILE).write_text(json.dumps(texts))

    logger.info("index built", extra={"vectors": index.ntotal, "dim": dim})
    return index.ntotal


def load_index() -> bool:
    """Load persisted FAISS index + metadata from disk. Returns True if OK."""
    global _faiss_index, _chunk_metadata, _chunk_texts

    out = _index_dir()
    idx_path = out / INDEX_FILE
    meta_path = out / META_FILE
    texts_path = out / TEXTS_FILE

    if not idx_path.exists():
        logger.info("no persisted index found")
        return False

    _faiss_index = faiss.read_index(str(idx_path))
    _chunk_metadata = json.loads(meta_path.read_text())
    _chunk_texts = json.loads(texts_path.read_text()) if texts_path.exists() else []
    logger.info("index loaded from disk", extra={"vectors": _faiss_index.ntotal})
    return True


def search(query: str, top_k: int = settings.top_k) -> list[tuple[dict, str, float]]:
    """
    Search the FAISS index.
    Returns list of (meta_dict, chunk_text, score).
    """
    global _faiss_index, _chunk_metadata, _chunk_texts

    if _faiss_index is None or _faiss_index.ntotal == 0:
        load_index()
    if _faiss_index is None or _faiss_index.ntotal == 0:
        return []

    top_k = min(top_k, settings.top_k_cap, _faiss_index.ntotal)

    with timing_span(logger, "embed_query"):
        qvec = embed_query(query)
    faiss.normalize_L2(qvec)

    with timing_span(logger, "faiss_search", top_k=top_k):
        scores, indices = _faiss_index.search(qvec, top_k)

    results: list[tuple[dict, str, float]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        meta = _chunk_metadata[idx]
        text = _chunk_texts[idx] if idx < len(_chunk_texts) else ""
        results.append((meta, text, float(score)))

    return results
