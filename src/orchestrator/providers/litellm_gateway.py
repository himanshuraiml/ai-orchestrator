import time

import litellm

from orchestrator.providers.base import GenerationResult, ModelGateway


class LiteLLMGateway(ModelGateway):
    """Routes to OpenAI/Anthropic/Google (and anything else LiteLLM supports)."""

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

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            response_format=response_format,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)

        try:
            cost_usd = litellm.completion_cost(completion_response=response)
        except Exception:  # noqa: BLE001 — unpriced/unknown models must not fail the request
            cost_usd = None

        return GenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )
