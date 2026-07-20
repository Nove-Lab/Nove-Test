"""Anchored-pin model end-to-end (decision 2026-07-03-engine-selection-policy).

Real ``novetest`` subprocesses against a dual-marker fixture workspace:

    init → engine-ambiguous → init --engine bogus → invalid-flag
         → init --engine pytest → pinned
         → test from a nested subdir (walk-up, workspace-scoped)
         → explicit target from anchor AND from the subdir → ONE baseline
           series (anchor-relative normalization)

plus the ``no-engine-detected`` discovery report, the deep ``uninitialized``
walk-up error, and the D6 legacy-store migration (silent backfill +
ambiguous-anchor error). All four D7 codes are observable here;
``data.candidates`` payload shapes are pinned by syrupy snapshots.

Determinism note — the dual-READY ambiguity: pytest readiness probes the
test venv's interpreter (always ready here), and jest readiness is
PATH + filesystem only (``shutil.which("node"/"npx")`` + package.json +
``node_modules/.bin/jest`` — it never *executes* node). Fabricated ``node`` /
``npx`` shims prepended to PATH therefore make jest deterministically READY
on every host, no Node.js required.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest
from syrupy.assertion import SnapshotAssertion

FIXTURE_PROJECTS_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


@dataclass(slots=True, frozen=True)
class CLIRun:
    returncode: int
    stdout: str
    stderr: str

    def envelope(self) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self.stdout)
        return payload


@pytest.fixture
def node_shim_path(tmp_path: Path) -> Path:
    """A PATH dir with fake ``node`` / ``npx`` executables (never executed)."""

    shims = tmp_path / "node-shims"
    shims.mkdir()
    for name in ("node", "npx"):
        posix = shims / name
        posix.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        posix.chmod(0o755)
        (shims / f"{name}.bat").write_text("@exit /b 0\r\n", encoding="utf-8")
    return shims


@pytest.fixture
def run_cli(node_shim_path: Path):
    """Spawn the real ``novetest`` CLI at a given cwd, shims on PATH."""

    def _run(cwd: Path, args: Sequence[str]) -> CLIRun:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["NOVETEST_OUTPUT"] = "json"
        env["PATH"] = str(node_shim_path) + os.pathsep + env.get("PATH", "")
        env.pop("NOVETEST_HOME", None)
        result = subprocess.run(
            [sys.executable, "-m", "novetest", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return CLIRun(
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr
        )

    return _run


def _fabricate_jest_marker(workspace: Path) -> None:
    """Make jest detection + readiness pass filesystem-only (see module doc)."""

    (workspace / "package.json").write_text(
        json.dumps({"name": "dual-fixture", "devDependencies": {"jest": "^29.0.0"}}),
        encoding="utf-8",
    )
    bin_dir = workspace / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "jest").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    jest_pkg = workspace / "node_modules" / "jest"
    jest_pkg.mkdir(parents=True)
    (jest_pkg / "package.json").write_text(
        json.dumps({"name": "jest", "version": "29.9.9"}), encoding="utf-8"
    )


@pytest.fixture
def dual_marker_workspace(tmp_path: Path) -> Path:
    """pytest-basic fixture + a deterministically-READY jest marker."""

    workspace = tmp_path / "dual"
    shutil.copytree(FIXTURE_PROJECTS_ROOT / "pytest-basic", workspace)
    _fabricate_jest_marker(workspace)
    return workspace


@pytest.fixture
def pytest_only_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "single"
    shutil.copytree(FIXTURE_PROJECTS_ROOT / "pytest-basic", workspace)
    return workspace


def _strip_pin(workspace: Path) -> None:
    """Rewrite store.json into the legacy (pre-pin) shape."""

    metadata_path = workspace / ".novetest" / "store.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("pinned_engine", None)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The canonical dual-marker lifecycle
# ---------------------------------------------------------------------------


def test_dual_marker_lifecycle(
    dual_marker_workspace: Path, run_cli, snapshot: SnapshotAssertion
) -> None:
    workspace = dual_marker_workspace

    # --- init → engine-ambiguous (both candidates READY), nothing created.
    ambiguous = run_cli(workspace, ["init"])
    assert ambiguous.returncode == 2, ambiguous.stderr
    envelope = ambiguous.envelope()
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "engine-ambiguous"
    assert envelope["data"] == snapshot(name="engine_ambiguous_data")
    assert not (workspace / ".novetest").exists()

    # --- init --engine bogus → invalid-flag, still nothing created.
    bogus = run_cli(workspace, ["init", "--engine", "mocha"])
    assert bogus.returncode == 2
    assert bogus.envelope()["errors"][0]["code"] == "invalid-flag"
    assert not (workspace / ".novetest").exists()

    # --- init --engine pytest → pinned store.
    pinned = run_cli(workspace, ["init", "--engine", "pytest"])
    assert pinned.returncode == 0, pinned.stderr
    pinned_data = pinned.envelope()["data"]
    assert pinned_data["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }
    assert pinned_data["engine_readiness"]["engine"] == "pytest"

    # --- status surfaces the pin.
    status = run_cli(workspace, ["status"])
    assert status.returncode == 0, status.stderr
    assert status.envelope()["data"]["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }

    # --- bare `test` from a NESTED subdir: walk-up anchors the store and the
    #     scope stays the whole workspace (target_expression == "").
    nested = workspace / "pytest_basic"
    bare = run_cli(nested, ["test"])
    assert bare.returncode == 0, bare.stderr
    assert bare.envelope()["ok"] is True

    # --- the same explicit ask from the anchor and from the nested subdir
    #     (in a different spelling) lands in ONE baseline series.
    from_anchor = run_cli(workspace, ["test", "tests/test_math_utils.py"])
    assert from_anchor.returncode == 0, from_anchor.stderr
    from_nested = run_cli(nested, ["test", "./tests/test_math_utils.py"])
    assert from_nested.returncode == 0, from_nested.stderr

    entries = run_cli(workspace, ["memory", "list"]).envelope()["data"]["entries"]
    expressions = [e["run_record"]["target_expression"] for e in entries]
    # Newest first: nested-explicit, anchor-explicit, bare.
    assert expressions == ["tests/test_math_utils.py", "tests/test_math_utils.py", ""]
    # All three ran the pinned engine.
    assert {e["run_record"]["engine_name"] for e in entries} == {"pytest"}

    # Series proof end-to-end: the newest explicit run resolves the older
    # explicit run as its regression baseline (same target_expression).
    newest_id = entries[0]["run_record"]["run_reference"]["run_id"]
    baseline_id = entries[1]["run_record"]["run_reference"]["run_id"]
    inspected = run_cli(workspace, ["inspect", newest_id])
    assert inspected.returncode == 0, inspected.stderr
    regression = inspected.envelope()["data"]["regression_outcome"]
    assert regression["kind"] == "fact-set"
    assert regression["baseline_run_reference"]["run_id"] == baseline_id

    # --- re-pin in place: same store, run history retained.
    repinned = run_cli(workspace, ["init", "--engine", "jest"])
    assert repinned.returncode == 0, repinned.stderr
    assert repinned.envelope()["data"]["pinned_engine"]["engine_name"] == "jest"
    after = run_cli(workspace, ["memory", "list"]).envelope()["data"]
    assert after["count"] == 3  # history survived the re-pin


# ---------------------------------------------------------------------------
# Single-marker workspace: envelope unchanged except the additive pin field
# ---------------------------------------------------------------------------


def test_single_marker_init_envelope_is_additive_only(
    pytest_only_workspace: Path, run_cli
) -> None:
    """Acceptance pin: the pre-decision init envelope gains exactly ONE key
    (``data.pinned_engine``) on a single-marker workspace — nothing else
    moves (zero new flags for the ~90% case)."""

    result = run_cli(pytest_only_workspace, ["init"])
    assert result.returncode == 0, result.stderr
    data = result.envelope()["data"]
    assert set(data.keys()) == {
        "store_path",
        "store_state",
        "initialized_at",
        "engine_readiness",
        "pinned_engine",
    }
    assert data["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }
    assert set(data["engine_readiness"].keys()) == {
        "state",
        "engine",
        "ecosystem",
        "engine_version",
        "evidence",
        "issues",
    }
    assert data["engine_readiness"]["state"] == "ready"


# ---------------------------------------------------------------------------
# no-engine-detected — D4 bounded discovery report
# ---------------------------------------------------------------------------


def test_markerless_init_reports_discovered_candidates(
    tmp_path: Path, run_cli, snapshot: SnapshotAssertion
) -> None:
    root = tmp_path / "monorepo"
    root.mkdir()
    backend = root / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    # Skip-list decoy: a marker inside node_modules must NOT be reported.
    decoy = root / "node_modules" / "left-pad"
    decoy.mkdir(parents=True)
    (decoy / "package.json").write_text("{}", encoding="utf-8")

    result = run_cli(root, ["init"])
    assert result.returncode == 4, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "no-engine-detected"
    assert envelope["data"] == snapshot(name="no_engine_detected_data")
    assert envelope["data"]["candidates"] == [
        {"path": "backend", "ecosystem": "python", "engine_name": "pytest"}
    ]
    assert not (root / ".novetest").exists()


# ---------------------------------------------------------------------------
# uninitialized — the existing code, via the upward walk
# ---------------------------------------------------------------------------


def test_verb_in_uninitialized_tree_errors_without_scanning(
    tmp_path: Path, run_cli
) -> None:
    deep = tmp_path / "plain" / "a" / "b"
    deep.mkdir(parents=True)
    result = run_cli(deep, ["status"])
    assert result.returncode == 2
    assert result.envelope()["errors"][0]["code"] == "uninitialized"


# ---------------------------------------------------------------------------
# D6 migration — legacy pin-less stores (S19 read/execution seam split;
# Gate-1 D1=A / D2=A, 2026-07-20)
# ---------------------------------------------------------------------------


def test_legacy_store_read_verb_does_not_backfill_execution_verb_does(
    pytest_only_workspace: Path, run_cli
) -> None:
    """D2=A: a READ verb (``status``) over a legacy single-marker store
    proceeds engine-less and writes NOTHING — the pin stays absent. The
    backfill happens on the next EXECUTION verb (``run``)."""

    workspace = pytest_only_workspace
    assert run_cli(workspace, ["init"]).returncode == 0
    _strip_pin(workspace)  # simulate a store created before the decision
    store_json = workspace / ".novetest" / "store.json"

    # --- READ verb: proceeds engine-less, leaves the store pin-less.
    status = run_cli(workspace, ["status"])
    assert status.returncode == 0, status.stderr
    envelope = status.envelope()
    assert envelope["ok"] is True
    assert envelope["errors"] == []
    # No backfill: pin is still absent on the wire AND on disk.
    assert envelope["data"]["pinned_engine"] is None
    assert "pinned_engine" not in json.loads(
        store_json.read_text(encoding="utf-8")
    )

    # --- EXECUTION verb: NOW the legacy store is pinned (single marker).
    run = run_cli(workspace, ["run"])
    assert run.returncode == 0, run.stderr
    metadata = json.loads(store_json.read_text(encoding="utf-8"))
    assert metadata["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }


def test_legacy_ambiguous_store_read_proceeds_execution_refuses(
    dual_marker_workspace: Path, run_cli
) -> None:
    """The C8-narrow trigger, both shapes: on a legacy + ambiguous store a
    READ verb exits 0 (D1=A) while an EXECUTION verb still exits 2 with
    ``engine-ambiguous`` (the refusal moved to the execution path)."""

    workspace = dual_marker_workspace
    assert run_cli(workspace, ["init", "--engine", "pytest"]).returncode == 0
    _strip_pin(workspace)

    # --- READ verb: proceeds engine-less, exit 0 (was exit 2 pre-S19).
    read = run_cli(workspace, ["status"])
    assert read.returncode == 0, read.stderr
    assert read.envelope()["ok"] is True
    assert read.envelope()["data"]["pinned_engine"] is None

    # --- EXECUTION verb: still refuses on ambiguity.
    for verb in ("run", "test"):
        execution = run_cli(workspace, [verb])
        assert execution.returncode == 2, execution.stderr
        envelope = execution.envelope()
        assert envelope["errors"][0]["code"] == "engine-ambiguous"
        assert "novetest init --engine" in envelope["errors"][0]["message"]

    # The instructed re-pin resolves it in place; reads and executions agree.
    assert run_cli(workspace, ["init", "--engine", "pytest"]).returncode == 0
    assert run_cli(workspace, ["status"]).returncode == 0


def test_read_verb_over_legacy_ambiguous_store_leaves_store_json_byte_identical(
    dual_marker_workspace: Path, run_cli
) -> None:
    """Read-purity (D2=A) at the byte level: a ``status`` over a legacy +
    ambiguous store mutates ``store.json`` not at all — same bytes before and
    after (no torn/backfilled write, no timestamp churn)."""

    workspace = dual_marker_workspace
    assert run_cli(workspace, ["init", "--engine", "pytest"]).returncode == 0
    _strip_pin(workspace)
    store_json = workspace / ".novetest" / "store.json"
    before = store_json.read_bytes()

    result = run_cli(workspace, ["status"])
    assert result.returncode == 0, result.stderr

    assert store_json.read_bytes() == before
