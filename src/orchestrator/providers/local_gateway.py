import time

import httpx

from orchestrator.config.settings import get_settings
from orchestrator.providers.base import GenerationResult, ModelGateway


def _managed_models() -> tuple[str, str]:
    # The two local models this deployment is allowed to run. On a 16GB Mac
    # they cannot both be resident at once, so LocalGateway evicts the other
    # before loading the requested one. See tasks.md Phase 0.7 / 1.4.3.
    settings = get_settings()
    return (settings.ollama_coding_model, settings.ollama_general_model)


class LocalGateway(ModelGateway):
    """Routes to a local Ollama server. Only one managed local model may be
    resident at a time (16GB RAM constraint), so this evicts the other
    managed model before loading the requested one."""

    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url or get_settings().ollama_base_url
        self._client = client

    def _http(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def _running_models(self, client: httpx.AsyncClient) -> set[str]:
        response = await client.get("/api/ps")
        response.raise_for_status()
        return {m["name"] for m in response.json().get("models", [])}

    async def _evict_other_managed_models(self, client: httpx.AsyncClient, keep: str) -> None:
        running = await self._running_models(client)
        for other in _managed_models():
            if other != keep and other in running:
                await client.post("/api/generate", json={"model": other, "keep_alive": 0})

    async def generate(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> GenerationResult:
        start = time.monotonic()

        client = self._http()
        try:
            await self._evict_other_managed_models(client, keep=model)

            payload: dict = {"model": model, "messages": messages, "stream": False}
            if temperature is not None:
                payload["options"] = {"temperature": temperature}
            if response_format is not None and response_format.get("type") == "json_object":
                payload["format"] = "json"

            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        finally:
            if self._client is None:
                await client.aclose()

        latency_ms = int((time.monotonic() - start) * 1000)

        return GenerationResult(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            cost_usd=0.0,
            latency_ms=latency_ms,
            raw=data,
        )
