"""MCP tool discovery + invocation — arch doc §24 / tasks.md 2.2.1.

Treats MCP as the standardized tool boundary: each server in `tools/mcp/`
is a standalone stdio subprocess. This client is intentionally stateless —
it spawns the target server, does one request, and tears it down. That's
the right tradeoff for a personal, low-concurrency deployment; a pooled
per-server session would be the next step if call volume grows enough for
per-call spawn latency to matter.
"""

import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from orchestrator.config.settings import REPO_ROOT

MCP_SERVERS: dict[str, list[str]] = {
    "python": [sys.executable, str(REPO_ROOT / "tools/mcp/python/server.py")],
    "ocr": [sys.executable, str(REPO_ROOT / "tools/mcp/ocr/server.py")],
    "documents": [sys.executable, str(REPO_ROOT / "tools/mcp/documents/server.py")],
}


class MCPServerError(RuntimeError):
    pass


def _parse_content(item) -> dict:
    text = getattr(item, "text", None)
    if text is None:
        return {"text": str(item)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


class MCPToolClient:
    def __init__(self, servers: dict[str, list[str]] | None = None) -> None:
        self.servers = servers or MCP_SERVERS

    def _params(self, server: str) -> StdioServerParameters:
        if server not in self.servers:
            raise MCPServerError(f"Unknown MCP server {server!r}")
        command, *args = self.servers[server]
        # The MCP SDK inherits only a minimal env (HOME/PATH/etc) by default,
        # which strips LANG — tesseract/pandoc subprocesses then emit
        # non-UTF-8 output that fails to decode. These are trusted local
        # servers, not third-party ones, so full inheritance is safe here.
        return StdioServerParameters(command=command, args=args, env=dict(os.environ))

    async def list_tools(self, server: str) -> list[dict]:
        params = self._params(server)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
                for tool in result.tools
            ]

    async def call_tool(self, server: str, tool_name: str, arguments: dict) -> dict:
        params = self._params(server)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

            if result.is_error:
                detail = "; ".join(_parse_content(item).get("text", str(item)) for item in result.content)
                raise MCPServerError(f"MCP tool {server}.{tool_name} failed: {detail}")

            if result.structured_content is not None:
                return result.structured_content

            if result.content:
                return _parse_content(result.content[0])

            return {}
