"""Subprocess E2E for the ``novetest replay <run_id>`` verb.

Exercises the real CLI path (argv → Cyclopts → ``replay_cmd`` →
``replay_run`` → envelope) end-to-end against materialized fixtures. The
pure envelope-builder split is unit-tested in
``tests/unit/cli/test_replay.py``; this file pins the user-facing wire
surface and exit codes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _materialize(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


@dataclass(slots=True, frozen=True)
class _CLIRun:
    returncode: int
    stdout: str
    stderr: str

    def envelope(self) -> dict[str, object]:
        return json.loads(self.stdout)


def _run_cli(workspace: Path, args: Sequence[str]) -> _CLIRun:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return _CLIRun(result.returncode, result.stdout, result.stderr)


def _run_id_of(envelope: dict[str, object]) -> str:
    data = envelope["data"]
    assert isinstance(data, dict)
    entry = data["memory_entry"]
    assert isinstance(entry, dict)
    run_id = entry["entry_id"]
    assert isinstance(run_id, str) and len(run_id) == 26
    return run_id


def test_replay_basic_reproducible_envelope(tmp_path: Path) -> None:
    workspace = _materialize("pytest-basic", tmp_path)
    assert _run_cli(workspace, ["init"]).returncode == 0
    run = _run_cli(workspace, ["run", "tests/"])
    assert run.returncode == 0, run.stderr
    run_id = _run_id_of(run.envelope())

    result = _run_cli(workspace, ["replay", run_id, "--reruns", "3"])
    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "replay"
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    assert data["original_run_reference"]["run_id"] == run_id
    outcome = data["replay_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "replay-result"
    assert outcome["classification"] == "reproducible"
    assert outcome["reruns_total"] == 3
    assert outcome["reruns_failed"] == 0


def test_replay_flaky_inconsistent_envelope(tmp_path: Path) -> None:
    workspace = _materialize("flaky-python", tmp_path)
    assert _run_cli(workspace, ["init"]).returncode == 0
    run = _run_cli(workspace, ["run", "tests/"])
    assert run.returncode == 0, run.stderr
    run_id = _run_id_of(run.envelope())

    result = _run_cli(workspace, ["replay", run_id, "--reruns", "5"])
    assert result.returncode == 0, result.stderr
    outcome = result.envelope()["data"]["replay_outcome"]  # type: ignore[index]
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "replay-result"
    assert outcome["classification"] == "inconsistent"
    assert outcome["reruns_total"] == 5
    assert outcome["reruns_failed"] >= 1
    assert outcome["test_id"] == (
        "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"
    )


def test_replay_unknown_run_id_is_not_found_exit_two(tmp_path: Path) -> None:
    workspace = _materialize("pytest-basic", tmp_path)
    assert _run_cli(workspace, ["init"]).returncode == 0

    result = _run_cli(workspace, ["replay", "01NOTAREALRUNID00000000AAA"])
    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "replay"
    assert envelope["ok"] is False
    errors = envelope["errors"]
    assert isinstance(errors, list)
    assert errors[0]["code"] == "not-found"
