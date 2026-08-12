"""Python execution MCP server — arch doc §26 / tasks.md 2.2.2.

Runs model-generated code as a subprocess sandboxed via
orchestrator.security.sandbox (CPU limit, memory limit best-effort, 30s
default timeout, no network). Never executes code in this server process
itself — the sandbox subprocess is the isolation boundary.
"""

import sys
import tempfile
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from orchestrator.security.sandbox import SandboxConfig, run_sandboxed

mcp = MCPServer("python-executor")


@mcp.tool()
async def execute(code: str, timeout_seconds: int = 30) -> dict:
    """Execute a Python snippet in a sandboxed subprocess; returns stdout/stderr."""
    workdir = Path(tempfile.mkdtemp(prefix="orch-py-"))
    script = workdir / "snippet.py"
    script.write_text(code)

    config = SandboxConfig(
        cpu_seconds=timeout_seconds,
        timeout_seconds=float(timeout_seconds),
        allow_network=False,
    )
    result = await run_sandboxed([sys.executable, str(script)], config=config, cwd=workdir)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "truncated": result.truncated,
    }


if __name__ == "__main__":
    mcp.run()
