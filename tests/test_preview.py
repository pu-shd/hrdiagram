"""macOS zsh launcher checks; Docker reports them as skipped when zsh is absent."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="Requires macOS/zsh launcher")


def launcher(tmp_path, port):
    docker = tmp_path / "docker-compose"
    marker = tmp_path / "docker-called"
    docker.write_text('#!/bin/sh\nprintf "%s" "$HRDIAGRAM_PORT" > "$PREVIEW_MARKER"\n')
    docker.chmod(0o755)
    env = {**os.environ, "HRDIAGRAM_PORT": port, "PREVIEW_MARKER": str(marker)}
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["zsh", str(ROOT / "scripts/run.sh")], env=env, text=True, capture_output=True
    )
    return result, marker


def test_preview_uses_configured_port(tmp_path):
    result, marker = launcher(tmp_path, "8090")
    assert result.returncode == 0, result.stderr
    assert "http://localhost:8090" in result.stdout
    assert marker.read_text() == "8090"


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_preview_rejects_invalid_port_before_starting_docker(tmp_path, port):
    result, marker = launcher(tmp_path, port)
    assert result.returncode != 0
    assert "HRDIAGRAM_PORT" in result.stderr
    assert not marker.exists()
