"""Sandbox policy enforcement — arch doc §26 / tasks.md 2.3.6.

Two things live here:

- `run_sandboxed`: subprocess execution with CPU/memory/process limits
  (via `resource`), a wall-clock timeout, output-size truncation, and — on
  macOS, where `sandbox-exec` is available — a Seatbelt profile that denies
  network access and restricts writes to the sandbox workdir. This is a
  best-effort, single-user sandbox appropriate for a personal deployment; it
  is not a hardened multi-tenant boundary (arch doc's "ephemeral container"
  is the production-grade version, deferred — no Docker socket needed here).
- `resolve_within`: path-containment check for adapters that restrict
  filesystem access to a root directory (e.g. the filesystem adapter).
  Defends against `..`/symlink traversal for a trusted single local user;
  it is not TOCTOU-safe against an adversarial concurrent writer.
"""

import asyncio
import contextlib
import os
import resource
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class SandboxViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxConfig:
    cpu_seconds: int = 30
    memory_mb: int = 512
    timeout_seconds: float = 30.0
    max_output_bytes: int = 1_000_000
    allow_network: bool = False
    max_processes: int = 32


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    truncated: bool


def _limit_resources(config: SandboxConfig) -> Callable[[], None]:
    def _apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (config.cpu_seconds, config.cpu_seconds))
        # RLIMIT_AS caps total virtual memory. macOS's kernel rejects finite
        # RLIMIT_AS values outright (EINVAL) regardless of the number
        # requested, so this is Linux-only in practice; skip it where the
        # platform refuses rather than crash the whole sandboxed call.
        mem_bytes = config.memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass
        resource.setrlimit(resource.RLIMIT_NPROC, (config.max_processes, config.max_processes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return _apply


_SEATBELT_PROFILE = """(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow file-read*)
(allow file-write* (subpath "{workdir}"))
(allow file-write* (subpath "/private/tmp"))
(allow file-write* (subpath "/tmp"))
(allow sysctl-read)
(allow mach-lookup)
{network_clause}
"""


def _wrap_with_macos_sandbox(argv: list[str], workdir: Path, *, allow_network: bool) -> list[str]:
    sandbox_exec = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or not sandbox_exec:
        return argv

    network_clause = "(allow network*)" if allow_network else "(deny network*)"
    profile = _SEATBELT_PROFILE.format(workdir=workdir, network_clause=network_clause)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sb", delete=False, dir=str(workdir)
    ) as profile_file:
        profile_file.write(profile)

    return [sandbox_exec, "-f", profile_file.name, *argv]


async def run_sandboxed(
    argv: list[str],
    *,
    config: SandboxConfig | None = None,
    input_text: str | None = None,
    cwd: Path | None = None,
) -> SandboxResult:
    config = config or SandboxConfig()
    workdir = cwd or Path(tempfile.mkdtemp(prefix="orch-sandbox-"))
    workdir.mkdir(parents=True, exist_ok=True)

    command = _wrap_with_macos_sandbox(argv, workdir, allow_network=config.allow_network)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workdir),
        preexec_fn=_limit_resources(config),
    )

    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input_text.encode() if input_text is not None else None),
            timeout=config.timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        # Drain the pipes rather than just wait()ing — the killed process may
        # have already buffered output the OS pipe hasn't delivered yet, and
        # leaving it unread leaks the pipe fds.
        with contextlib.suppress(Exception):
            await process.communicate()
        stdout, stderr = b"", f"sandboxed process timed out after {config.timeout_seconds}s".encode()
        timed_out = True

    truncated = len(stdout) > config.max_output_bytes
    stdout = stdout[: config.max_output_bytes]

    return SandboxResult(
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        returncode=process.returncode if process.returncode is not None else -1,
        timed_out=timed_out,
        truncated=truncated,
    )


def resolve_within(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()

    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        raise SandboxViolation(
            f"Path {relative_path!r} escapes sandbox root {resolved_root}"
        ) from None

    return candidate
