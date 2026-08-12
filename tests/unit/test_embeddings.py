from unittest.mock import AsyncMock, patch

import httpx
import pytest

from orchestrator.context.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    FallbackEmbedder,
    OllamaEmbedder,
    OpenAIEmbedder,
)

# Captured before any test patches httpx.AsyncClient, so the mocked
# transport can construct a *real* client instead of recursing into the mock.
_RealAsyncClient = httpx.AsyncClient


class _FakeSuccess(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _FakeFailure(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("boom")


async def test_fallback_uses_primary_when_it_succeeds():
    embedder = FallbackEmbedder(primary=_FakeSuccess(), fallback=_FakeFailure())
    result = await embedder.embed(["hello"])
    assert result == [[1.0, 0.0]]


async def test_fallback_switches_to_secondary_on_primary_failure():
    embedder = FallbackEmbedder(primary=_FakeFailure(), fallback=_FakeSuccess())
    result = await embedder.embed(["hello"])
    assert result == [[1.0, 0.0]]


async def test_fallback_propagates_when_both_fail():
    embedder = FallbackEmbedder(primary=_FakeFailure(), fallback=_FakeFailure())
    with pytest.raises(EmbeddingError):
        await embedder.embed(["hello"])


async def test_ollama_embedder_calls_api_per_text():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        calls.append(body)
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    transport = httpx.MockTransport(handler)
    embedder = OllamaEmbedder(base_url="http://fake-ollama", model="nomic-embed-text")

    with patch("httpx.AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=transport, **kw)):
        result = await embedder.embed(["one", "two"])

    assert result == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert len(calls) == 2


async def test_ollama_embedder_raises_embedding_error_on_http_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not found"})

    transport = httpx.MockTransport(handler)
    embedder = OllamaEmbedder(base_url="http://fake-ollama", model="missing-model")

    with (
        patch("httpx.AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=transport, **kw)),
        pytest.raises(EmbeddingError),
    ):
        await embedder.embed(["hello"])


async def test_openai_embedder_uses_configured_dimensions():
    fake_response = AsyncMock()
    fake_response.data = [{"embedding": [0.5, 0.5]}]

    with patch("litellm.aembedding", AsyncMock(return_value=fake_response)) as mock_call:
        embedder = OpenAIEmbedder(model="text-embedding-3-small", dimensions=768)
        result = await embedder.embed(["hello"])

    assert result == [[0.5, 0.5]]
    mock_call.assert_awaited_once_with(model="text-embedding-3-small", input=["hello"], dimensions=768)


async def test_openai_embedder_wraps_failures():
    with patch("litellm.aembedding", AsyncMock(side_effect=RuntimeError("rate limited"))):
        embedder = OpenAIEmbedder(model="text-embedding-3-small", dimensions=768)
        with pytest.raises(EmbeddingError):
            await embedder.embed(["hello"])
