"""End-to-end TEXT-mode rendering via real ``novetest`` subprocesses.

Mirrors the JSON-mode integration tests but pins the human surface: a real
``python -m novetest <verb> --output text`` invocation inside a copied
fixture project must produce scannable text — NOT the pre-slice pretty-JSON
dump (regression guard for the Future-cycle #9 bug). Unstable fields
(``run_id`` ULIDs, timestamps) are asserted via substring/regex, not
snapshot equality, per the brief §"Failure modes" #5.

The JSON / NDJSON wire contract is asserted untouched by the dedicated
byte-identity guard (``test_json_mode_still_starts_with_brace``): TEXT must
change, JSON must not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _prepare(tmp_path: Path, fixture: str) -> Path:
    workspace = tmp_path / fixture
    shutil.copytree(_FIXTURES / fixture, workspace)
    return workspace


def _run(workspace: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _init(workspace: Path) -> None:
    result = _run(workspace, ["init", "--output", "json"])
    assert result.returncode == 0, result.stderr


def test_test_text_mode_is_not_json(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path, "pytest-basic")
    _init(workspace)

    result = _run(workspace, ["test", "--output", "text"])

    assert result.returncode == 0, result.stderr
    # Regression guard against the pre-slice "pretty JSON" bug.
    assert not result.stdout.lstrip().startswith("{")
    assert "recommendation" in result.stdout
    assert "run_id=" in result.stdout


def test_run_text_mode_is_not_json(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path, "pytest-basic")
    _init(workspace)

    result = _run(workspace, ["run", "--output", "text"])

    assert result.returncode == 0, result.stderr
    assert not result.stdout.lstrip().startswith("{")
    assert "passed" in result.stdout
    assert "run_id=" in result.stdout


def test_localization_text_mode_is_not_json(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path, "pytest-failing")
    _init(workspace)

    # ``test`` collects per-test coverage + a failing run, enabling SBFL.
    test_result = _run(workspace, ["test", "--output", "json"])
    assert test_result.returncode == 3, test_result.stderr  # user tests failed
    run_id = json.loads(test_result.stdout)["data"]["run_reference"]["run_id"]

    result = _run(workspace, ["localization", run_id, "--output", "text"])

    assert result.returncode == 0, result.stderr
    assert not result.stdout.lstrip().startswith("{")
    assert "ochiai" in result.stdout
    assert "entries" in result.stdout


def test_json_mode_still_starts_with_brace(tmp_path: Path) -> None:
    """JSON / NDJSON wire contract untouched: TEXT changes, JSON does not."""

    workspace = _prepare(tmp_path, "pytest-basic")
    _init(workspace)

    json_result = _run(workspace, ["run", "--output", "json"])
    assert json_result.returncode == 0, json_result.stderr
    assert json_result.stdout.lstrip().startswith("{")
    json.loads(json_result.stdout)  # parses cleanly

    ndjson_result = _run(workspace, ["run", "--output", "ndjson"])
    assert ndjson_result.returncode == 0, ndjson_result.stderr
    assert ndjson_result.stdout.count("\n") == 1
    json.loads(ndjson_result.stdout.strip())


def test_help_text_mode_is_not_json(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path, "pytest-basic")
    result = _run(workspace, ["--help", "--output", "text"])
    assert result.returncode == 0, result.stderr
    assert not result.stdout.lstrip().startswith("{")
    assert "Onboarding:" in result.stdout
    assert "Operating:" in result.stdout


def test_env_var_json_override_wins_over_text_default(tmp_path: Path) -> None:
    """``NOVETEST_OUTPUT=json`` still routes to the JSON envelope verbatim."""

    workspace = _prepare(tmp_path, "pytest-basic")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", "--help"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.lstrip().startswith("{")
    assert json.loads(result.stdout)["command"] == "help"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
