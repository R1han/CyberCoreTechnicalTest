"""
Ask-Docs Backend — Configuration
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Paths ────────────────────────────────────────────────────────────
    docs_dir: str = str(Path(__file__).resolve().parents[2] / "docs")
    index_dir: str = str(Path(__file__).resolve().parents[2] / "data" / "index")

    # ── Ollama (LLM + Embeddings) ─────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "mistral"          # Ollama model for generation
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768            # nomic-embed-text dimension

    # ── Retrieval / Chunking ─────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 5
    top_k_cap: int = 20
    similarity_threshold: float = 0.35  # below this → abstain

    # ── Reranker ─────────────────────────────────────────────────────────
    rerank_enabled: bool = True
    rerank_vector_weight: float = 0.4   # weight for vector similarity
    rerank_bm25_weight: float = 0.6     # weight for BM25 keyword score

    # ── Ingestion limits ─────────────────────────────────────────────────
    max_file_size_mb: int = 50
    max_chunks: int = 100_000

    # ── Rate limiting ────────────────────────────────────────────────────
    rate_limit_per_minute: int = 30

    # ── Server ───────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # ── Ignore patterns (ingestion) ──────────────────────────────────────
    ignore_patterns: list[str] = [
        ".env",
        "node_modules",
        ".git",
        "__pycache__",
        "*.pyc",
        "*.exe",
        "*.dll",
        "*.so",
        "*.bin",
        "*.iso",
        "*.tar",
        "*.gz",
        "*.zip",
    ]


settings = Settings()
