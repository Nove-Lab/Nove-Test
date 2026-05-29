"""Integration test for the cargo adapter against the ``cargo-test-basic``
fixture.

Spawns **real** ``cargo nextest run`` subprocesses. Skips when either
``cargo`` or ``cargo-nextest`` is absent. The current CI matrix has no
Rust cell yet, so this test is expected to skip on every CI runner; it
is intended for local-dev exercise and the matrix-extension follow-up
(Release team).
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
