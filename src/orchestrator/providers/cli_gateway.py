"""Fallback gateway for models only reachable through a CLI (no HTTP API).

Gap fix vs. architecture doc §13: the doc never specifies how the orchestrator
talks to a CLI subprocess. This defines a small JSON envelope protocol:

Request (written to the subprocess's stdin as a single line of JSON)::

    {"model": str, "messages": [...], "temperature": float | null,
     "response_format": {...} | null}

Response (the subprocess's *last* stdout line must be exactly one JSON
object; anything else on stdout is ignored, so progress/log output should go
to stderr instead)::

    {"content": str, "input_tokens": int | null, "output_tokens": int | null,
     "cost_usd": float | null, "error": str | null}

Exit code 0 with `error: null` is success. Any other combination (nonzero
exit, `error` set, malformed JSON, timeout) is a failure; stderr is captured
for diagnostics.
"""
import asyncio
import contextlib
import json
import time

from orchestrator.providers.base import GenerationResult, ModelGateway


class CLIExecutionError(RuntimeError):
    def __init__(self, message: str, *, stderr: str = "", exit_code: int | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


class CLIModelGateway(ModelGateway):
    """Invokes `commands[model]` as a subprocess implementing the envelope protocol."""

    def __init__(self, commands: dict[str, list[str]], *, timeout_seconds: float = 120.0) -> None:
        self.commands = commands
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> GenerationResult:
        if model not in self.commands:
            raise CLIExecutionError(f"No CLI command registered for model {model!r}")

        request = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "response_format": response_format,
            }
        )

        start = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *self.commands[model],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(request.encode()), timeout=self.timeout_seconds
            )
        except TimeoutError:
            process.kill()
            # Drain the pipes rather than just wait()ing, so a killed process
            # with already-buffered output doesn't leak pipe fds.
            with contextlib.suppress(Exception):
                await process.communicate()
            raise CLIExecutionError(
                f"CLI model {model!r} timed out after {self.timeout_seconds}s"
            ) from None

        latency_ms = int((time.monotonic() - start) * 1000)
        stderr_text = stderr.decode(errors="replace")

        last_line = next(
            (line for line in reversed(stdout.decode(errors="replace").splitlines()) if line.strip()),
            "",
        )
        try:
            envelope = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise CLIExecutionError(
                f"CLI model {model!r} produced no valid JSON envelope on stdout",
                stderr=stderr_text,
                exit_code=process.returncode,
            ) from exc

        if process.returncode != 0 or envelope.get("error"):
            raise CLIExecutionError(
                envelope.get("error") or f"CLI model {model!r} exited with code {process.returncode}",
                stderr=stderr_text,
                exit_code=process.returncode,
            )

        return GenerationResult(
            content=envelope.get("content", ""),
            input_tokens=envelope.get("input_tokens"),
            output_tokens=envelope.get("output_tokens"),
            cost_usd=envelope.get("cost_usd"),
            latency_ms=latency_ms,
            raw=envelope,
        )
