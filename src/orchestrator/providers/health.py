from dataclasses import dataclass

import httpx

from orchestrator.config.settings import get_settings


@dataclass
class ProviderHealth:
    provider: str
    available: bool
    detail: str = ""


async def check_ollama() -> ProviderHealth:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=3.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
        return ProviderHealth("ollama", available=True)
    except Exception as exc:  # noqa: BLE001 — any failure means "not available", not a crash
        return ProviderHealth("ollama", available=False, detail=str(exc))


def _check_api_key(provider: str, api_key: str) -> ProviderHealth:
    # A liveness check here does not mean issuing a real (billed) request —
    # it means the credential this provider needs is configured.
    if api_key:
        return ProviderHealth(provider, available=True)
    return ProviderHealth(provider, available=False, detail="API key not configured")


async def check_openai() -> ProviderHealth:
    return _check_api_key("openai", get_settings().openai_api_key)


async def check_anthropic() -> ProviderHealth:
    return _check_api_key("anthropic", get_settings().anthropic_api_key)


async def check_google() -> ProviderHealth:
    return _check_api_key("google", get_settings().google_api_key)


async def check_all() -> dict[str, ProviderHealth]:
    checks = (await check_openai(), await check_anthropic(), await check_google(), await check_ollama())
    return {check.provider: check for check in checks}
