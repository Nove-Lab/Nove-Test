"""A pytest suite whose tests ERROR in a fixture is not a green suite.

Delivery-phasing row 49, the direct successor to row 45. Row 45 covered the
suite that never *ran* (a module that does not parse: `status="errored"`, zero
results, exit 3). This module covers the suite that ran, produced results, and
still established nothing: pytest-json-report labels a setup/teardown failure
with the singular outcome ``"error"``, which is not in ``FAIL_LIKE_OUTCOMES``,
so before the fix `_aggregate_pytest_status` counted zero failures and the run
normalized to ``status="passed"`` at exit **0** — worse than row 45, which at
least exited 3.

Measured on ``69b1d5c`` before the fix, against
``tests/fixtures/projects/pytest-fixture-error/``:

| target | pre-fix status / exit | post-fix status / exit |
|---|---|---|
| ``tests/test_setup_error.py`` | ``passed`` / 0 | ``failed`` / 3 |
| ``tests/test_teardown_error.py`` | ``passed`` / 0 | ``failed`` / 3 |
| ``tests/test_error_and_failure.py`` | ``failed`` / 3 | ``failed`` / 3 (unmoved) |

Row 56 (the direct successor, second half of this file) adds the failure TEXT
those errored tests carry. Pre-row-56 every one of them had
``failure_reference: null``, because the extractor mined the ``call`` phase
only — a setup error emits no ``call`` key at all and a teardown error emits
a *passing* one.

Scope note: these assertions are deliberately Run-Record-level (status,
per-test outcomes, exit code, failure reference) and say nothing about
``recommendations[]`` — that envelope is orchestration's contract and Manual
Test verifies it end to end. What the Run engine owes the rest of the system
is an honest record.

The payload-level pins (the mapping table itself, the all-error suite, and the
untouched ``exit_code in (2, 3, 5)`` branch) live in
``tests/unit/run/test_normalizer.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Spawn ``[sys.executable, "-m", "novetest", *args]`` in ``workspace``.

    Same canonical shape (``NOVETEST_OUTPUT=json`` + UTF-8) as the sibling
    run-integration smokes (``test_error_classification.py`` /
    ``test_zero_collection_warning.py``).
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


@pytest.fixture
def fixture_error_workspace(tmp_path: Path) -> Path:
    """Copy ``pytest-fixture-error`` so ``novetest init`` writes ``.novetest/``
    into the copy rather than polluting the fixture tree."""

    dest = tmp_path / "pytest-fixture-error"
    shutil.copytree(FIXTURE_ROOT / "pytest-fixture-error", dest)
    init_result = _spawn_novetest(dest, ["init"], timeout=60.0)
    assert init_result.returncode == 0, init_result.stderr
    return dest


def _run_record(workspace: Path, target: str) -> dict[str, object]:
    """``novetest run <target>`` → the persisted Run Record, exit 3 asserted.

    Exit 3 is the honest non-green user result (``ok: true``, empty
    ``errors``), NOT an error envelope — see ``docs/agent/troubleshooting.md``
    "Exit 3 is not an error".
    """

    result = _spawn_novetest(workspace, ["run", target], timeout=300.0)
    assert result.returncode == 3, (
        f"expected exit 3 for a suite with an errored test; got "
        f"{result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["errors"] == []
    memory_entry = envelope["data"]["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    return run_record


def _outcomes(run_record: dict[str, object]) -> list[str]:
    test_results = run_record["test_results"]
    assert isinstance(test_results, list)
    return sorted(str(tr["outcome"]) for tr in test_results)


def test_setup_error_suite_is_a_failed_run(fixture_error_workspace: Path) -> None:
    """A fixture that raises during SETUP plus one passing test: the run is
    ``failed``, and the errored test's outcome is spelled ``errored`` — the
    Run Record's vocabulary, not pytest's singular ``error``.

    This is the exact shape that answered ``[all_green] … (passed 1,
    skipped 0, total 2)`` at exit 0 before the fix.
    """

    run_record = _run_record(fixture_error_workspace, "tests/test_setup_error.py")

    assert run_record["status"] == "failed"
    assert _outcomes(run_record) == ["errored", "passed"]
    # pytest's own `summary` block is passed through verbatim, so the raw
    # singular spelling survives THERE (it is forensic data, not a decision
    # input) while no per-test outcome carries it.
    summary = run_record["summary_counts"]
    assert isinstance(summary, dict)
    assert summary["error"] == 1
    assert summary["total"] == 2


def test_teardown_error_suite_is_a_failed_run(
    fixture_error_workspace: Path,
) -> None:
    """A fixture that raises during TEARDOWN: the test body passed, so pytest
    reports "1 passed, 1 error" — and the run is still ``failed``. One mapping
    covers both phases because pytest resolves both to the same category."""

    run_record = _run_record(fixture_error_workspace, "tests/test_teardown_error.py")

    assert run_record["status"] == "failed"
    assert _outcomes(run_record) == ["errored"]


def test_error_plus_real_failure_suite_is_unmoved(
    fixture_error_workspace: Path,
) -> None:
    """The control row: an error AND a genuine assertion failure. This was
    already reported correctly before the fix (one ``failed`` test makes the
    run non-green by itself), so it is pinned to prove the mapping change did
    not move a shape that was already right."""

    run_record = _run_record(
        fixture_error_workspace, "tests/test_error_and_failure.py"
    )

    assert run_record["status"] == "failed"
    assert _outcomes(run_record) == ["errored", "failed"]


# ---------------------------------------------------------------------------
# Row 56 — the errored test's failure text, end to end
#
# Row 49 (above) made this suite fail-like, which is what makes it reach
# Localization at all; row 56 is what it arrives WITH. Pre-row-56 every
# errored test carried ``failure_reference: null`` on every shape, because the
# extractor mined the ``call`` phase only and an errored test's crash is never
# there. Run-Record-level assertions only — nothing here touches
# ``recommendations[]`` or localization output.
# ---------------------------------------------------------------------------


def _failure_reference(run_record: dict[str, object], outcome: str) -> str:
    """The single ``outcome``-spelled result's ``failure_reference``, asserted
    non-null on the way out."""

    test_results = run_record["test_results"]
    assert isinstance(test_results, list)
    matching = [tr for tr in test_results if tr["outcome"] == outcome]
    assert len(matching) == 1, f"expected exactly one {outcome!r} result: {matching!r}"
    reference = matching[0]["failure_reference"]
    assert isinstance(reference, str), (
        f"{outcome!r} result carries no failure_reference: {matching[0]!r}"
    )
    return reference


def test_setup_error_test_carries_the_fixture_crash_text(
    fixture_error_workspace: Path,
) -> None:
    """The errored test's ``failure_reference`` names the raise site inside
    the SETUP fixture — file, line, and the exception the fixture raises."""

    run_record = _run_record(fixture_error_workspace, "tests/test_setup_error.py")

    reference = _failure_reference(run_record, "errored")
    assert "RuntimeError: warehouse service unavailable" in reference
    # `<path>:<lineno>: ` prefix, from pytest's own `crash` object. The path is
    # the fixture's own module (the raise is in `warehouse_connection`), not
    # the test that merely depends on it.
    assert "test_setup_error.py:" in reference
    # The passing sibling stays clean.
    test_results = run_record["test_results"]
    assert isinstance(test_results, list)
    passed = [tr for tr in test_results if tr["outcome"] == "passed"]
    assert passed[0]["failure_reference"] is None


def test_teardown_error_test_carries_the_fixture_crash_text(
    fixture_error_workspace: Path,
) -> None:
    """The teardown shape: the entry HAS a ``call`` phase and it *passed*, so
    a "look in ``call``" extractor finds nothing. The reference now comes from
    the ``teardown`` phase."""

    run_record = _run_record(fixture_error_workspace, "tests/test_teardown_error.py")

    reference = _failure_reference(run_record, "errored")
    assert "RuntimeError: warehouse session close failed" in reference
    assert "test_teardown_error.py:" in reference


def test_error_and_failure_carry_their_own_phases_crash_text(
    fixture_error_workspace: Path,
) -> None:
    """Both halves of the mixed module at once: the errored test gets the
    setup crash (new), the genuinely failing test keeps its ``call``-phase
    assertion text (unmoved — this one was already correct pre-row-56)."""

    run_record = _run_record(
        fixture_error_workspace, "tests/test_error_and_failure.py"
    )

    errored_reference = _failure_reference(run_record, "errored")
    assert "RuntimeError: warehouse service unavailable" in errored_reference
    failed_reference = _failure_reference(run_record, "failed")
    assert "assert 8 == 99" in failed_reference
