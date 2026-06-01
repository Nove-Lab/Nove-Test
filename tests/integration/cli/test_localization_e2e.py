"""Subprocess E2E tests for the Phase 4 Localization CLI verbs.

Verbs covered:

- ``novetest localization <run_id>``
- ``novetest localization latest``
- ``novetest inspect <run_id>`` (localization_outcome section)

Strategy: materialize the ``localization-branch`` fixture under ``tmp_path``,
initialize a Project Store, execute a real pytest run with per-test coverage
(via the run orchestration layer — same path the branch-basic integration test
uses), then derive localization findings, and finally verify the three verbs
against the real on-disk store. The localization fixture's deliberate
``divide`` bug yields Ochiai score 1.0 for the ``divide`` symbol — the E2E
assertions pin this deterministic value.

NOTE: These tests require ``localization <run_id>`` and
``localization latest`` to be registered in ``cli/app.py``. If the
handlers are not yet present, each subprocess call will exit non-zero
with "Unknown command" and the assertions will fail.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.localization import derive_localization_findings
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory.project_store import create_project_store
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


# ---------------------------------------------------------------------------
# Fixture materialisation helpers
# ---------------------------------------------------------------------------


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "localization-branch"
)


def _materialize_fixture(dest: Path) -> Path:
    """Copy the fixture project tree into ``dest`` and return the project root."""
    target = dest / "localization-branch"
    shutil.copytree(
        _FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


def _run_cli(workspace: Path, args: list[str]) -> tuple[int, dict[str, object], str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    result = subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload: dict[str, object] = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, payload, result.stderr


# ---------------------------------------------------------------------------
# Shared setup: one seeded + derived store per module via a session-scoped
# tmp_path analogue. Since pytest's tmp_path is function-scoped we use a
# module-scoped fixture that does all the expensive work (real pytest
# subprocess + SBFL derivation) once.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_workspace(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """Materialize the fixture, run with coverage, derive localization findings.

    Returns a dict with:
    - ``workspace``: the project root (cwd for CLI invocations)
    - ``run_id``: the ``run_id`` of the run that was derived
    - ``run_reference``: the ``RunReference`` object

    This fixture is module-scoped so the expensive pytest subprocess runs
    once per test module, not once per test.
    """
    tmp = tmp_path_factory.mktemp("loc_e2e")
    workspace = _materialize_fixture(tmp)
    clear_resolver_cache()

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        init = loop.run_until_complete(initialize_project_workspace(workspace))
        outcome = loop.run_until_complete(
            run_target_in_store("tests/", init.store, timeout=120.0, collect_coverage=True)
        )
    finally:
        loop.close()

    run_reference = outcome.memory_entry.run_record.run_reference

    # Pre-derive localization findings so the cache is populated for all
    # three tests (the ``localization <run_id>`` test also exercises the
    # cache-aware derive, so it doesn't matter if we call it here first —
    # both calls must return the same finding).
    finding = derive_localization_findings(init.store, run_reference)

    return {
        "workspace": workspace,
        "run_id": run_reference.run_id,
        "run_reference": run_reference,
        "store": init.store,
        "finding": finding,
    }


# ---------------------------------------------------------------------------
# E2E Test 1: localization <run_id> → fact-set, divide top-1, score 1.0
# ---------------------------------------------------------------------------


def test_localization_run_id_e2e_emits_fact_set(
    seeded_workspace: dict[str, object],
) -> None:
    """``novetest localization <run_id>`` against the localization-branch
    fixture: emits ``kind: "fact-set"``, the top-1 entry is the ``divide``
    symbol with Ochiai score 1.0."""

    workspace = seeded_workspace["workspace"]
    run_id = seeded_workspace["run_id"]

    code, envelope, stderr = _run_cli(workspace, ["localization", run_id])
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("command") == "localization"
    assert envelope.get("ok") is True

    data = envelope.get("data")
    assert isinstance(data, dict)
    outcome = data.get("localization_outcome")
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert "schema_version" not in outcome

    entries = outcome.get("entries")
    assert isinstance(entries, list)
    assert len(entries) >= 1
    top = entries[0]
    assert top["rank"] == 1
    assert top["score_raw"] == 1.0
    code_location = top["code_location"]
    assert isinstance(code_location, dict)
    assert code_location["symbol"] == "divide"
    assert code_location["file"].endswith("calculator.py")
    # evidence_lines is inside code_location, NOT a top-level entry key.
    assert "evidence_lines" in code_location
    assert "evidence_lines" not in top


# ---------------------------------------------------------------------------
# E2E Test 2: localization latest → byte-equivalent to run_id variant
# ---------------------------------------------------------------------------


def test_localization_latest_e2e_emits_same_finding(
    seeded_workspace: dict[str, object],
) -> None:
    """``novetest localization latest`` against the same store should pick
    the same run and emit the same ``kind: "fact-set"`` with the same
    top-1 ``divide`` entry. Since there's only one run in the store, the
    latest-resolution always resolves to it."""

    workspace = seeded_workspace["workspace"]
    run_id = seeded_workspace["run_id"]

    code, envelope, stderr = _run_cli(workspace, ["localization", "latest"])
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("command") == "localization.latest"
    assert envelope.get("ok") is True

    data = envelope.get("data")
    assert isinstance(data, dict)
    outcome = data.get("localization_outcome")
    assert isinstance(outcome, dict)
    assert outcome["kind"] == "fact-set"
    assert outcome["run_reference"]["run_id"] == run_id

    entries = outcome.get("entries")
    assert isinstance(entries, list)
    top = entries[0]
    assert top["rank"] == 1
    assert top["score_raw"] == 1.0
    assert top["code_location"]["symbol"] == "divide"


# ---------------------------------------------------------------------------
# E2E Test 3: inspect <run_id> after derive → localization_outcome.kind=="fact-set"
# ---------------------------------------------------------------------------


def test_inspect_after_localization_derive_shows_fact_set(
    seeded_workspace: dict[str, object],
) -> None:
    """After ``derive_localization_findings`` has been called, ``inspect
    <run_id>`` should reflect the cached findings: ``localization_outcome.
    kind == "fact-set"`` and ``sub_reports.localization == "available"``."""

    workspace = seeded_workspace["workspace"]
    run_id = seeded_workspace["run_id"]

    code, envelope, stderr = _run_cli(workspace, ["inspect", run_id])
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("command") == "inspect"
    assert envelope.get("ok") is True

    data = envelope.get("data")
    assert isinstance(data, dict)

    loc_outcome = data.get("localization_outcome")
    assert isinstance(loc_outcome, dict)
    assert loc_outcome["kind"] == "fact-set", (
        f"Expected fact-set after derivation, got: {loc_outcome!r}"
    )
    assert "schema_version" not in loc_outcome

    sub_reports = data.get("sub_reports")
    assert isinstance(sub_reports, dict)
    assert sub_reports.get("localization") == "available", (
        f"Expected localization=available, got: {sub_reports!r}"
    )


# ---------------------------------------------------------------------------
# E2E Test 4: cache-rederived warning + behavioral re-derive on --formula change
# (Defect 5 fix, 2026-06-01).
#
# Pre-Defect-5: ``--formula=dstar2`` against an Ochiai cache silently
# returned the stale Ochiai finding + a ``localization-cache-args-ignored``
# warning (the warning disclosed the bug; the behavior was still wrong).
# Post-Defect-5: the cache is invalidated, the engine re-derives at
# ``dstar2``, the fresh ``dstar2`` finding is returned, and the warning
# becomes ``localization-cache-rederived`` carrying the previous (formula,
# top_n) for audit.
#
# Reproduces the Manual Test 2026-06-01 §"Defect 5 surfaced" reproduction
# end-to-end against the localization-branch fixture.
# ---------------------------------------------------------------------------


def test_localization_latest_rederives_when_explicit_flag_overrides_cache(
    seeded_workspace: dict[str, object],
) -> None:
    """``novetest localization latest --formula dstar2`` against a store
    whose cache was derived with the default ``ochiai`` formula:

    - The cache is invalidated and ``derive_localization_findings`` runs
      fresh at ``dstar2``. The returned envelope reports
      ``outcome.formula == "dstar2"`` (top-1 is still ``divide`` — the
      bug site is formula-invariant for this fixture — but the
      ``alternate_scores_available`` field NO LONGER lists ``dstar2``
      since it is now the primary formula).
    - The on-disk ``localization_findings.json`` is overwritten with the
      fresh payload — a follow-up ``localization`` call with no flags
      would now return ``dstar2`` (cache-as-source-of-truth).
    - The envelope-level ``warnings`` tuple carries exactly one
      ``localization-cache-rederived`` warning with
      ``details.previous.formula == "ochiai"`` /
      ``details.previous.top_n == 10`` and ``details.requested.formula ==
      "dstar2"`` / ``details.requested.formula_explicit == True``.

    Mirrors the Manual Test 2026-06-01 §"Defect 5 surfaced" reproduction;
    closes Defect 5 task brief §"Empirical reproduction" end-to-end."""

    workspace = seeded_workspace["workspace"]
    run_id = seeded_workspace["run_id"]

    code, envelope, stderr = _run_cli(
        workspace, ["localization", "latest", "--formula", "dstar2"]
    )
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("command") == "localization.latest"
    assert envelope.get("ok") is True

    data = envelope.get("data")
    assert isinstance(data, dict)
    outcome = data.get("localization_outcome")
    assert isinstance(outcome, dict)
    # Fresh findings returned — formula reflects the user's --formula=dstar2
    # request, NOT the previously-cached ochiai.
    assert outcome["kind"] == "fact-set"
    assert outcome["formula"] == "dstar2", (
        f"Expected re-derived dstar2 formula, got: {outcome.get('formula')!r}"
    )
    # ``dstar2`` is now the primary formula and thus drops out of the
    # ``alternate_scores_available`` set (it always lists the OTHER three).
    assert "dstar2" not in outcome["alternate_scores_available"]
    assert set(outcome["alternate_scores_available"]) == {
        "ochiai",
        "op2",
        "tarantula",
    }

    entries = outcome.get("entries")
    assert isinstance(entries, list)
    assert len(entries) >= 1
    top = entries[0]
    assert top["rank"] == 1
    assert top["formula"] == "dstar2", (
        f"Each entry's primary formula must reflect the re-derive selection; "
        f"got {top.get('formula')!r}"
    )
    # The top suspect lives in the fixture under test (``calculator.py``).
    # We intentionally do NOT pin the symbol name here — DStar2 weighs
    # ef^2 differently from Ochiai and may surface a symbol other than
    # ``divide`` at rank 1 for ties. The Defect-5 invariant under test is
    # "re-derive happened with the new formula", not "DStar2 picks divide".
    assert top["code_location"]["file"].endswith("calculator.py")

    # The on-disk cache file is overwritten — a follow-up call with no
    # flags would now return dstar2 (cache-as-source-of-truth post-rederive).
    follow_up_code, follow_up_envelope, follow_up_stderr = _run_cli(
        workspace, ["localization", "latest"]
    )
    assert follow_up_code == 0, (
        f"Follow-up call failed: stderr={follow_up_stderr!r}"
    )
    follow_up_outcome = follow_up_envelope["data"]["localization_outcome"]
    assert follow_up_outcome["formula"] == "dstar2", (
        "Cache should have been overwritten with the re-derived dstar2 finding; "
        f"follow-up reads back {follow_up_outcome.get('formula')!r}"
    )

    warnings = envelope.get("warnings")
    assert isinstance(warnings, list)
    assert len(warnings) == 1, (
        f"Expected exactly one cache-rederived warning, got {warnings!r}"
    )
    warning = warnings[0]
    assert warning["code"] == "localization-cache-rederived"
    assert "--formula='dstar2'" in warning["message"]
    assert "--formula='ochiai'" in warning["message"]
    assert "cache overwritten" in warning["message"]

    details = warning["details"]
    assert details["previous"]["formula"] == "ochiai"
    assert details["previous"]["top_n"] == 10  # engine default
    assert details["requested"]["formula"] == "dstar2"
    assert details["requested"]["formula_explicit"] is True
    assert details["requested"]["top_n_explicit"] is False
    expected_path = (
        f".novetest/localization/findings/run_{run_id}/localization_findings.json"
    )
    assert details["cache_path"] == expected_path
