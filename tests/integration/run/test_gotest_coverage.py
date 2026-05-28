"""Integration test for the gotest adapter's coverage path against the
``gotest-basic-coverage`` fixture.

Spawns a **real** ``go test -coverprofile=...`` subprocess. Skips when
``go`` is not on ``PATH``. Same precondition guard as
``test_gotest_basic.py``; current CI has no Go cell yet, so the test is
expected to skip on every CI runner. A future Release-side slice adds
Go to the matrix and the test becomes a real gate.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "gotest-basic-coverage"
)


def _require_go() -> None:
    if shutil.which("go") is None:
        pytest.skip("requires `go` on PATH")


async def test_gotest_coverage_emits_cover_profile(tmp_path: Path) -> None:
    _require_go()

    target = resolve_test_target("", FIXTURE_ROOT)
    result = await run_gotest(
        target, artifact_dir=tmp_path, timeout=120.0, collect_coverage=True
    )

    assert result.engine_name == "go-test"
    # All 4 tests pass in this fixture by contract → exit 0.
    assert result.returncode == 0

    cover_path = result.artifact_paths["coverage_profile"]
    assert cover_path.name == "cover.out"
    assert cover_path.is_file()

    lines = cover_path.read_text(encoding="utf-8").splitlines()
    # First line is the mode header (pinned format since Go 1.0).
    assert lines[0] == "mode: atomic"
    # Subsequent lines have the form
    # `<file>:<startLine>.<startCol>,<endLine>.<endCol> <numStmts> <count>`.
    # Verify the cover profile carries both source files (per
    # -coverpkg=./...).
    file_paths_in_profile = {line.split(":", 1)[0] for line in lines[1:] if line}
    assert any(
        p.endswith("/classifier.go") for p in file_paths_in_profile
    )
    assert any(
        p.endswith("/arithmetic.go") for p in file_paths_in_profile
    )

    # At least one region of `classifier.go` has count=0 (the negative
    # branch is uncovered by fixture contract).
    classifier_lines = [
        line
        for line in lines[1:]
        if line and line.split(":", 1)[0].endswith("/classifier.go")
    ]
    uncovered = [line for line in classifier_lines if line.endswith(" 0")]
    assert uncovered, (
        "expected at least one uncovered region in classifier.go "
        "(the negative branch); got: " + repr(classifier_lines)
    )
