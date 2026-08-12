from orchestrator.tools.adapters.base import ToolAdapter
from orchestrator.tools.mcp_client import MCPToolClient


class OCRAdapter(ToolAdapter):
    """Scanned PDF/image → text pipeline — tasks.md 2.3.2. Delegates to
    the `ocr` MCP server (tools/mcp/ocr/server.py): PyMuPDF text-layer
    extraction with a PaddleOCR fallback for scanned pages.
    """

    def __init__(self, client: MCPToolClient | None = None) -> None:
        self.client = client or MCPToolClient()

    async def invoke(self, arguments: dict) -> dict:
        return await self.client.call_tool("ocr", "extract_text", arguments)
