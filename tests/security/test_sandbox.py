import sys
from pathlib import Path

import pytest

from orchestrator.security.sandbox import (
    SandboxConfig,
    SandboxViolation,
    resolve_within,
    run_sandboxed,
)


async def test_run_sandboxed_captures_stdout():
    result = await run_sandboxed(
        [sys.executable, "-c", "print('hello sandbox')"],
        config=SandboxConfig(timeout_seconds=5),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "hello sandbox"
    assert not result.timed_out


async def test_run_sandboxed_enforces_timeout():
    result = await run_sandboxed(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        config=SandboxConfig(timeout_seconds=1),
    )

    assert result.timed_out
    assert result.returncode != 0


async def test_run_sandboxed_truncates_large_output():
    result = await run_sandboxed(
        [sys.executable, "-c", "print('x' * 1000)"],
        config=SandboxConfig(timeout_seconds=5, max_output_bytes=10),
    )

    assert result.truncated
    assert len(result.stdout) == 10


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt network denial is macOS-only")
async def test_run_sandboxed_denies_network_by_default():
    result = await run_sandboxed(
        [
            sys.executable,
            "-c",
            "import socket; socket.create_connection(('8.8.8.8', 53), timeout=3)",
        ],
        config=SandboxConfig(timeout_seconds=5, allow_network=False),
    )

    assert result.returncode != 0
    assert not result.timed_out


def test_resolve_within_allows_nested_path(tmp_path: Path):
    resolved = resolve_within(tmp_path, "sub/dir/file.txt")

    assert resolved == (tmp_path / "sub/dir/file.txt").resolve()


def test_resolve_within_rejects_path_traversal(tmp_path: Path):
    with pytest.raises(SandboxViolation):
        resolve_within(tmp_path, "../outside.txt")
