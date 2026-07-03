"""NFR-ORCH-002 round-trip verification.

For the ``localization-branch`` fixture, run the integrated
``novetest test`` workflow, pick the first ``investigate_location``
recommendation, and resolve every ``evidence_citation`` back to its
canonical retrieval interface. Each citation MUST round-trip to a
non-null fact AND the slot values in the recommendation MUST match the
resolved fact.

Brief §8 — the canonical NFR-ORCH-002 evidence pin. Future changes that
break citation traceability fail this gate loudly.

Per-kind retrieval interfaces:

- ``localization_finding`` → ``localization/get_localization_findings(run_ref)``
- ``coverage_fact`` → ``coverage/get_coverage_facts(run_ref)``
- ``regression_fact`` → ``regression/get_regression_facts(baseline_ref, target_ref)``
- ``replay_result`` → ``replay/get_replay_result(run_ref)`` (reachable via
  ``novetest test --reruns N`` since the 2026-06-25 integration cycle)
- ``test_result`` → ``memory/retrieve_run_evidence(run_ref)`` + find by ``test_id``
- ``run_reference`` → ``memory/list_run_history()`` + verify in history
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from novetest.coverage import get_coverage_facts
from novetest.localization import LocalizationFinding, get_localization_findings
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory import list_run_history, retrieve_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.replay_result import ReplayResult
from novetest.models.run_reference import RunReference
from novetest.replay import get_replay_result
from novetest.orchestration.recommendation import (
    CATEGORY_INVESTIGATE_LOCATION,
    CATEGORY_REGRESSION_WITH_LOCALIZATION,
)
from novetest.orchestration.workflows import (
    initialize_project_workspace,
    test_target_in_store,
)
from novetest.regression import RegressionFactSet, get_regression_facts


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _materialize_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


def _resolve_run_reference(citation: dict[str, object]) -> RunReference | None:
    """Reconstruct a RunReference from a citation's ``run_reference`` block."""

    ref_dict = citation.get("run_reference")
    if isinstance(ref_dict, dict):
        return RunReference.from_dict(dict(ref_dict))
    return None


async def test_investigate_location_citations_round_trip(tmp_path: Path) -> None:
    """Every citation on an ``investigate_location`` recommendation resolves.

    Phase 6 brief §8 — NFR-ORCH-002 evidence pin. The
    ``localization-branch`` fixture is the canonical reproducer
    (high-confidence per-test SBFL, ochiai=1.0 on the divide bug).
    """

    clear_resolver_cache()
    workspace = _materialize_fixture("localization-branch", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)
    store = init.store

    inv = next(
        (r for r in outcome.recommendations if r.category == CATEGORY_INVESTIGATE_LOCATION),
        None,
    )
    assert inv is not None, (
        f"Expected investigate_location in recommendations; got "
        f"{[r.category for r in outcome.recommendations]}"
    )
    assert len(inv.evidence_citations) >= 1, (
        "REQ-ORCH-005: every recommendation MUST carry ≥1 evidence citation"
    )

    for citation in inv.evidence_citations:
        kind = citation["kind"]
        if kind == "localization_finding":
            ref = _resolve_run_reference(citation)
            assert ref is not None
            resolved = get_localization_findings(store, ref)
            assert isinstance(resolved, LocalizationFinding), (
                f"Citation {citation!r} did not resolve to a LocalizationFinding"
            )
            # Cross-check on (file, primary_line) — these are the
            # discriminator slots the synthesizer encodes and the
            # citation carries. Resolving by rank alone is ambiguous
            # when SBFL produces ties (Ochiai = 1.0 hits the same rank
            # on multiple co-suspect files), so the round-trip uses
            # the unambiguous (file, primary_line) pair instead.
            selector = citation.get("selector") or {}
            target_file = selector.get("file")
            target_line = selector.get("primary_line")
            entry = next(
                (
                    e
                    for e in resolved.entries
                    if e.code_location.file == target_file
                    and e.code_location.primary_line == target_line
                ),
                None,
            )
            assert entry is not None, (
                f"Localization citation selector (file={target_file!r}, "
                f"primary_line={target_line!r}) did not resolve to any "
                f"finding entry. Entries={[(e.code_location.file, e.code_location.primary_line) for e in resolved.entries]!r}"
            )
            # Slot values match the resolved finding.
            assert entry.code_location.file == inv.slots["file"]
            assert entry.code_location.primary_line == inv.slots["primary_line"]
            assert entry.formula == inv.slots["formula"]
        elif kind == "test_result":
            ref = _resolve_run_reference(citation)
            assert ref is not None
            entry = retrieve_run_evidence(store, ref)
            test_id = citation["test_id"]
            test_results = entry.run_record.test_results
            match = next((tr for tr in test_results if tr.node_id == test_id), None)
            assert match is not None, (
                f"test_result citation {citation!r} did not resolve to a TestResult"
            )
        elif kind == "coverage_fact":
            ref = _resolve_run_reference(citation)
            assert ref is not None
            resolved_cov = get_coverage_facts(store, ref)
            assert isinstance(resolved_cov, CoverageFactSet), (
                f"coverage_fact citation {citation!r} did not resolve"
            )
        elif kind == "regression_fact":
            # Investigate_location does NOT emit regression_fact citations;
            # if we ever do, resolve via get_regression_facts here.
            baseline = citation.get("run_reference_from")
            target = citation.get("run_reference_to")
            assert isinstance(baseline, dict) and isinstance(target, dict)
            br = RunReference.from_dict(dict(baseline))
            tr = RunReference.from_dict(dict(target))
            resolved_reg = get_regression_facts(store, br, tr)
            assert isinstance(resolved_reg, RegressionFactSet)
        elif kind == "run_reference":
            ref = _resolve_run_reference(citation)
            assert ref is not None
            history = list_run_history(store)
            assert any(
                e.run_record.run_reference.run_id == ref.run_id for e in history
            ), f"run_reference citation {citation!r} not in run history"
        elif kind == "replay_result":
            # Reachable since the 2026-06-25 ``--reruns`` integration:
            # resolve via the canonical cache-read interface.
            ref = _resolve_run_reference(citation)
            assert ref is not None
            resolved_replay = get_replay_result(store, ref)
            assert isinstance(resolved_replay, ReplayResult), (
                f"replay_result citation {citation!r} did not resolve"
            )
        else:
            pytest.fail(f"Unknown citation kind: {kind!r}")


async def test_every_recommendation_has_at_least_one_citation(tmp_path: Path) -> None:
    """REQ-ORCH-005 — every emitted recommendation carries ≥1 citation.

    Run against the localization-branch fixture (which surfaces multiple
    investigate_location entries because Phase 4 SBFL may produce
    multiple ranks). Loop over every recommendation and confirm ≥1
    citation.
    """

    clear_resolver_cache()
    workspace = _materialize_fixture("localization-branch", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await test_target_in_store("tests/", init.store, timeout=120.0)

    assert outcome.recommendations, "Expected ≥1 recommendation"
    for rec in outcome.recommendations:
        assert len(rec.evidence_citations) >= 1, (
            f"REQ-ORCH-005 violation: recommendation {rec.recommendation_id} "
            f"({rec.category}) carries 0 citations"
        )
