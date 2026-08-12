import httpx

from orchestrator.config.settings import get_settings
from orchestrator.tools.adapters.base import ToolAdapter

_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class ToolConfigurationError(RuntimeError):
    pass


class BrowserAdapter(ToolAdapter):
    """Web search via httpx + the Brave Search API — tasks.md 2.3.5."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def invoke(self, arguments: dict) -> dict:
        settings = get_settings()
        if not settings.brave_search_api_key:
            raise ToolConfigurationError(
                "BRAVE_SEARCH_API_KEY is not configured; web_search is unavailable"
            )

        query = arguments["query"]
        count = arguments.get("count", 5)

        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.get(
                _SEARCH_URL,
                params={"q": query, "count": count},
                headers={
                    "X-Subscription-Token": settings.brave_search_api_key,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if self._client is None:
                await client.aclose()

        results = [
            {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")}
            for r in data.get("web", {}).get("results", [])
        ]
        return {"results": results}
