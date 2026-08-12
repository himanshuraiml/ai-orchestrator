"""Pandoc document-conversion MCP server — arch doc §24 / tasks.md 2.2.4.

Shells out to the local `pandoc` binary (DOCX, MD, PDF, HTML, ...). Not
LibreOffice — arch doc explicitly drops it to keep the image small; Pandoc
covers the conversions this project needs.
"""

import asyncio
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("documents")

_TIMEOUT_SECONDS = 60.0


@mcp.tool()
async def convert(input_path: str, output_path: str, to_format: str | None = None) -> dict:
    """Convert a document between formats via Pandoc."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    argv = ["pandoc", input_path, "-o", output_path]
    if to_format:
        argv += ["-t", to_format]

    process = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return {"success": False, "error": f"pandoc timed out after {_TIMEOUT_SECONDS}s"}

    if process.returncode != 0:
        return {"success": False, "error": stderr.decode(errors="replace")}

    size = Path(output_path).stat().st_size
    return {"success": True, "output_path": output_path, "bytes_written": size}


if __name__ == "__main__":
    mcp.run()
