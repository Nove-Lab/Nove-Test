"""Integration test for the cargo adapter's coverage path against the
``cargo-test-basic-coverage`` fixture.

Spawns a **real** ``cargo llvm-cov nextest --lcov`` subprocess. Skips
when either ``cargo``, ``cargo-nextest``, or ``cargo-llvm-cov`` is
absent. Same precondition guard pattern as ``test_cargo_basic.py``;
current CI has no Rust cell yet, so the test is expected to skip on
every CI runner. A future Release-side slice adds Rust to the matrix
and the test becomes a real gate.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.cargo_adapter import run_cargo
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "cargo-test-basic-coverage"
)


def _require_cargo_nextest_and_llvm_cov() -> None:
    """Skip when cargo / cargo-nextest / cargo-llvm-cov is missing.

    Like the basic-fixture guard, this uses `shutil.which` for the
    cargo-subcommand binaries because they're on PATH as
    `cargo-<name>` per cargo's subcommand convention.
    """

    if shutil.which("cargo") is None:
        pytest.skip("requires `cargo` on PATH")
    if shutil.which("cargo-nextest") is None:
        pytest.skip("requires `cargo-nextest`")
    if shutil.which("cargo-llvm-cov") is None:
        pytest.skip(
            "requires `cargo-llvm-cov` (install: cargo install cargo-llvm-cov)"
        )


async def test_cargo_coverage_emits_lcov_report(tmp_path: Path) -> None:
    _require_cargo_nextest_and_llvm_cov()

    target = resolve_test_target("", FIXTURE_ROOT)
    result = await asyncio.wait_for(
        run_cargo(
            target, artifact_dir=tmp_path, timeout=240.0, collect_coverage=True
        ),
        timeout=260.0,
    )

    assert result.engine_name == "cargo-test"
    # All 4 tests pass in this fixture by contract → exit 0.
    assert result.returncode == 0

    coverage_path = result.artifact_paths["coverage_lcov"]
    assert coverage_path.name == "coverage.lcov"
    assert coverage_path.is_file()

    lcov_text = coverage_path.read_text(encoding="utf-8")
    # LCOV format: each source file is delimited by `SF:<path>` ...
    # `end_of_record`. Verify both source files appear.
    assert "SF:" in lcov_text
    assert "end_of_record" in lcov_text
    assert "classifier.rs" in lcov_text
    assert "arithmetic.rs" in lcov_text

    # At least one `DA:<line>,0` indicates an uncovered region — the
    # negative branch of `classifier::classify` is intentionally
    # uncovered by fixture contract.
    da_lines = [line for line in lcov_text.splitlines() if line.startswith("DA:")]
    uncovered = [line for line in da_lines if line.endswith(",0")]
    assert uncovered, (
        "expected at least one uncovered region (the negative branch of "
        "classifier::classify); got: " + repr(da_lines)
    )
