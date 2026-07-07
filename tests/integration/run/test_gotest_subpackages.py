"""RUN-01 (W1/S1) regression tests against the ``gotest-subpackages`` fixture.

The fixture's root package compiles but has NO tests; everything lives in
``./pkg``. Pre-fix:

- ``run .`` appended ``.`` verbatim → ``go test -json … .`` ran the root
  package only, non-recursively → zero tests, exit 0, normalized to
  ``status="passed"`` — silent false green;
- ``run ./pkg`` (normalized to ``pkg``) was read by go as an IMPORT PATH
  (``package pkg is not in std``) → pre-compile failure → fake
  ``AdapterInvocationError(unparseable-output)`` build failure.

These tests spawn a **real** ``go test -json`` subprocess and skip when
``go`` is not on ``PATH`` (same posture as ``test_gotest_basic.py``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import NativeResult


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects" / "gotest-subpackages"
)

SUBPACKAGE_IMPORT_PATH = "example.com/gotestsubpackages/pkg"


def _require_go() -> None:
    if shutil.which("go") is None:
        pytest.skip("requires `go` on PATH")


def _tests_run(result: NativeResult) -> set[str]:
    """Names of tests that emitted a ``run`` action."""

    events = result.payload["events"]
    assert isinstance(events, list)
    return {
        event["Test"]
        for event in events
        if isinstance(event, dict)
        and event.get("Action") == "run"
        and isinstance(event.get("Test"), str)
    }


async def test_directory_dot_target_runs_subpackage_tests(tmp_path: Path) -> None:
    """``run .`` must execute the subpackage tests — not 0-tests-passed."""

    _require_go()

    target = resolve_test_target(".", FIXTURE_ROOT)
    assert target.target_type == "directory"
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.returncode == 0
    assert _tests_run(result) == {"TestAdd", "TestAddCommutative", "TestDouble"}
    packages = result.payload["packages"]
    assert isinstance(packages, list)
    assert SUBPACKAGE_IMPORT_PATH in packages


async def test_directory_subpackage_target_runs_instead_of_fake_build_failure(
    tmp_path: Path,
) -> None:
    """``run ./pkg`` (normalized: ``pkg``) runs normally — no fake failure."""

    _require_go()

    target = resolve_test_target("pkg", FIXTURE_ROOT)
    assert target.target_type == "directory"
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.returncode == 0
    assert _tests_run(result) == {"TestAdd", "TestAddCommutative", "TestDouble"}


async def test_nodeid_target_selects_exactly_one_test(tmp_path: Path) -> None:
    """``pkg::TestAdd`` decomposes to ``-run '^TestAdd$' ./pkg`` — the
    anchoring matters: ``TestAddCommutative`` shares the prefix and an
    unanchored pattern would over-select."""

    _require_go()

    target = resolve_test_target("pkg::TestAdd", FIXTURE_ROOT)
    assert target.target_type == "nodeid"
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.returncode == 0
    assert _tests_run(result) == {"TestAdd"}


async def test_engine_native_wildcard_still_passes_verbatim(tmp_path: Path) -> None:
    """``./...`` remains engine-native pass-through after the conversion."""

    _require_go()

    target = resolve_test_target("./...", FIXTURE_ROOT)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=120.0)

    assert result.returncode == 0
    assert _tests_run(result) == {"TestAdd", "TestAddCommutative", "TestDouble"}
