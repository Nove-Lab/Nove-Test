"""Adapter error-classification honesty — W2/S15 riders (routed from the
W1/S8 close), end-to-end through the REAL ``novetest`` CLI.

Two user-side error shapes used to surface as the adapter catch-all
``adapter-unparseable-output`` (exit 4), steering agents toward tool-repair
remediation for what is a fix-your-code/config problem. Both now persist an
``errored`` Run Record (exit 3, ``ok: true``) per the documented contract —
``docs/agent/troubleshooting.md`` "Exit 3 is not an error": a suite that
crashed before producing normal results "is still a persisted user result".

| Shape | Pre-S15 | Post-S15 |
|---|---|---|
| pytest collection/import error under coverage (``test`` verb always-on; ``run --coverage``) | exit 4 ``adapter-unparseable-output`` | exit 3, ``status="errored"``, coverage artifacts omitted |
| corrupt ``go.mod`` with go installed (build failure, zero tests ran) | exit 4 ``adapter-unparseable-output`` | exit 3, ``status="errored"``, zero test_results |

The adapter-level boundary pins (incl. the KEEP side: clean pytest exit +
missing coverage JSON still raises) live in
``tests/unit/run/adapters/test_pytest_adapter.py`` and
``tests/unit/run/adapters/test_gotest_adapter.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Spawn ``[sys.executable, "-m", "novetest", *args]`` in ``workspace``.

    Same canonical shape (``NOVETEST_OUTPUT=json`` + UTF-8) as the other
    run-integration smokes (``test_zero_collection_warning.py`` /
    ``test_dotnet_warnings.py``).
    """

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    return subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def _assert_errored_user_result(
    result: subprocess.CompletedProcess[str],
) -> dict[str, object]:
    """Exit 3 / ok=true / empty errors — the persisted-user-result shape."""

    assert result.returncode == 3, (
        f"expected exit 3 (persisted errored run); got "
        f"{result.returncode}: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["errors"] == []
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


# ---------------------------------------------------------------------------
# pytest collection error under coverage (wire delta B)
# ---------------------------------------------------------------------------


@pytest.fixture
def broken_collection_workspace(tmp_path: Path) -> Path:
    """Copy ``pytest-basic`` and plant a syntactically broken test module.

    pytest exits 2 on the collection error; pytest-cov writes NO coverage
    JSON when the session is interrupted during collection — the exact
    shape that used to abort inside the adapter on the coverage path.
    """

    dest = tmp_path / "pytest-basic"
    shutil.copytree(FIXTURE_ROOT / "pytest-basic", dest)
    (dest / "tests" / "test_broken_syntax.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8"
    )
    return dest


def test_cli_test_verb_collection_error_is_persisted_errored_run(
    broken_collection_workspace: Path,
) -> None:
    """``novetest test`` (always-on coverage) on a collection-error suite →
    exit 3 / ok=true and a persisted ``errored`` Run Record — the shape the
    W1/S8 contract test had to avoid (pre-S15 it exited 4)."""

    init_result = _spawn_novetest(
        broken_collection_workspace, ["init"], timeout=60.0
    )
    assert init_result.returncode == 0, init_result.stderr

    test_result = _spawn_novetest(
        broken_collection_workspace, ["test"], timeout=300.0
    )
    data = _assert_errored_user_result(test_result)

    run_reference = data["run_reference"]
    assert isinstance(run_reference, dict)
    run_id = run_reference["run_id"]
    assert isinstance(run_id, str) and run_id

    # The persisted record really is `errored` (not a masked failure).
    show_result = _spawn_novetest(
        broken_collection_workspace, ["memory", "show", run_id], timeout=60.0
    )
    assert show_result.returncode == 0, show_result.stderr
    show_data = json.loads(show_result.stdout)["data"]
    memory_entry = show_data["memory_entry"]
    run_record = memory_entry["run_record"]
    assert run_record["status"] == "errored"
    # Coverage artifacts were omitted — pytest-cov never wrote them.
    assert "coverage_json" not in run_record["artifact_paths"]
    assert "coverage_xml" not in run_record["artifact_paths"]


def test_cli_run_coverage_collection_error_is_persisted_errored_run(
    broken_collection_workspace: Path,
) -> None:
    """``novetest run --coverage`` on the same suite → exit 3 with the
    ``errored`` record inline on ``data.memory_entry``."""

    init_result = _spawn_novetest(
        broken_collection_workspace, ["init"], timeout=60.0
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(
        broken_collection_workspace, ["run", "--coverage"], timeout=300.0
    )
    data = _assert_errored_user_result(run_result)

    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    assert run_record["status"] == "errored"
    assert "coverage_json" not in run_record["artifact_paths"]


# ---------------------------------------------------------------------------
# corrupt go.mod with go installed (wire delta C)
# ---------------------------------------------------------------------------


def _require_go() -> None:
    if shutil.which("go") is None:
        pytest.skip("requires `go` on PATH (see scripts/dev-host-setup.md §3)")


@pytest.fixture
def corrupt_gomod_workspace(tmp_path: Path) -> Path:
    """Copy ``gotest-basic``; the test corrupts ``go.mod`` after init."""

    dest = tmp_path / "gotest-basic"
    shutil.copytree(FIXTURE_ROOT / "gotest-basic", dest)
    return dest


def test_cli_corrupt_gomod_is_persisted_errored_run(
    corrupt_gomod_workspace: Path,
) -> None:
    """A corrupt ``go.mod`` on an equipped host: ``go test -json`` fails
    before any test runs (no NDJSON, non-zero exit) → a persisted
    ``errored`` run with zero test results, exit 3 — NOT the exit-4
    ``adapter-unparseable-output`` catch-all (nothing was unparseable;
    nothing was produced)."""

    _require_go()

    init_result = _spawn_novetest(corrupt_gomod_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, init_result.stderr

    # Corrupt AFTER init: the marker file still exists (detection + the
    # `go version` readiness probe stay green) but the build fails.
    (corrupt_gomod_workspace / "go.mod").write_text(
        "modle example.com/gotestbasic\n", encoding="utf-8"
    )

    run_result = _spawn_novetest(corrupt_gomod_workspace, ["run"], timeout=300.0)
    data = _assert_errored_user_result(run_result)

    memory_entry = data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    assert run_record["status"] == "errored"
    assert run_record["test_results"] == []
    summary = run_record["summary_counts"]
    assert isinstance(summary, dict)
    assert summary.get("total") == 0
