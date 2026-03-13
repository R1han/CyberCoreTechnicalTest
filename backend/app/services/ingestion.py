"""
Ask-Docs — Document Ingestion Service

Reads .md, .pdf, .txt, .html, .xlsx from the docs directory,
cleans text, and produces chunks for embedding.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import uuid
from pathlib import Path

from app.config import settings
from app.models import ChunkMeta
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Supported loaders ────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".md", ".pdf", ".txt", ".html", ".htm", ".xlsx"}


def _should_ignore(path: Path) -> bool:
    """Return True if file matches any ignore pattern."""
    rel = str(path)
    for pat in settings.ignore_patterns:
        if fnmatch.fnmatch(path.name, pat) or fnmatch.fnmatch(rel, f"*{pat}*"):
            return True
    return False


def _read_text(path: Path) -> str:
    """Extract text content from a file based on its extension."""
    ext = path.suffix.lower()

    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")

    if ext in {".html", ".htm"}:
        from bs4 import BeautifulSoup

        raw = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")
        # remove script/style
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    if ext == ".pdf":
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)

    if ext == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        rows: list[str] = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                rows.append(" | ".join(cells))
        wb.close()
        return "\n".join(rows)

    return ""


# ── Cleaning ─────────────────────────────────────────────────────────────────

_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_text(text: str) -> str:
    """Normalize whitespace and strip control characters."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_NEWLINE.sub("\n\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


# ── Chunking ─────────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size,
    overlap: int = settings.chunk_overlap,
) -> list[tuple[str, int, int]]:
    """
    Split *text* into overlapping chunks.
    Returns list of (chunk_text, start_char, end_char).
    """
    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        if chunk.strip():
            chunks.append((chunk.strip(), start, end))
        start += chunk_size - overlap
    return chunks


# ── Public API ───────────────────────────────────────────────────────────────


def discover_files(docs_dir: str | None = None) -> list[Path]:
    """Walk *docs_dir* and return supported, non-ignored file paths."""
    root = Path(docs_dir or settings.docs_dir)
    if not root.exists():
        logger.warning("docs_dir does not exist", extra={"docs_dir": str(root)})
        return []

    files: list[Path] = []
    max_size = settings.max_file_size_mb * 1024 * 1024
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if _should_ignore(p):
            logger.debug("ignoring file", extra={"path": str(p)})
            continue
        if p.stat().st_size > max_size:
            logger.warning(
                "file exceeds max size, skipping",
                extra={"path": str(p), "size_mb": p.stat().st_size / 1024 / 1024},
            )
            continue
        files.append(p)
    return files


def ingest_file(path: Path) -> list[tuple[str, ChunkMeta]]:
    """
    Read, clean, chunk a single file and return (chunk_text, meta) pairs.
    """
    text = _read_text(path)
    if not text.strip():
        return []

    text = clean_text(text)
    doc_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

    results: list[tuple[str, ChunkMeta]] = []
    for idx, (chunk, start, end) in enumerate(chunk_text(text)):
        chunk_id = f"{doc_id}_c{idx}"
        meta = ChunkMeta(
            doc_id=doc_id,
            chunk_id=chunk_id,
            file_path=str(path),
            content_hash=content_hash,
            embedding_model=settings.embedding_model,
            start_char=start,
            end_char=end,
        )
        results.append((chunk, meta))

    return results


def ingest_all(docs_dir: str | None = None) -> list[tuple[str, ChunkMeta]]:
    """Ingest every supported file in docs_dir and return all chunks + meta."""
    files = discover_files(docs_dir)
    logger.info("discovered files for ingestion", extra={"count": len(files)})

    all_chunks: list[tuple[str, ChunkMeta]] = []
    for f in files:
        try:
            chunks = ingest_file(f)
            all_chunks.extend(chunks)
            logger.info(
                "ingested file",
                extra={"path": str(f), "chunks": len(chunks)},
            )
        except Exception:
            logger.exception("error ingesting file", extra={"path": str(f)})

    if len(all_chunks) > settings.max_chunks:
        logger.warning(
            "chunk count exceeds max_chunks; truncating",
            extra={"total": len(all_chunks), "max": settings.max_chunks},
        )
        all_chunks = all_chunks[: settings.max_chunks]

    return all_chunks
