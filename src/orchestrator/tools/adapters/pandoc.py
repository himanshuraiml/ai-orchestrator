from orchestrator.tools.adapters.base import ToolAdapter
from orchestrator.tools.mcp_client import MCPToolClient


class PandocAdapter(ToolAdapter):
    """Document conversion — tasks.md 2.3.3. Delegates to the `documents`
    MCP server (tools/mcp/documents/server.py), which shells out to Pandoc.
    """

    def __init__(self, client: MCPToolClient | None = None) -> None:
        self.client = client or MCPToolClient()

    async def invoke(self, arguments: dict) -> dict:
        return await self.client.call_tool("documents", "convert", arguments)
