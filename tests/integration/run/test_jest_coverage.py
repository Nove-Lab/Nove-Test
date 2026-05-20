"""Integration test for the jest adapter's coverage path against the
``jest-basic-coverage`` fixture.

Spawns a **real** ``npx jest --coverage`` subprocess. It skips when any
of the following preconditions is unmet:

- ``node`` / ``npx`` is not on ``PATH``;
- the fixture's ``node_modules/.bin/jest`` is not present (the user has
  not yet run ``npm install`` inside the fixture).

Same precondition guard as ``test_jest_basic.py``. The current CI matrix
has **no Node.js cell**, so this test is expected to skip on every CI
runner; a future Release-side slice adds Node.js and the test becomes a
real gate.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.target_resolver import resolve_test_target


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


async def test_jest_coverage_emits_istanbul_final_json(tmp_path: Path) -> None:
    _require_node_and_local_jest()

    target = resolve_test_target("__tests__/", FIXTURE_ROOT)
    result = await run_jest(
        target, artifact_dir=tmp_path, timeout=120.0, collect_coverage=True
    )

    assert result.engine_name == "jest"
    assert result.payload["success"] is True

    coverage_path = result.artifact_paths["coverage_json"]
    assert coverage_path.name == "coverage-final.json"
    assert coverage_path.parent.name == "coverage"
    assert coverage_path.is_file()

    # Istanbul's raw shape: a map keyed by absolute source file path,
    # each entry carrying statement / fn / branch maps.
    istanbul = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert isinstance(istanbul, dict)
    classifier_entries = [
        v for k, v in istanbul.items() if k.endswith("classifier.js")
    ]
    assert classifier_entries, "expected coverage for src/classifier.js"
    entry = classifier_entries[0]
    assert "statementMap" in entry
    assert "branchMap" in entry
