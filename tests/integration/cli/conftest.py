from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pytest


@dataclass(slots=True, frozen=True)
class CLIRun:
    returncode: int
    stdout: str
    stderr: str

    def envelope(self) -> dict[str, object]:
        return json.loads(self.stdout)


def _has_ancestor_store(start: Path) -> bool:
    for ancestor in (start, *start.parents):
        if (ancestor / ".novetest").exists():
            return True
    return False


@pytest.fixture
def isolated_cwd(tmp_path: Path) -> Path:
    """A directory guaranteed to have no ``.novetest/`` in any ancestor."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert not _has_ancestor_store(workspace), (
        f"tmp_path ancestor chain unexpectedly contains a .novetest/ directory: {workspace}"
    )
    return workspace


@pytest.fixture
def run_cli(isolated_cwd: Path):
    def _run(args: Sequence[str], *, env_overrides: dict[str, str] | None = None) -> CLIRun:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if env_overrides:
            for k, v in env_overrides.items():
                env[k] = v
        result = subprocess.run(
            [sys.executable, "-m", "novetest", *args],
            cwd=isolated_cwd,
            env=env,
            capture_output=True,
            text=True,
        )
        return CLIRun(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)

    return _run
