"""
Integration test for the /query endpoint.

Verifies SSE streaming, citation format, and basic error handling.
Mocks the retrieval and Ollama layers so no real model is needed.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_META = {
    "doc_id": "abc123",
    "chunk_id": "abc123_c0",
    "file_path": "docs/getting-started.md",
    "content_hash": "deadbeef",
    "embedding_model": "nomic-embed-text",
    "embedding_version": "1.0",
    "start_char": 0,
    "end_char": 100,
}

MOCK_CHUNK_TEXT = "Ask-Docs is a local AI-powered documentation assistant."

MOCK_SEARCH_RESULTS = [
    (MOCK_META, MOCK_CHUNK_TEXT, 0.85),
    (
        {**MOCK_META, "chunk_id": "abc123_c1", "start_char": 100, "end_char": 200},
        "It uses RAG to answer questions about your documents.",
        0.78,
    ),
]


class _FakeStreamResponse:
    """Simulates an httpx async streaming response for Ollama /api/generate."""
    status_code = 200

    async def aiter_lines(self):
        tokens = ["Ask-Docs ", "is ", "a ", "local ", "AI ", "assistant."]
        for token in tokens:
            yield json.dumps({"response": token, "done": False})
        yield json.dumps({"response": "", "done": True})

    def raise_for_status(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeAsyncClient:
    """Simulates httpx.AsyncClient with a streaming .stream() method."""
    def __init__(self, **kwargs):
        pass

    def stream(self, method, url, **kwargs):
        return _FakeStreamResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ── Tests ────────────────────────────────────────────────────────────────────


class TestQueryEndpoint:
    @patch("app.services.rag.search", return_value=MOCK_SEARCH_RESULTS)
    @patch("app.services.rag.httpx.AsyncClient", new=_FakeAsyncClient)
    def test_streaming_response_with_citations(self, mock_search, client):
        """Test that /query returns SSE stream with citations and tokens."""

        response = client.post(
            "/query",
            json={"question": "What is Ask-Docs?", "top_k": 3},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "X-Request-ID" in response.headers

        # Parse SSE events
        body = response.text
        events: list[tuple[str, str]] = []
        current_event = ""
        for line in body.split("\n"):
            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                events.append((current_event, line[6:]))

        # Should have citations
        citation_events = [e for e in events if e[0] == "citation"]
        assert len(citation_events) >= 2

        # Verify citation format
        for _, data in citation_events:
            cit = json.loads(data)
            assert "doc_id" in cit
            assert "chunk_id" in cit
            assert "file_path" in cit
            assert "score" in cit
            assert "snippet" in cit

        # Should have token events
        token_events = [e for e in events if e[0] == "token"]
        assert len(token_events) > 0

        # Should have a done event
        done_events = [e for e in events if e[0] == "done"]
        assert len(done_events) == 1

    def test_empty_question_returns_422(self, client):
        """Test that empty question returns validation error."""
        response = client.post(
            "/query",
            json={"question": "", "top_k": 3},
        )
        assert response.status_code == 422

    def test_top_k_too_high_is_capped(self, client):
        """Test that top_k exceeding the cap is rejected."""
        response = client.post(
            "/query",
            json={"question": "test", "top_k": 100},
        )
        # top_k > 20 should be rejected by pydantic validation
        assert response.status_code == 422

    @patch("app.services.rag.search", return_value=[])
    def test_abstention_when_no_results(self, mock_search, client):
        """Test that the system abstains when no retrieval results."""
        response = client.post(
            "/query",
            json={"question": "Something completely unrelated?", "top_k": 3},
        )
        assert response.status_code == 200

        body = response.text
        # Should contain abstention
        assert "don't have enough information" in body.lower() or "abstain" in body.lower()


class TestHealthEndpoints:
    def test_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readyz(self, client):
        response = client.get("/readyz")
        assert response.status_code == 200
        assert "ready" in response.json()
