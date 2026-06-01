"""``novetest test [target]`` — integrated workflow.

Composes the canonical Phase-6 chain (workflows/orchestration.md §2):

.. code-block:: text

    run/execute
      → memory/store_run_evidence
      → orchestration/evaluate_stage_eligibility
      → coverage/derive_coverage_facts
      → regression/resolve_latest_baseline → regression/compare_runs
      → localization/derive_localization_findings
      → orchestration/build_fact_bundle
      → orchestration/synthesize_recommendation
        (citations chained inside)

Error policy (brief §5):

- Steps 5-8 are **best-effort**: any single-engine failure becomes
  ``stage_eligibility.<stage> = "unavailable"`` (with the engine's
  ``unavailable.reason`` preserved on ``per_stage_reasons``). The
  workflow continues — synthesis still fires on whatever facts survived.
- Step 2 (``run/execute``) is fatal. The CLI handler maps the same
  exception surface ``novetest run`` does and re-uses the Run error
  envelope unchanged.
- Replay step is intentionally absent in Phase 6 entry: ``replay_result``
  is always ``None``; ``stage_eligibility.replay`` is always
  ``"not_run"``. Phase 5 lands the wiring.

Output shape: a ``TestOutcome`` dataclass that the CLI handler projects
onto the brief §5 envelope shape (verbatim). The handler stays thin —
all business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from novetest.coverage import (
    CoverageUnavailable,
    derive_coverage_facts,
    get_coverage_facts,
)
from novetest.localization import (
    LocalizationFinding,
    LocalizationUnavailable,
    derive_localization_findings,
)
from novetest.memory import (
    ProjectStore,
    retrieve_run_evidence,
    store_run_evidence,
)
from novetest.models import LocalizationFinding as LocalizationFindingModel
from novetest.models import MemoryEntry, RunRecord
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.orchestration.recommendation import (
    FactBundle,
    Recommendation,
    StageEligibility,
    build_fact_bundle,
    synthesize_recommendation,
)
from novetest.regression import (
    RegressionUnavailable,
    compare_runs,
    resolve_latest_baseline,
)
from novetest.run import execute, resolve_test_target
from novetest.utils.ulid import generate_ulid


@dataclass(slots=True, frozen=True)
class TestOutcome:
    """Result of the integrated ``novetest test`` workflow.

    The CLI handler projects this onto the envelope shape pinned by the
    brief §5; this dataclass is the canonical Python-side view.

    ``stage_eligibility`` is the ``StageEligibility`` block emitted on
    ``data.stage_eligibility``. ``recommendations`` is the list of
    deterministic ``Recommendation`` records the synthesizer produced.
    ``memory_entry`` is preserved so callers (tests, inspect) can
    inspect what landed; the envelope itself does not surface it.

    ``run_record_status`` carries the Run's normalized ``status``
    (``"passed"`` / ``"failed"`` / ``"errored"`` / ...) so the CLI
    handler can pick the right exit code without re-parsing the Memory
    Entry. Mirrors the ``RunOutcome`` shape ``cli/app.py::run_cmd``
    already consumes.
    """

    # Pytest collection guard — keeps this dataclass from being picked up
    # by test discovery just because its name starts with ``Test``. Mirrors
    # ``TestResult.__test__`` / ``TestTransition.__test__``.
    __test__: ClassVar[bool] = False

    memory_entry: MemoryEntry
    artifact_dir: Path
    stage_eligibility: StageEligibility
    fact_bundle: FactBundle
    recommendations: list[Recommendation]
    run_record_status: str


async def test_target_in_store(
    target_expression: str,
    store: ProjectStore,
    *,
    timeout: float | None = 600.0,
) -> TestOutcome:
    """Execute target, persist evidence, derive facts, synthesize recommendations.

    Sequence per brief §5 / workflows/orchestration.md §2:

    1. Resolve target via Run engine.
    2. ``run/execute`` with coverage instrumentation always-on (the
       integrated workflow needs coverage to reach Localization's
       sbfl_per_test mode; if coverage is unsupported by the native
       engine, ``derive_coverage_facts`` returns Unavailable and the
       workflow still continues).
    3. Persist Run Record via ``memory/store_run_evidence``.
    4. Derive Coverage Facts via ``derive_coverage_facts`` (best-effort).
    5. Resolve baseline + compare via Regression engine (best-effort).
    6. Derive Localization Findings (best-effort).
    7. Build ``StageEligibility`` from the per-stage outcomes.
    8. Build ``FactBundle`` from the surviving facts.
    9. Synthesize recommendations.

    No Replay step — Phase 5 dep (per brief §"Out of scope").
    """

    workspace_path = store.path.parent
    target = resolve_test_target(target_expression, workspace_path)
    run_id = generate_ulid()
    artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"

    # Step 2 — execute. Always with coverage so the integrated workflow
    # has the per-test attribution Localization needs for sbfl_per_test.
    record = await execute(
        target,
        artifact_dir=artifact_dir,
        run_id=run_id,
        timeout=timeout,
        collect_coverage=True,
    )

    # Step 3 — persist. ``store_run_evidence`` mutates artifact paths to
    # Project-Store-relative form before write; mirror that here so the
    # in-memory record matches what later derivations will see.
    relative_paths = {
        name: str(Path(p).relative_to(store.path))
        for name, p in record.artifact_paths.items()
    }
    from dataclasses import replace as _replace

    persisted_record = _replace(record, artifact_paths=relative_paths)
    entry = store_run_evidence(store, persisted_record)
    run_record: RunRecord = persisted_record

    # Step 4 — best-effort Coverage derivation.
    coverage_outcome: CoverageFactSet | CoverageUnavailable = derive_coverage_facts(
        store, run_record.run_reference
    )
    coverage_facts: CoverageFactSet | None = (
        coverage_outcome if isinstance(coverage_outcome, CoverageFactSet) else None
    )
    # Refresh the Memory Entry so ``has_coverage_facts`` reflects disk state.
    if coverage_facts is not None:
        entry = retrieve_run_evidence(store, run_record.run_reference)

    # Step 5 — Regression: resolve latest baseline for the target, then
    # compare. Both calls are best-effort; missing baseline (the natural
    # case for a fresh target) surfaces as Unavailable, not an exception.
    regression_outcome: RegressionFactSet | RegressionUnavailable
    baseline_outcome = resolve_latest_baseline(store, run_record.target_expression)
    if isinstance(baseline_outcome, RegressionUnavailable):
        regression_outcome = baseline_outcome
    else:
        baseline_ref, target_ref = baseline_outcome
        # Per Regression contract: when the resolver returns a pair, the
        # second element is the latest run — which is the run we just
        # persisted. If for any reason the pair's target side is NOT
        # the run we just executed, fall through and use the resolver's
        # selection (Regression engine is authoritative on baseline
        # selection).
        regression_outcome = compare_runs(store, baseline_ref, target_ref)
    regression_facts: RegressionFactSet | None = (
        regression_outcome
        if isinstance(regression_outcome, RegressionFactSet)
        else None
    )

    # Step 6 — Localization. Engine handles its own mode dispatch + cache
    # write; if coverage is unavailable it falls back to aggregate or
    # failure_proximity modes per the Phase-4 mode-narrative.
    localization_outcome: (
        LocalizationFindingModel | LocalizationUnavailable
    ) = derive_localization_findings(store, run_record.run_reference)
    localization_findings: LocalizationFinding | None = (
        localization_outcome
        if isinstance(localization_outcome, LocalizationFindingModel)
        else None
    )

    # Step 7 — build StageEligibility from the four per-stage outcomes.
    stage_eligibility = _build_stage_eligibility(
        coverage_outcome=coverage_outcome,
        regression_outcome=regression_outcome,
        localization_outcome=localization_outcome,
    )

    # Step 8 — bundle the surviving facts. Replay always None here.
    bundle = build_fact_bundle(
        run_record=run_record,
        stage_eligibility=stage_eligibility,
        coverage_facts=coverage_facts,
        regression_facts=regression_facts,
        localization_findings=localization_findings,
        replay_result=None,
    )

    # Step 9 — pure rule-based synthesis.
    recommendations = synthesize_recommendation(bundle)

    return TestOutcome(
        memory_entry=entry,
        artifact_dir=artifact_dir,
        stage_eligibility=stage_eligibility,
        fact_bundle=bundle,
        recommendations=recommendations,
        run_record_status=run_record.status,
    )


def build_test_outcome_from_run_id(
    store: ProjectStore, run_id: str
) -> TestOutcome | None:
    """Re-derive a ``TestOutcome`` for an already-executed run.

    Mirrors ``inspect``'s "compose existing evidence" pattern (no run
    execution, no derive — just cache reads + synthesis). Used by the
    NFR-ORCH-002 round-trip integration test to verify that the
    same bundle of facts yields the same recommendations on re-derive.

    Returns ``None`` when no Memory Entry matches ``run_id``.
    """

    # Mirror ``inspect.py::build_inspect_view``'s resolution path.
    from novetest.memory import list_run_history as _list_run_history

    history = _list_run_history(store)
    target_entry = next(
        (e for e in history if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target_entry is None:
        return None
    ref = target_entry.run_record.run_reference

    # Cache-only reads — never derive on this path.
    coverage_outcome: CoverageFactSet | CoverageUnavailable = get_coverage_facts(
        store, ref
    )
    coverage_facts: CoverageFactSet | None = (
        coverage_outcome if isinstance(coverage_outcome, CoverageFactSet) else None
    )

    # Regression: compose baseline resolution (cache-only is fine — same
    # logic ``status._latest_regression_available`` uses).
    from novetest.memory import find_runs_for_target as _find_runs_for_target
    from novetest.regression import get_regression_facts as _get_regression_facts

    siblings = _find_runs_for_target(
        store, target_entry.run_record.target_expression, include_tombstoned=False
    )
    priors = sorted(
        (s for s in siblings if s.run_record.run_reference.created_at < ref.created_at),
        key=lambda e: e.run_record.run_reference.created_at,
        reverse=True,
    )
    regression_outcome: RegressionFactSet | RegressionUnavailable
    if not priors:
        regression_outcome = RegressionUnavailable(
            reason="no-comparable-baseline",
            detail=target_entry.run_record.target_expression,
            baseline_run_reference=None,
            target_run_reference=ref,
        )
    else:
        regression_outcome = _get_regression_facts(
            store, priors[0].run_record.run_reference, ref
        )
    regression_facts: RegressionFactSet | None = (
        regression_outcome
        if isinstance(regression_outcome, RegressionFactSet)
        else None
    )

    from novetest.localization import get_localization_findings as _get_localization

    localization_outcome: (
        LocalizationFinding | LocalizationUnavailable
    ) = _get_localization(store, ref)
    localization_findings: LocalizationFinding | None = (
        localization_outcome
        if isinstance(localization_outcome, LocalizationFinding)
        else None
    )

    stage_eligibility = _build_stage_eligibility(
        coverage_outcome=coverage_outcome,
        regression_outcome=regression_outcome,
        localization_outcome=localization_outcome,
    )

    bundle = build_fact_bundle(
        run_record=target_entry.run_record,
        stage_eligibility=stage_eligibility,
        coverage_facts=coverage_facts,
        regression_facts=regression_facts,
        localization_findings=localization_findings,
        replay_result=None,
    )
    recommendations = synthesize_recommendation(bundle)
    return TestOutcome(
        memory_entry=target_entry,
        artifact_dir=store.path / "run" / "artifacts" / f"run_{run_id}",
        stage_eligibility=stage_eligibility,
        fact_bundle=bundle,
        recommendations=recommendations,
        run_record_status=target_entry.run_record.status,
    )


# ---------------------------------------------------------------------------
# StageEligibility builder — pure projection from engine outcomes
# ---------------------------------------------------------------------------


def _build_stage_eligibility(
    *,
    coverage_outcome: CoverageFactSet | CoverageUnavailable,
    regression_outcome: RegressionFactSet | RegressionUnavailable,
    localization_outcome: LocalizationFinding | LocalizationUnavailable,
) -> StageEligibility:
    """Compute the four-slot ``StageEligibility`` from per-engine outcomes.

    Per brief §5 envelope shape:

    - ``coverage``     → ``"available"`` iff CoverageFactSet
    - ``regression``   → ``"available"`` iff RegressionFactSet
    - ``localization`` → the finding's ``mode`` when available, else
      ``"unavailable"``
    - ``replay``       → always ``"not_run"`` in Phase 6 (Phase 5 dep)

    ``per_stage_reasons`` captures the verbatim engine reason for each
    unavailable stage (preserved for ``unavailable_analysis``'s
    ``reason_per_stage`` slot).
    """

    coverage_state = "available" if isinstance(coverage_outcome, CoverageFactSet) else "unavailable"
    regression_state = (
        "available" if isinstance(regression_outcome, RegressionFactSet) else "unavailable"
    )
    if isinstance(localization_outcome, LocalizationFinding):
        localization_state = localization_outcome.mode
    else:
        localization_state = "unavailable"

    reasons: dict[str, str | None] = {
        "coverage": (
            None
            if isinstance(coverage_outcome, CoverageFactSet)
            else coverage_outcome.reason
        ),
        "regression": (
            None
            if isinstance(regression_outcome, RegressionFactSet)
            else regression_outcome.reason
        ),
        "localization": (
            None
            if isinstance(localization_outcome, LocalizationFinding)
            else localization_outcome.reason
        ),
        "replay": "replay_not_run",
    }
    return StageEligibility(
        coverage=coverage_state,
        regression=regression_state,
        localization=localization_state,
        replay="not_run",
        per_stage_reasons=reasons,
    )


# Pytest collection guard — the public-API function name starts with
# ``test_`` and would otherwise be picked up by ``pytest`` discovery
# when importing this module from a test. The ``__test__ = False``
# attribute on a free function is the canonical opt-out (mirrors
# ``TestOutcome.__test__`` / ``TestResult.__test__`` on the dataclasses).
test_target_in_store.__test__ = False  # type: ignore[attr-defined]


__all__ = [
    "TestOutcome",
    "build_test_outcome_from_run_id",
    "test_target_in_store",
]
