"""Shared fixtures for orchestration integration tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pytest


FIXTURE_PROJECTS_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _materialize_fixture(name: str, dest: Path) -> Path:
    """Copy a fixture project tree into ``dest`` and return the new root."""

    src = FIXTURE_PROJECTS_ROOT / name
    target = dest / name
    shutil.copytree(src, target)
    return target


@pytest.fixture
def basic_workspace(tmp_path: Path) -> Path:
    return _materialize_fixture("pytest-basic", tmp_path)


@pytest.fixture
def failing_workspace(tmp_path: Path) -> Path:
    return _materialize_fixture("pytest-failing", tmp_path)


@pytest.fixture
def empty_workspace(tmp_path: Path) -> Path:
    return _materialize_fixture("empty-no-engine", tmp_path)


@pytest.fixture
def coverage_workspace(tmp_path: Path) -> Path:
    return _materialize_fixture("pytest-coverage", tmp_path)


@pytest.fixture
def collection_error_workspace(tmp_path: Path) -> Path:
    """A pytest project whose test module does not parse (row 45).

    The suite never executes: pytest raises at collection, collects zero
    tests and exits non-zero, so the Run Record lands ``status: "errored"``
    with no ``test_results`` at all.
    """
    return _materialize_fixture("pytest-collection-error", tmp_path)


@dataclass(slots=True, frozen=True)
class CLIRun:
    returncode: int
    stdout: str
    stderr: str

    def envelope(self) -> dict[str, object]:
        return json.loads(self.stdout)


@pytest.fixture
def run_cli_in():
    """Spawn the real ``novetest`` CLI rooted at a given workspace path."""

    def _run(workspace: Path, args: Sequence[str]) -> CLIRun:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # NOVETEST_OUTPUT=json pins the envelope shape; the CLI flag would
        # work too but every integration test wants the same mode anyway.
        env["NOVETEST_OUTPUT"] = "json"
        result = subprocess.run(
            [sys.executable, "-m", "novetest", *args],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            # The child is forced to UTF-8 (`PYTHONIOENCODING` above), but
            # `text=True` decodes the captured pipes with the *parent*'s
            # locale codec, which is cp1252 on a Windows runner. Pin the
            # decode to UTF-8 to match what the child writes.
            encoding="utf-8",
        )
        return CLIRun(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return _run
