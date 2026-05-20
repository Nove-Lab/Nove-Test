"""End-to-end test: `novetest run --coverage` on a jest workspace.

Exercises the full jest coverage path — the Run adapter emits an Istanbul
`coverage-final.json`, and the Coverage engine's Istanbul parser turns it
into a real `CoverageFactSet` (instead of `CoverageUnavailable`).

This test spawns a **real** jest subprocess. It skips when any of the
following preconditions is unmet, mirroring `tests/integration/run/
test_jest_basic.py`:

- `node` / `npx` is not on `PATH`;
- the `jest-basic-coverage` fixture's `node_modules` is not installed
  (run `(cd tests/fixtures/projects/jest-basic-coverage && npm install
  --no-audit --no-fund)` to exercise locally).

The `jest-basic-coverage` fixture is created by the parallel Run-team
slice (`tasks/run-team-2026-05-20-jest-coverage-wiring.md`); it exists
post-merge. Until then the skip guard fires cleanly because the fixture's
`node_modules/.bin/jest` is absent.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from novetest.coverage.persistence import coverage_facts_path
from novetest.memory.project_store import create_project_store
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.orchestration.workflows.run import run_target_in_store


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "jest-basic-coverage"
)


def _require_node_and_local_jest() -> None:
    if shutil.which("node") is None or shutil.which("npx") is None:
        pytest.skip("requires Node.js (`node` + `npx`) on PATH")
    local_jest = FIXTURE_ROOT / "node_modules" / ".bin" / "jest"
    local_jest_cmd = FIXTURE_ROOT / "node_modules" / ".bin" / "jest.cmd"
    if not local_jest.exists() and not local_jest_cmd.exists():
        pytest.skip(
            "fixture's `node_modules` not installed — run "
            "`(cd tests/fixtures/projects/jest-basic-coverage && "
            "npm install --no-audit --no-fund)` to exercise this test locally"
        )


def _materialize_jest_workspace(dest: Path) -> Path:
    """Copy the fixture into ``dest`` and symlink its installed node_modules.

    Copying `node_modules` outright would be slow; a symlink keeps jest's
    module resolution working while leaving the committed fixture pristine.
    """
    workspace = dest / "jest-basic-coverage"
    shutil.copytree(
        FIXTURE_ROOT,
        workspace,
        ignore=shutil.ignore_patterns("node_modules", ".novetest"),
    )
    os.symlink(FIXTURE_ROOT / "node_modules", workspace / "node_modules")
    return workspace


async def test_run_coverage_on_jest_workspace_produces_fact_set(
    tmp_path: Path,
) -> None:
    _require_node_and_local_jest()

    workspace = _materialize_jest_workspace(tmp_path)
    store = create_project_store(workspace)

    outcome = await run_target_in_store("", store, collect_coverage=True)

    fact_set = outcome.coverage_outcome
    assert isinstance(fact_set, CoverageFactSet), (
        f"expected a CoverageFactSet, got {fact_set!r}"
    )
    assert fact_set.engine_name == "jest"
    assert fact_set.ecosystem == "javascript-typescript"
    # jest's default --coverage merges per-run with no per-test attribution.
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.summary.num_statements > 0
    assert fact_set.files, "expected at least one covered source file"

    for file_coverage in fact_set.files:
        # Decision 2026-05-15 #6: persisted paths are workspace-relative.
        assert not Path(file_coverage.file_path).is_absolute()
        assert not file_coverage.file_path.startswith("..")
        assert file_coverage.line_contexts == {}

    # The load-bearing facts file landed on disk so Memory's
    # `has_coverage_facts` flag auto-flips.
    assert coverage_facts_path(store, fact_set.run_reference.run_id).is_file()
    assert outcome.memory_entry.has_coverage_facts is True
