from pathlib import Path

from orchestrator.config.settings import get_settings
from orchestrator.security.sandbox import resolve_within
from orchestrator.tools.adapters.base import ToolAdapter


class UnsupportedOperationError(ValueError):
    pass


class FilesystemAdapter(ToolAdapter):
    """Read/write restricted to a workspace root — tasks.md 2.3.4. In-process
    (no MCP hop — arch doc's folder tree lists this straight under
    tools/adapters/, with no matching tools/mcp/ server).
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(get_settings().artifact_root)

    async def invoke(self, arguments: dict) -> dict:
        operation = arguments["operation"]
        path = resolve_within(self.root, arguments["path"])

        if operation == "read":
            return {"content": path.read_text()}

        if operation == "write":
            content = arguments["content"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return {"bytes_written": len(content.encode())}

        if operation == "list":
            return {"entries": sorted(p.name for p in path.iterdir())}

        raise UnsupportedOperationError(f"Unsupported filesystem operation: {operation!r}")
