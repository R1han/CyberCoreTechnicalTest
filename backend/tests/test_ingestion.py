"""
Unit tests for chunking and ingestion.
"""
from pathlib import Path
import tempfile
import os

import pytest

from app.services.ingestion import (
    chunk_text,
    clean_text,
    discover_files,
    ingest_file,
    _should_ignore,
)


# ── chunk_text ───────────────────────────────────────────────────────────────

class TestChunkText:
    def test_short_text_single_chunk(self):
        text = "Hello world, this is a short text."
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0][0] == text
        assert chunks[0][1] == 0
        assert chunks[0][2] == len(text)

    def test_overlap_produces_more_chunks(self):
        text = "A" * 200
        no_overlap = chunk_text(text, chunk_size=100, overlap=0)
        with_overlap = chunk_text(text, chunk_size=100, overlap=50)
        assert len(with_overlap) > len(no_overlap)

    def test_chunks_cover_full_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        # Verify all original content is covered
        covered = set()
        for _, start, end in chunks:
            covered.update(range(start, end))
        assert len(covered) >= len(text) - 1 

    def test_empty_text_returns_empty(self):
        assert chunk_text("", chunk_size=100, overlap=10) == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n\n  ", chunk_size=100, overlap=10) == []

    def test_chunk_size_respected(self):
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        for chunk_text_str, _, _ in chunks:
            assert len(chunk_text_str) <= 200


# ── clean_text ───────────────────────────────────────────────────────────────

class TestCleanText:
    def test_normalizes_crlf(self):
        assert "\n" in clean_text("hello\r\nworld")
        assert "\r" not in clean_text("hello\r\nworld")

    def test_collapses_multiple_newlines(self):
        result = clean_text("hello\n\n\n\n\nworld")
        assert result == "hello\n\nworld"

    def test_collapses_multiple_spaces(self):
        result = clean_text("hello    world")
        assert result == "hello world"

    def test_strips_text(self):
        result = clean_text("  hello  ")
        assert result == "hello"


# ── _should_ignore ───────────────────────────────────────────────────────────

class TestShouldIgnore:
    def test_ignores_env_file(self):
        assert _should_ignore(Path(".env"))

    def test_ignores_node_modules(self):
        assert _should_ignore(Path("node_modules/package.json"))

    def test_ignores_git(self):
        assert _should_ignore(Path(".git/config"))

    def test_ignores_binary(self):
        assert _should_ignore(Path("model.bin"))

    def test_allows_markdown(self):
        assert not _should_ignore(Path("docs/readme.md"))

    def test_allows_txt(self):
        assert not _should_ignore(Path("notes.txt"))


# ── discover_files / ingest_file ─────────────────────────────────────────────

class TestDiscoverAndIngest:
    def test_discover_finds_md_files(self, tmp_path: Path):
        (tmp_path / "test.md").write_text("# Hello\nWorld")
        (tmp_path / "test.py").write_text("print('hi')") 
        files = discover_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].suffix == ".md"

    def test_discover_skips_ignored(self, tmp_path: Path):
        (tmp_path / ".env").write_text("SECRET=123")
        files = discover_files(str(tmp_path))
        assert len(files) == 0

    def test_ingest_file_produces_chunks(self, tmp_path: Path):
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\n" + "Some content. " * 100)
        results = ingest_file(md)
        assert len(results) > 0
        for chunk_text_str, meta in results:
            assert len(chunk_text_str) > 0
            assert meta.doc_id
            assert meta.chunk_id
            assert meta.file_path == str(md)
            assert meta.content_hash

    def test_ingest_empty_file_returns_empty(self, tmp_path: Path):
        md = tmp_path / "empty.md"
        md.write_text("")
        results = ingest_file(md)
        assert len(results) == 0

    def test_ingest_html_file(self, tmp_path: Path):
        html = tmp_path / "page.html"
        html.write_text("<html><body><h1>Title</h1><p>Content here</p></body></html>")
        results = ingest_file(html)
        assert len(results) > 0
        for chunk_text_str, _ in results:
            assert "<script" not in chunk_text_str
