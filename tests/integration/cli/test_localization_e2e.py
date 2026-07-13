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


# ---------------------------------------------------------------------------
# E2E Test 5: failure_proximity formula-noop warning (Defect 7 fix,
# 2026-06-08).
#
# Pre-Defect-7: a no-coverage run that triggers ``failure_proximity`` mode
# pinned ``finding.formula = "ochiai"`` as a structural placeholder. Any
# user passing ``--formula <non-ochiai>`` against that cached finding
# triggered an infinite warning loop: every retry unlinked the cache,
# re-derived, got the same placeholder back, and emitted the
# ``localization-cache-rederived`` warning again.
#
# Post-Defect-7: the CLI recognizes the structural-noop case and emits a
# distinct ``localization-formula-noop-in-mode`` warning WITHOUT
# re-deriving (no cache invalidation either). This subprocess test
# reproduces the original Defect 7 trigger end-to-end against the
# ``localization-no-coverage`` fixture and pins the wire-level behavior.
# ---------------------------------------------------------------------------


_NO_COVERAGE_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "projects"
    / "localization-no-coverage"
)


def _materialize_no_coverage_fixture(dest: Path) -> Path:
    """Copy the no-coverage fixture project tree into ``dest``."""
    target = dest / "localization-no-coverage"
    shutil.copytree(
        _NO_COVERAGE_FIXTURE_ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


@pytest.fixture(scope="module")
def seeded_no_coverage_workspace(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, object]:
    """Materialize the no-coverage fixture, run WITHOUT coverage, derive
    localization findings — exercises the ``failure_proximity`` mode path.

    Module-scoped so the expensive pytest subprocess runs once.
    """
    tmp = tmp_path_factory.mktemp("loc_e2e_no_cov")
    workspace = _materialize_no_coverage_fixture(tmp)
    clear_resolver_cache()

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        init = loop.run_until_complete(initialize_project_workspace(workspace))
        # CRITICAL: ``collect_coverage=False`` so the run has no
        # CoverageFactSet — that's what pushes the engine into
        # ``failure_proximity`` mode.
        outcome = loop.run_until_complete(
            run_target_in_store(
                "tests/", init.store, timeout=120.0, collect_coverage=False
            )
        )
    finally:
        loop.close()

    run_reference = outcome.memory_entry.run_record.run_reference
    finding = derive_localization_findings(init.store, run_reference)

    return {
        "workspace": workspace,
        "run_id": run_reference.run_id,
        "run_reference": run_reference,
        "store": init.store,
        "finding": finding,
    }


def test_localization_failure_proximity_non_default_formula_emits_noop_warning(
    seeded_no_coverage_workspace: dict[str, object],
) -> None:
    """``novetest localization <run_id> --formula op2`` against a
    failure_proximity-mode finding emits exactly ONE
    ``localization-formula-noop-in-mode`` warning, exit 0, and DOES NOT
    re-derive (the engine's placeholder formula stays ``"ochiai"``).

    Defect 7 reproduction: pre-Defect-7 the same invocation would have
    triggered a ``localization-cache-rederived`` warning AND re-derived;
    a second invocation would have repeated the same warning, forming the
    infinite loop. Post-Defect-7 a single noop warning is emitted and the
    cache file on disk is left untouched.

    This is the load-bearing wire-level assertion the 2026-06-08 task
    brief DoD #4 requires."""

    workspace = seeded_no_coverage_workspace["workspace"]
    run_id = seeded_no_coverage_workspace["run_id"]

    # Capture the cache file's mtime BEFORE the noop call so we can assert
    # below that it was NOT touched by the request.
    cache_path = (
        workspace
        / ".novetest"
        / "localization"
        / "findings"
        / f"run_{run_id}"
        / "localization_findings.json"
    )
    assert cache_path.exists(), (
        "Test precondition broken: failure_proximity derive should have "
        f"persisted a findings file at {cache_path}"
    )
    pre_mtime = cache_path.stat().st_mtime

    code, envelope, stderr = _run_cli(
        workspace, ["localization", run_id, "--formula", "op2"]
    )
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("command") == "localization"
    assert envelope.get("ok") is True

    data = envelope.get("data")
    assert isinstance(data, dict)
    outcome = data.get("localization_outcome")
    assert isinstance(outcome, dict)
    # Engine's placeholder is preserved — user sees what the engine
    # actually computed, not a fictional ``formula="op2"`` finding.
    assert outcome["kind"] == "fact-set"
    assert outcome["mode"] == "failure_proximity"
    assert outcome["formula"] == "ochiai", (
        f"Expected placeholder formula='ochiai' in failure_proximity, got "
        f"{outcome.get('formula')!r}"
    )

    warnings = envelope.get("warnings")
    assert isinstance(warnings, list)
    assert len(warnings) == 1, (
        f"Expected exactly one noop warning, got {warnings!r}"
    )
    warning = warnings[0]
    assert warning["code"] == "localization-formula-noop-in-mode"
    assert "op2" in warning["message"]
    assert "failure_proximity" in warning["message"]
    details = warning["details"]
    assert details["requested_formula"] == "op2"
    assert details["returned_formula"] == "ochiai"
    assert details["mode"] == "failure_proximity"

    # Load-bearing no-loop evidence: the cache file's mtime is
    # unchanged. Pre-Defect-7 the same call would have unlinked + re-
    # written this file. Same-mtime + same on-disk content == no
    # re-derive ran.
    assert cache_path.exists(), (
        "Cache file disappeared — Defect 7 carve-out is supposed to "
        "SKIP the re-derive (which includes the unlink). The file must "
        "still be on disk post-call."
    )
    assert cache_path.stat().st_mtime == pre_mtime, (
        "Cache file mtime changed — Defect 7 carve-out is supposed to "
        "leave the on-disk findings untouched."
    )


def test_localization_failure_proximity_default_formula_no_warning(
    seeded_no_coverage_workspace: dict[str, object],
) -> None:
    """Symmetric companion to the noop-warning test: a user who does NOT
    pass ``--formula`` against the same failure_proximity run sees NO
    warning. Regression-pin that the noop carve-out doesn't fire on the
    default path."""

    workspace = seeded_no_coverage_workspace["workspace"]
    run_id = seeded_no_coverage_workspace["run_id"]

    code, envelope, stderr = _run_cli(workspace, ["localization", run_id])
    assert code == 0, f"Expected exit 0, got {code}. stderr={stderr!r}"
    assert envelope.get("ok") is True

    outcome = envelope["data"]["localization_outcome"]
    assert outcome["mode"] == "failure_proximity"
    assert outcome["formula"] == "ochiai"

    warnings = envelope.get("warnings")
    assert warnings == [], (
        f"Default-formula failure_proximity should emit no warnings; got "
        f"{warnings!r}"
    )


# ---------------------------------------------------------------------------
# S30 — SBFL score correctness against the REAL per-test payload.
# ---------------------------------------------------------------------------


def test_per_test_context_nodeids_all_attested_by_run_record(
    seeded_workspace: dict[str, object],
) -> None:
    """S30/ANA-11 load-bearing assumption guard: every nodeid in the real
    coverage.py per-test contexts matches a Run Record ``test_result``
    node_id.

    ``build_spectra`` now EXCLUDES discovered nodeids outside the
    failed/passed outcome sets; if the pytest adapter's context ids ever
    drifted from the normalizer's node_ids, real passing tests would be
    silently dropped from the SBFL sample. This guard makes that drift
    loud at the integration boundary.
    """
    from novetest.coverage.retrieval import get_coverage_facts
    from novetest.memory.store import retrieve_run_evidence

    store = seeded_workspace["store"]
    run_reference = seeded_workspace["run_reference"]

    entry = retrieve_run_evidence(store, run_reference)
    record_node_ids = {tr.node_id for tr in entry.run_record.test_results}

    coverage = get_coverage_facts(store, run_reference)
    context_nodeids: set[str] = set()
    for file_cov in coverage.files:
        for nodeids in file_cov.line_contexts.values():
            context_nodeids.update(nodeids)

    assert context_nodeids, "per-test fixture must attest context nodeids"
    unattested = context_nodeids - record_node_ids
    assert not unattested, (
        f"Coverage context nodeids missing from the Run Record: "
        f"{sorted(unattested)!r} — the ANA-11 exclusion contract would "
        f"silently drop these from the SBFL sample"
    )


def test_dstar2_alternate_score_is_positive_for_the_bug_symbol(
    seeded_workspace: dict[str, object],
) -> None:
    """S30/ANA-10 e2e pin: ``divide`` (covered by every failing test and no
    passing test → D* denominator 0) carries a POSITIVE, finite
    ``alternate_scores.dstar2`` on the real fixture. Pre-S30 this slot was
    filled with 0.0 — minimum suspicion for the true bug site."""
    import math

    from novetest.models.localization_finding import LocalizationFinding

    finding = seeded_workspace["finding"]
    assert isinstance(finding, LocalizationFinding)
    top = finding.entries[0]
    assert top.code_location.symbol == "divide"
    dstar2_score = top.alternate_scores["dstar2"]
    assert dstar2_score > 0.0
    assert math.isfinite(dstar2_score)
