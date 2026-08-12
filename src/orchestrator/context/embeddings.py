"""Embedding providers — arch doc §27 / tasks.md 4.3.

Local `nomic-embed-text` via Ollama is the default (free, no API cost);
OpenAI `text-embedding-3-small` is the fallback when Ollama is unreachable
or the model hasn't been pulled (see tasks.md 0.7 — not pulled by default).
Both are requested at `settings.embedding_dimensions` (768, nomic's native
size) so they share one pgvector column — see db/models.py EMBEDDING_DIM.
"""

from abc import ABC, abstractmethod

import httpx
import litellm

from orchestrator.config.settings import get_settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OllamaEmbedder(EmbeddingProvider):
    """Ollama has no batch embeddings endpoint on the version this project
    targets, so texts are embedded one request at a time."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
            vectors = []
            for text in texts:
                try:
                    response = await client.post(
                        "/api/embeddings", json={"model": self.model, "prompt": text}
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise EmbeddingError(f"Ollama embedding call failed: {exc}") from exc

                embedding = response.json().get("embedding")
                if not embedding:
                    raise EmbeddingError(f"Ollama returned no embedding for model {self.model!r}")
                vectors.append(embedding)
            return vectors


class OpenAIEmbedder(EmbeddingProvider):
    def __init__(self, model: str | None = None, dimensions: int | None = None) -> None:
        settings = get_settings()
        self.model = model or settings.openai_embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await litellm.aembedding(
                model=self.model, input=texts, dimensions=self.dimensions
            )
        except Exception as exc:
            raise EmbeddingError(f"OpenAI embedding call failed: {exc}") from exc

        return [item["embedding"] for item in response.data]


class FallbackEmbedder(EmbeddingProvider):
    """Tries `primary`; falls back to `secondary` on failure — tasks.md 4.3
    ("Local ... Fallback: OpenAI")."""

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self.primary.embed(texts)
        except EmbeddingError:
            return await self.fallback.embed(texts)


def get_embedder() -> EmbeddingProvider:
    return FallbackEmbedder(OllamaEmbedder(), OpenAIEmbedder())
