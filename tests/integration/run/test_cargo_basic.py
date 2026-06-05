"""Integration test for the cargo adapter against the ``cargo-test-basic``
fixture.

Spawns **real** ``cargo nextest run`` subprocesses. Skips when either
``cargo`` or ``cargo-nextest`` is absent. The current CI matrix has no
Rust cell yet, so this test is expected to skip on every CI runner; it
is intended for local-dev exercise and the matrix-extension follow-up
(Release team).

CLI-level smokes (added 2026-06-05 per
``tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md`` §3 +
``decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`` §2):
``test_cli_smoke_run_dot_emits_envelope`` and
``test_cli_smoke_run_bare_emits_envelope`` exercise the full
orchestration path via ``subprocess.run([sys.executable, "-m",
"novetest", ...])``, catching defects that bypass the adapter-direct
call. The dot-case pins the 2026-06-04 cargo CLI orchestration defect:
``novetest run .`` returned ``adapter-unparseable-output`` because
``target_resolver`` classified ``.`` as ``target_type="directory"``
with ``target_expression="."``, and the pre-fix cargo adapter appended
``.`` to nextest's argv as a filter DSL token that matched zero tests.
The bare-case is the control — proves the existing happy-path stays
green under the same CLI orchestration. Both skip-gate on
``cargo + cargo-nextest`` presence so unequipped CI stays green;
Manual Test's equipped host (per ``scripts/dev-host-setup.md §4``)
runs them.
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
from novetest.run.target_resolver import resolve_test_target


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "cargo-test-basic"
)


def _require_cargo_and_nextest() -> None:
    """Skip when cargo or cargo-nextest is missing.

    `cargo nextest` is a cargo subcommand — cargo finds it via the
    `cargo-<name>` binary on PATH convention. So `shutil.which(
    "cargo-nextest")` is both correct and zero-cost (no subprocess spawn).
    """

    if shutil.which("cargo") is None:
        pytest.skip("requires `cargo` on PATH")
    if shutil.which("cargo-nextest") is None:
        pytest.skip(
            "requires `cargo-nextest` (install: cargo install cargo-nextest --locked)"
        )


async def test_cargo_basic_captures_failing_test_and_integration_binary(
    tmp_path: Path,
) -> None:
    _require_cargo_and_nextest()

    target = resolve_test_target("", FIXTURE_ROOT)
    result = await asyncio.wait_for(
        run_cargo(target, artifact_dir=tmp_path, timeout=180.0),
        timeout=200.0,
    )

    assert result.engine_name == "cargo-test"
    # `test_subtract_intentionally_fails` fails by fixture contract → non-zero exit.
    assert result.returncode != 0

    events = result.payload["events"]
    assert isinstance(events, list) and len(events) > 0

    # The fixture has 3 leaf tests across two binaries:
    # - cargo_test_basic::tests::test_add_passes (unit, passes)
    # - cargo_test_basic::tests::test_subtract_intentionally_fails (unit, fails)
    # - <integration_test binary>::test_add_via_integration (integration, passes)
    test_event_names = {
        e.get("name")
        for e in events
        if isinstance(e, dict) and e.get("type") == "test" and e.get("event") != "started"
    }
    assert any(
        "test_add_passes" in str(name) for name in test_event_names
    )
    assert any(
        "test_subtract_intentionally_fails" in str(name) for name in test_event_names
    )
    assert any(
        "test_add_via_integration" in str(name) for name in test_event_names
    )

    # Failure log written for the failing test.
    failure_logs = result.payload["failure_logs"]
    assert isinstance(failure_logs, dict)
    failing_keys = [
        k for k in failure_logs if "test_subtract_intentionally_fails" in k
    ]
    assert failing_keys, f"expected a failure log key for the failing test; got {failure_logs!r}"
    failure_rel_path = failure_logs[failing_keys[0]]
    failure_log = tmp_path / str(failure_rel_path)
    assert failure_log.is_file()
    log_body = failure_log.read_text(encoding="utf-8")
    # Either the panic message or the backtrace marker should be present.
    assert "panicked" in log_body or "subtract" in log_body.lower()

    # `events.jsonl` round-trips.
    events_path = result.artifact_paths["cargo_events_jsonl"]
    assert events_path.is_file()
    assert events_path.read_text(encoding="utf-8").splitlines()

    # Engine version was parsed from `cargo --version`.
    assert result.engine_version is not None
    assert result.engine_version.startswith("1.")


# ---------------------------------------------------------------------------
# CLI-level smokes (2026-06-05 cargo CLI orchestration defect closure)
#
# These two tests exercise the full ``[sys.executable, "-m", "novetest",
# ...]`` invocation against a freshly initialized fixture workspace —
# the same path Manual Test's 2026-06-04 equipped-host pass exercised
# manually. The dot-case is the regression pin for the original
# defect; the bare-case is the control that proves the existing
# happy-path stays green under CLI orchestration too.
#
# Pattern source: ``tests/integration/orchestration/conftest.py::
# run_cli_in`` (the canonical CLI smoke shape — same Python
# interpreter, ``NOVETEST_OUTPUT=json`` for stable envelope, UTF-8
# decode). The JUnit hotfix #1 (2026-06-04) established the pattern
# precedent for adapter-cycle CLI smokes; this slice carries it to
# cargo.
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_smoke_workspace(tmp_path: Path) -> Path:
    """Copy ``cargo-test-basic`` into ``tmp_path`` so ``novetest init``
    can write ``.novetest/`` into the workspace without polluting the
    fixture tree. Matches the JUnit and gotest fixture-isolation pattern.

    The copy includes the source tree but excludes the typical cargo
    artifacts (``target/``, ``Cargo.lock``) — those are gitignored in
    the fixture so ``shutil.copytree`` only carries the version-pinned
    files. A fresh ``target/`` materializes during the smoke's first
    compilation.
    """

    dest = tmp_path / "cargo-test-basic"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _spawn_novetest(workspace: Path, args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Spawn ``[sys.executable, "-m", "novetest", *args]`` in ``workspace``
    with the canonical env (``NOVETEST_OUTPUT=json`` + UTF-8) and return
    the completed process.

    Single helper used by both CLI smokes so the env / argv shape is
    identical between them — a divergence would mask invocation-shape
    bugs that the two cases are meant to triangulate.
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


def test_cli_smoke_run_dot_emits_envelope(cli_smoke_workspace: Path) -> None:
    """Pin the 2026-06-04 cargo CLI orchestration defect closure.

    Pre-fix (Manual Test 2026-06-04 capture, see
    ``agent-comms/findings/manual-test-team-2026-06-04-host-equip.md``
    §"Cargo adapter — CLI vs adapter-direct discrepancy"):
    ``novetest run .`` against ``cargo-test-basic`` returned
    ``adapter-unparseable-output`` with stderr tail ``Starting 0
    tests across 2 binaries (3 tests skipped) … error: no tests to
    run``. The pre-fix cargo adapter appended the literal ``"."`` to
    nextest's argv as a filter DSL token, matching zero tests.

    Post-fix (Fix A + Fix B):
    - Fix A suppresses the append for ``target_type="directory"``.
    - ``--workspace`` covers the workspace root, so the invocation is
      identical to ``novetest run`` bare.
    - The fixture has 2 passing + 1 failing test → CLI emits a Run
      Record envelope with ``ok: true`` and exit
      ``EXIT_USER_TESTS_FAILED=3`` (the dedicated channel for
      "tests ran, some failed").
    - Exit ``1`` (``EXIT_GENERIC``) was the pre-fix failure mode —
      the assertion's ``(0, 3)`` tuple rejects that.

    Skip-gates on ``cargo + cargo-nextest`` presence — unequipped CI
    stays green; Manual Test's equipped host (per
    ``scripts/dev-host-setup.md §4``) runs this. Per
    ``decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md``
    §2.5, originating-team pre-handoff gate also exercises this on an
    equipped host.
    """

    _require_cargo_and_nextest()

    init_result = _spawn_novetest(cli_smoke_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, (
        f"`novetest init` failed: stdout={init_result.stdout!r} "
        f"stderr={init_result.stderr!r}"
    )

    # The defect surface: positional ``.`` reaches the adapter as a
    # nextest filter pre-fix; post-fix Fix A suppresses the append for
    # ``target_type="directory"`` and the invocation succeeds.
    run_result = _spawn_novetest(cli_smoke_workspace, ["run", "."], timeout=300.0)

    # Exit 0 (all passed) or 3 (EXIT_USER_TESTS_FAILED, some user test
    # failed) are the only acceptable codes on the canonical happy-path
    # fixture. The cargo-test-basic fixture has exactly one failing
    # test by contract (``test_subtract_intentionally_fails``), so the
    # expected exit is 3 — but 0 would also be acceptable (e.g. if a
    # future polish changes the fixture). Exit 1 (EXIT_GENERIC) is the
    # pre-fix failure mode and indicates the orchestration layer
    # raised an envelope with ``code="adapter-unparseable-output"``;
    # the assertion explicitly rejects it. Exit 2 (EXIT_USAGE) /
    # 4 (EXIT_ENGINE_MISSING) / 5 (EXIT_STORAGE) all indicate contract
    # or environment violations and MUST not occur on this fixture.
    # See ``src/novetest/cli/output.py:12-17``.
    assert run_result.returncode in (0, 3), (
        f"CLI returned exit {run_result.returncode}; expected 0 "
        f"(EXIT_OK, all passed) or 3 (EXIT_USER_TESTS_FAILED, some "
        f"user tests failed). Exit code 1 (EXIT_GENERIC) is the "
        f"pre-fix defect mode and indicates the adapter emitted an "
        f"``adapter-unparseable-output`` envelope — Fix A "
        f"(directory-type carve-out in cargo_adapter.py) regression. "
        f"Exit codes 2 (EXIT_USAGE), 4 (EXIT_ENGINE_MISSING), 5 "
        f"(EXIT_STORAGE) indicate contract or environment violations. "
        f"See ``src/novetest/cli/output.py:12-17``. "
        f"stdout: {run_result.stdout!r} stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    assert isinstance(envelope["ok"], bool)
    # Negative load-bearing assertion: post-fix MUST NOT carry the
    # pre-fix error code. Without this assertion, an exit-3 envelope
    # whose ``ok`` was True for some other reason (impossible today,
    # but cheap insurance against future contract drift) could pass
    # the exit-code check while still masking the bug.
    error_codes = [err.get("code") for err in envelope.get("errors", [])]
    assert "adapter-unparseable-output" not in error_codes, (
        f"post-fix envelope must not carry the pre-fix error code "
        f"``adapter-unparseable-output`` — Fix A regression. "
        f"envelope: {envelope!r}"
    )
    if envelope["ok"]:
        # Envelope shape per ``src/novetest/cli/app.py:269-281``:
        # ``data = {"memory_entry": entry.to_dict()}``. The
        # ``RunRecord`` lives under ``data.memory_entry.run_record`` —
        # same shape JUnit hotfix #3 corrected (envelope path bug
        # caught by Main Branch's pre-merge gate on 2026-06-04).
        run_record = envelope["data"]["memory_entry"]["run_record"]
        assert run_record["engine_name"] == "cargo-test"
        # target_expression preserved end-to-end: the record carries
        # the literal "." the user typed even though the adapter
        # suppressed it from nextest's argv. The user-facing semantic
        # (run the workspace) and the audit trail (what was requested)
        # are correctly separated.
        assert run_record["target_expression"] == "."
        assert run_record["target_type"] == "directory"


def test_cli_smoke_run_bare_emits_envelope(cli_smoke_workspace: Path) -> None:
    """Control case for ``test_cli_smoke_run_dot_emits_envelope``.

    Pre-fix this case worked (the integration-test ``run_cargo()``
    direct calls covered it). The CLI-level invocation here proves the
    orchestration layer still wires the bare case correctly post-Fix A
    — a regression that broke both ``.`` and bare would be caught
    here too, but the dot-case alone could in principle pass while
    bare regressed (e.g. if a future refactor coupled the bare path
    to the directory-suppression branch incorrectly).

    Together with the dot-case, this triangulates the orchestration
    invariant: ``target_type ∈ {workspace, directory}`` both produce a
    workspace-wide cargo nextest invocation, and both emit a normal
    Run Record envelope.
    """

    _require_cargo_and_nextest()

    init_result = _spawn_novetest(cli_smoke_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(cli_smoke_workspace, ["run"], timeout=300.0)
    assert run_result.returncode in (0, 3), (
        f"CLI returned exit {run_result.returncode}; expected 0 or 3 "
        f"on the canonical fixture. stdout: {run_result.stdout!r} "
        f"stderr: {run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["schema"] == "novetest/v1"
    if envelope["ok"]:
        run_record = envelope["data"]["memory_entry"]["run_record"]
        assert run_record["engine_name"] == "cargo-test"
        # Bare invocation → ``target_type="workspace"``,
        # ``target_expression=""``.
        assert run_record["target_expression"] == ""
        assert run_record["target_type"] == "workspace"
