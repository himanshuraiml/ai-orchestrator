from orchestrator.tools.adapters.base import ToolAdapter
from orchestrator.tools.mcp_client import MCPToolClient


class PythonAdapter(ToolAdapter):
    """Sandboxed Python execution — tasks.md 2.3.1. Delegates to the
    `python` MCP server (tools/mcp/python/server.py), which runs the code
    in a resource-limited subprocess (security/sandbox.py).
    """

    def __init__(self, client: MCPToolClient | None = None) -> None:
        self.client = client or MCPToolClient()

    async def invoke(self, arguments: dict) -> dict:
        return await self.client.call_tool("python", "execute", arguments)
