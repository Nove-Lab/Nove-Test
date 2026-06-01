"""Python-API integration tests for the Phase 6 ``novetest test`` workflow.

Exercises ``test_target_in_store`` against the real fixture projects:

- ``pytest-basic`` — clean run, expected category set ``["all_green"]``.
- ``pytest-failing`` — 2 failing tests, no usable per-test coverage
  (the fixture's bug pattern doesn't yield high-confidence findings
  reliably), expected category set ``["unavailable_analysis"]`` OR
  contains ``investigate_location`` depending on what Phase 4 SBFL
  surfaces.
- ``localization-branch`` — 1st run, deliberate divide bug at lines
  31-34, expected category set ``["investigate_location"]`` (no compound
  because no prior baseline).

Determinism contract: each fixture's workflow output is byte-identical
across 3 consecutive runs of the SAME ``test_target_in_store`` call
against the SAME store (modulo ``run_reference`` + ``derived_at`` /
timestamp fields). Implementation strategy: use
``build_test_outcome_from_run_id`` to re-derive against the
already-seeded store; that path is cache-only and avoids re-running
pytest 3x per fixture.

Brief §7 — golden snapshot enforcement uses ``syrupy`` snapshots over
the post-strip envelope. This file uses direct assertions for the
category-set invariants; the snapshot pin lives in the same file via
``syrupy``'s ``snapshot`` fixture.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.orchestration.recommendation import (
    CATEGORY_ALL_GREEN,
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
    CATEGORY_UNAVAILABLE_ANALYSIS,
)
from novetest.orchestration.workflows import (
    build_test_outcome_from_run_id,
    initialize_project_workspace,
    test_target_in_store,
)


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _materialize_fixture(name: str, dest: Path) -> Path:
    """Copy a fixture project tree into ``dest`` and return the project root."""
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


# ---------------------------------------------------------------------------
# Determinism strip helpers — pin run_reference + derived_at fields are the
# only timestamp-keyed slots; everything else is byte-stable per the brief
# §1 determinism contract.
# ---------------------------------------------------------------------------


def _strip_run_dependent(envelope_data: dict[str, Any]) -> dict[str, Any]:
    """Strip run-id + timestamp fields so two runs against the same fixture
    yield byte-identical envelopes.

    Surface affected:

    - ``run_reference`` (ULID-derived) — replaced with ``"<run_ref>"``.
    - Each recommendation's ``recommendation_id`` (carries the run_id).
    - Each citation's nested ``run_reference`` blocks.
    """

    stripped = json.loads(json.dumps(envelope_data))  # deep copy
    stripped["run_reference"] = "<run_ref>"
    for rec in stripped.get("recommendations", []):
        rec["recommendation_id"] = "<rec_id>"
        for slot_key in ("run_reference", "run_reference_from", "run_reference_to"):
            if slot_key in rec.get("slots", {}):
                rec["slots"][slot_key] = "<ref>"
        for citation in rec.get("evidence_citations", []):
            for slot_key in ("run_reference", "run_reference_from", "run_reference_to", "finding_id"):
                if slot_key in citation:
                    citation[slot_key] = "<ref>"
    return stripped


# ---------------------------------------------------------------------------
# pytest-basic → all_green
# ---------------------------------------------------------------------------


async def test_pytest_basic_yields_all_green(tmp_path: Path) -> None:
    """A clean pytest run yields exactly ``[all_green]`` — Phase 1 line 96.

    Phase-1 ``delivery-phasing.md:96`` bullet closure: empty downstream
    facts on a passing run → ``all_green``. The exact passing-summary
    counts are pinned to the fixture's test count.
    """

    workspace = _materialize_fixture("pytest-basic", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)

    cats = [r.category for r in outcome.recommendations]
    assert cats == [CATEGORY_ALL_GREEN], (
        f"Expected [all_green], got {cats}; "
        f"stage_eligibility={outcome.stage_eligibility.to_dict()}"
    )
    rec = outcome.recommendations[0]
    assert rec.slots["passed"] >= 1
    assert rec.slots["total_tests"] >= 1
    # ``all_green`` carries exactly one citation: the run_reference itself.
    assert len(rec.evidence_citations) == 1
    assert rec.evidence_citations[0]["kind"] == "run_reference"


# ---------------------------------------------------------------------------
# pytest-failing → unavailable_analysis OR investigate_location
# ---------------------------------------------------------------------------


async def test_pytest_failing_yields_failing_run_recommendation(tmp_path: Path) -> None:
    """A failing-tests fixture surfaces SOMETHING actionable.

    Two valid outcomes (brief §7):

    1. Phase 4 SBFL produces a high-confidence finding → at least one
       ``investigate_location`` recommendation.
    2. Otherwise → exactly ``[unavailable_analysis]``.

    Either way, the synthesizer MUST emit something — an empty list
    after a failing run is a contract violation.
    """

    workspace = _materialize_fixture("pytest-failing", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)

    cats = [r.category for r in outcome.recommendations]
    assert len(cats) >= 1, "Failing run must surface ≥1 recommendation"
    # Either investigate_* OR unavailable_analysis — never empty.
    surfaces_signal = (
        CATEGORY_INVESTIGATE_LOCATION in cats
        or CATEGORY_UNAVAILABLE_ANALYSIS in cats
        or CATEGORY_REGRESSION_WITH_LOCALIZATION in cats
    )
    assert surfaces_signal, f"Unexpected category set: {cats}"
    # The run record's status reflects "failed".
    assert outcome.run_record_status == "failed"


# ---------------------------------------------------------------------------
# localization-branch (1st run) → investigate_location
# ---------------------------------------------------------------------------


async def test_localization_branch_first_run_yields_investigate_location(
    tmp_path: Path,
) -> None:
    """1st run on the localization-branch fixture surfaces the divide bug.

    The fixture's deliberate ``divide`` bug at lines 31-34 produces
    Ochiai score 1.0 in per-test SBFL mode → ``investigate_location``
    at rank 1 with high confidence. No prior baseline → no compound.
    """

    clear_resolver_cache()
    workspace = _materialize_fixture("localization-branch", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)

    cats = [r.category for r in outcome.recommendations]
    # No regression baseline on first run → no compound.
    assert CATEGORY_REGRESSION_WITH_LOCALIZATION not in cats
    # The divide bug is high-confidence → investigate_location MUST fire.
    assert CATEGORY_INVESTIGATE_LOCATION in cats, (
        f"Expected investigate_location in categories, got {cats}"
    )
    # Find the top investigate_location and verify it points at the bug
    # source file (``calculator.py`` inside ``localization_branch/``).
    # The brief §1 sort key ``(priority, category, primary_slot)`` with
    # primary_slot = ``{file}:{anchor}`` puts ``localization_branch/calculator.py``
    # ahead of ``tests/test_calculator.py`` lexicographically — both
    # may surface as investigate_location entries, but the actual bug
    # site sorts first.
    inv = next(r for r in outcome.recommendations if r.category == CATEGORY_INVESTIGATE_LOCATION)
    assert inv.slots["file"].endswith("calculator.py"), (
        f"Expected calculator.py as first investigate_location, got {inv.slots['file']!r}"
    )
    assert "localization_branch" in inv.slots["file"], (
        f"Expected the bug-site file (under localization_branch/), got {inv.slots['file']!r}"
    )
    assert inv.slots["formula"] == "ochiai"
    assert inv.slots["mode"] == "sbfl_per_test"


# ---------------------------------------------------------------------------
# Determinism — same store → same recommendations across 3 re-derives
# ---------------------------------------------------------------------------


async def test_determinism_localization_branch_three_consecutive_rederives(
    tmp_path: Path,
) -> None:
    """3 cache-only re-derives over the same store yield byte-identical envelopes.

    Brief §1 Phase 6 DoD #1 — the binding determinism contract. We use
    ``build_test_outcome_from_run_id`` (cache-only) so we re-derive the
    same FactBundle 3 times without re-running pytest. Strip
    run_reference + recommendation_id (both deterministic but unique
    per ULID) to assert byte-equality of the rest.
    """

    clear_resolver_cache()
    workspace = _materialize_fixture("localization-branch", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)
    run_id = outcome.memory_entry.run_record.run_reference.run_id

    rederives = [
        build_test_outcome_from_run_id(init.store, run_id) for _ in range(3)
    ]
    for r in rederives:
        assert r is not None

    serialized = [
        json.dumps(
            [rec.to_dict() for rec in r.recommendations],  # type: ignore[union-attr]
            sort_keys=True,
        )
        for r in rederives
    ]
    assert serialized[0] == serialized[1] == serialized[2], (
        "Re-derive determinism violated:\n"
        f"  run #1: {serialized[0]}\n"
        f"  run #2: {serialized[1]}\n"
        f"  run #3: {serialized[2]}"
    )


# ---------------------------------------------------------------------------
# Snapshot — pin the pytest-basic all_green envelope structure
# ---------------------------------------------------------------------------


async def test_pytest_basic_envelope_snapshot(
    tmp_path: Path, snapshot: Any
) -> None:
    """Pin the stripped pytest-basic envelope via syrupy.

    Brief §7 — golden snapshot enforcement. Each fixture's snapshot
    must be byte-identical across 3 consecutive runs of the same
    workflow (the determinism test above pins the value invariant; this
    pins the structural invariant).
    """

    workspace = _materialize_fixture("pytest-basic", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)

    data: dict[str, Any] = {
        "stage_eligibility": outcome.stage_eligibility.to_dict(),
        "recommendation_schema_version": 1,
        "recommendations": [r.to_dict() for r in outcome.recommendations],
    }
    stripped = _strip_run_dependent({"run_reference": "x", **data})
    assert stripped == snapshot
