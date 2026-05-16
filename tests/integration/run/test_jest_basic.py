"""Integration test for the jest adapter against the ``jest-basic`` fixture.

This test spawns a **real** ``npx jest`` subprocess. It skips when any of
the following preconditions is unmet:

- ``node`` is not on ``PATH``;
- ``npx`` is not on ``PATH``;
- the fixture's ``node_modules/.bin/jest`` is not present (the user has
  not yet run ``npm install`` inside the fixture).

The current CI matrix has **no Node.js cell**, so this test is expected
to skip on every CI runner. It is intended for local-dev exercise. A
future Release-side slice can add Node.js to the matrix and the test
becomes a real gate.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects" / "jest-basic"
)


def _require_node_and_local_jest() -> None:
    if shutil.which("node") is None or shutil.which("npx") is None:
        pytest.skip("requires Node.js (`node` + `npx`) on PATH")
    local_jest = FIXTURE_ROOT / "node_modules" / ".bin" / "jest"
    local_jest_cmd = FIXTURE_ROOT / "node_modules" / ".bin" / "jest.cmd"
    if not local_jest.exists() and not local_jest_cmd.exists():
        pytest.skip(
            "fixture's `node_modules` not installed — run "
            "`(cd tests/fixtures/projects/jest-basic && npm install --no-audit --no-fund)` "
            "to exercise this test locally"
        )


async def test_jest_basic_runs_and_returns_passed_record(tmp_path: Path) -> None:
    _require_node_and_local_jest()

    target = resolve_test_target("__tests__/", FIXTURE_ROOT)
    result = await run_jest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.engine_name == "jest"
    assert result.returncode == 0, (
        f"jest exited non-zero; stderr tail: "
        f"{result.artifact_paths['stderr'].read_text(encoding='utf-8', errors='replace')[-400:]!r}"
    )
    assert result.payload["success"] is True
    assert result.payload["numTotalTests"] == 3
    assert result.payload["numPassedTests"] == 3

    report_path = result.artifact_paths["jest_json_report"]
    assert report_path.is_file()
    assert result.engine_version is not None
    assert result.engine_version.startswith("29.")
