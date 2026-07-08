"""Zero-collection warning integration coverage (W1/S4, RUN-12, correction C1).

The engine-level site in ``run/engine.py::execute_with_engine_context``
appends one ``AdapterWarning(code="zero-tests-collected")`` when a run
normalizes to a **passed** ``RunRecord`` with an **empty** ``test_results``
tuple — "the engine ran clean but nothing executed". This module proves the
three-way C1 behaviour end-to-end across the engines that share this file:

| Engine | Zero-collection outcome | Covered by |
|---|---|---|
| go-test | ``passed`` + ``zero-tests-collected`` warning | ``test_cli_smoke_gotest_zero_collection_emits_warning`` (this file) |
| junit | ``passed`` + ``zero-tests-collected`` warning | ``test_junit_warnings.py`` |
| xunit | ``passed`` + ``zero-tests-collected`` warning | ``test_dotnet_warnings.py`` |
| jest | ``AdapterInvocationError`` *before* a RunRecord (loud) | ``test_jest_zero_collection_raises_before_record`` (this file) |
| cargo | ``AdapterInvocationError`` *before* a RunRecord (loud) | ``test_cargo_zero_collection_raises_before_record`` (this file) |
| pytest | exit-5 → ``errored`` (separate concern) | ``tests/unit/run/test_engine.py`` case (3) |

The go test is the "go one" the S4 brief asks for; the jest / cargo
adapter-direct tests are the confirming C1 negatives (they never reach the
warning site because they raise a typed error first). Each skip-gates on
its toolchain so unequipped CI stays green; the equip-and-exercise gate on
an equipped host runs all three.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.run.adapters.cargo_adapter import run_cargo
from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"

ZERO_TESTS_COLLECTED = "zero-tests-collected"


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Spawn ``[sys.executable, "-m", "novetest", *args]`` in ``workspace``.

    Same canonical shape (``NOVETEST_OUTPUT=json`` + UTF-8) as the other
    per-engine warnings smokes (``test_junit_warnings.py`` /
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


# ---------------------------------------------------------------------------
# go-test — the positive case (passed-empty → warning) via the live CLI
# ---------------------------------------------------------------------------


def _require_go() -> None:
    if shutil.which("go") is None:
        pytest.skip("requires `go` on PATH (see scripts/dev-host-setup.md §3)")


@pytest.fixture
def gotest_zero_collection_workspace(tmp_path: Path) -> Path:
    """Copy ``gotest-basic`` so ``novetest init`` writes ``.novetest/``
    into the workspace without polluting the fixture tree."""

    dest = tmp_path / "gotest-basic"
    shutil.copytree(FIXTURE_ROOT / "gotest-basic", dest)
    return dest


def test_cli_smoke_gotest_zero_collection_emits_warning(
    gotest_zero_collection_workspace: Path,
) -> None:
    """``novetest run <pkg>::<NoSuchTest>`` against a real go module runs
    the engine to completion, collects zero tests, exits ``0`` (EXIT_OK),
    and surfaces ``zero-tests-collected`` on ``envelope.warnings[]``.

    ``go test -run '^TestNoSuchThing$' <pkg>`` matches nothing → "no tests
    to run", process exit 0 → the normalizer produces a ``passed`` record
    with an empty ``test_results`` tuple → the engine-level site decorates
    the run. This is exactly the silent-green path S4 makes loud.
    """

    _require_go()

    init_result = _spawn_novetest(
        gotest_zero_collection_workspace, ["init"], timeout=60.0
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(
        gotest_zero_collection_workspace,
        ["run", "example.com/gotestbasic::TestNoSuchThing"],
        timeout=300.0,
    )
    # A passed zero-collection run is EXIT_OK (0) — the warning is a
    # visibility signal, NOT a status/exit change (C1).
    assert run_result.returncode == 0, (
        f"expected exit 0 (EXIT_OK) for a passed zero-collection run; "
        f"got {run_result.returncode}. stdout={run_result.stdout!r} "
        f"stderr={run_result.stderr!r}"
    )

    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    run_record = envelope["data"]["memory_entry"]["run_record"]
    assert run_record["status"] == "passed"
    assert run_record["test_results"] == []

    warnings_block = envelope.get("warnings", [])
    assert isinstance(warnings_block, list)
    matching = [w for w in warnings_block if w.get("code") == ZERO_TESTS_COLLECTED]
    assert matching, (
        f"expected envelope warning with code={ZERO_TESTS_COLLECTED!r}; "
        f"got warnings={warnings_block!r}"
    )
    warning = matching[0]
    assert warning.get("message")
    assert "collected zero tests" in warning["message"]
    assert warning.get("details", {}).get("engine_name") == "go-test"


# ---------------------------------------------------------------------------
# jest — the negative case: raises a typed error BEFORE a RunRecord (C1)
# ---------------------------------------------------------------------------


def _require_node_and_local_jest() -> None:
    if shutil.which("node") is None or shutil.which("npx") is None:
        pytest.skip("requires Node.js (`node` + `npx`) on PATH")
    local_jest = FIXTURE_ROOT / "jest-basic" / "node_modules" / ".bin" / "jest"
    local_jest_cmd = FIXTURE_ROOT / "jest-basic" / "node_modules" / ".bin" / "jest.cmd"
    if not local_jest.exists() and not local_jest_cmd.exists():
        pytest.skip(
            "fixture's `node_modules` not installed — run "
            "`(cd tests/fixtures/projects/jest-basic && npm ci)` to exercise "
            "this test locally"
        )


async def test_jest_zero_collection_raises_before_record(tmp_path: Path) -> None:
    """jest matching zero tests raises ``AdapterInvocationError`` — it never
    reaches the engine-level zero-collection site (C1: already loud).

    Without ``--passWithNoTests`` (the adapter deliberately does not pass
    it), jest exits non-zero on "No tests found" and writes no JSON report,
    so the adapter raises before a ``NativeResult`` — hence before any
    ``RunRecord`` — exists. The ``zero-tests-collected`` warning is
    unreachable for jest by construction.
    """

    _require_node_and_local_jest()

    target = resolve_test_target(
        "NoSuchTestFileZZZ", FIXTURE_ROOT / "jest-basic"
    )
    with pytest.raises(AdapterInvocationError):
        await run_jest(target, artifact_dir=tmp_path, timeout=120.0)


# ---------------------------------------------------------------------------
# cargo — the negative case: raises a typed error BEFORE a RunRecord (C1)
# ---------------------------------------------------------------------------


def _require_cargo_and_nextest() -> None:
    if shutil.which("cargo") is None:
        pytest.skip("requires `cargo` on PATH")
    if shutil.which("cargo-nextest") is None:
        pytest.skip(
            "requires `cargo-nextest` (install: cargo install cargo-nextest --locked)"
        )


async def test_cargo_zero_collection_raises_before_record(tmp_path: Path) -> None:
    """cargo-nextest matching zero tests raises ``AdapterInvocationError`` —
    it never reaches the engine-level zero-collection site (C1: already loud).

    The cargo adapter treats a filter that matched zero tests as an
    invocation error (nextest itself exits non-zero on "no tests to run"),
    so it raises before a ``NativeResult`` exists. The
    ``zero-tests-collected`` warning is unreachable for cargo by
    construction.
    """

    _require_cargo_and_nextest()

    workspace = tmp_path / "cargo-test-basic"
    shutil.copytree(FIXTURE_ROOT / "cargo-test-basic", workspace)
    target = resolve_test_target(
        "cargo_test_basic::tests::no_such_test_zzz", workspace
    )
    with pytest.raises(AdapterInvocationError):
        await asyncio.wait_for(
            run_cargo(target, artifact_dir=tmp_path / "art", timeout=300.0),
            timeout=320.0,
        )
