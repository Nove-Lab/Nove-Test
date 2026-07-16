"""``novetest test [target]`` — integrated workflow.

Composes the canonical Phase-6 chain (workflows/orchestration.md §2):

.. code-block:: text

    run/execute
      → memory/store_run_evidence
      → orchestration/evaluate_stage_eligibility
      → coverage/derive_coverage_facts
      → regression/resolve_latest_baseline → regression/compare_runs
      → localization/derive_localization_findings
      → replay/replay_run                       (opt-in: --reruns N > 0
                                                 AND failed tests)
      → orchestration/build_fact_bundle
      → orchestration/synthesize_recommendation
        (citations chained inside)

Error policy (brief §5 + 2026-06-25 ``--reruns`` decision):

- Steps 5-8 are **best-effort**: any single-engine failure becomes
  ``stage_eligibility.<stage> = "unavailable"`` (with the engine's
  ``unavailable.reason`` preserved on ``per_stage_reasons``). The
  workflow continues — synthesis still fires on whatever facts survived.
- Step 2 (``run/execute``) is fatal. The CLI handler maps the same
  exception surface ``novetest run`` does and re-uses the Run error
  envelope unchanged.
- The Replay step is opt-in via ``reruns`` (the ``--reruns N`` CLI flag;
  decision ``2026-06-25-test-reruns-flag-and-replay-integration``).
  Default ``0`` keeps the pre-integration behavior byte-for-byte:
  ``replay_results`` empty, ``stage_eligibility.replay == "not_run"``.
  With ``N > 0`` and at least one failed test, ONE whole-run
  ``replay_run`` attempt executes with ``reruns=N`` (the Replay engine's
  attempt granularity is the original run — its classifier performs the
  per-test divergence analysis internally; there is no per-test replay
  scoping in the engine API). A ``ReplayUnavailable`` attempt outcome is
  best-effort like steps 5-8: ``stage_eligibility.replay =
  "unavailable"`` (reason preserved) and the invocation still succeeds.

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
from novetest.models import MemoryEntry, ReplayResult, RunRecord
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.orchestration.anchor_resolution import (
    normalize_target_expression,
    resolve_execution_engine,
)
from novetest.orchestration.recommendation import (
    FactBundle,
    Recommendation,
    StageEligibility,
    build_fact_bundle,
    synthesize_recommendation,
)
from novetest.orchestration.recommendation.fact_bundle import (
    record_has_failed_tests,
)
from novetest.regression import (
    RegressionUnavailable,
    compare_runs,
    resolve_latest_baseline,
)
from novetest.replay import ReplayUnavailable, get_replay_result, replay_run
from novetest.run import AdapterWarning, execute, resolve_test_target
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

    ``warnings`` carries the adapter's notice-grade signals from the Run
    step (defaults to empty when the adapter emitted none). The CLI
    handler projects them onto ``envelope.warnings[]`` via the same
    ``AdapterWarning → EnvelopeWarning`` field-copy ``run_cmd`` uses.
    Per decision 2026-06-06 they are transient envelope decorations —
    NOT persisted on the Run Record.
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
    warnings: tuple[AdapterWarning, ...] = ()


async def test_target_in_store(
    target_expression: str,
    store: ProjectStore,
    *,
    timeout: float | None = 600.0,
    reruns: int = 0,
    engine: tuple[str, str] | None = None,
) -> TestOutcome:
    """Execute target, persist evidence, derive facts, synthesize recommendations.

    Sequence per brief §5 / workflows/orchestration.md §2 (+ the
    2026-06-25 ``--reruns`` decision for step 6b):

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
    6b. Opt-in Replay: when ``reruns > 0`` AND the Run Record has failed
        tests, invoke ONE whole-run ``replay/replay_run`` attempt with
        ``reruns=reruns`` (best-effort — a ``ReplayUnavailable`` outcome
        surfaces on the eligibility slot, never fails the invocation).
        The replay-execution runs persist as first-class Memory Entries,
        exactly as the standalone ``novetest replay`` verb's do.
    7. Build ``StageEligibility`` from the per-stage outcomes.
    8. Build ``FactBundle`` from the surviving facts (Replay Results in
       ``replay_results``).
    9. Synthesize recommendations (``flaky_suspected`` is reachable when
       the attempt classified ``inconsistent``).

    ``reruns=0`` (the default) skips step 6b entirely — output is
    byte-identical to the pre-integration workflow.

    ``engine`` is the transient ``--engine`` override pair (decision
    ``2026-07-03-engine-selection-policy.md`` D3); ``None`` falls back to
    the store's pin, and ``run/execute`` requires an explicit,
    store-pinned (or overridden) pair — it never auto-detects. The target
    expression is normalized to anchor-relative canonical form first, so
    the same ask from any cwd shares one baseline series.
    """

    workspace_path = store.path.parent
    engine_pair = await resolve_execution_engine(store, engine)
    normalized_expression = normalize_target_expression(
        target_expression, workspace_path
    )
    target = resolve_test_target(normalized_expression, workspace_path)
    run_id = generate_ulid()
    artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"

    # Step 2 — execute. Always with coverage so the integrated workflow
    # has the per-test attribution Localization needs for sbfl_per_test.
    # ``execute`` returns ``(RunRecord, adapter_warnings)`` per the
    # 2026-06-06 envelope-warnings-projection slice; the warnings are
    # propagated to ``TestOutcome.warnings`` so the CLI handler can
    # surface them on ``envelope.warnings[]``.
    record, adapter_warnings = await execute(
        target,
        artifact_dir=artifact_dir,
        run_id=run_id,
        timeout=timeout,
        collect_coverage=True,
        engine=engine_pair,
    )

    # Step 3 — persist. Relativize artifact paths to Project-Store-relative
    # POSIX form (``.as_posix()`` so record.json and the envelope carry
    # forward slashes on every host — ORC-15) BEFORE handing the record to
    # ``store_run_evidence``, which persists what it is given verbatim. The
    # returned Memory Entry is re-read once after ALL derivations complete
    # (see below), so we only need the persistence side effect here.
    relative_paths = {
        name: Path(p).relative_to(store.path).as_posix()
        for name, p in record.artifact_paths.items()
    }
    from dataclasses import replace as _replace

    persisted_record = _replace(record, artifact_paths=relative_paths)
    store_run_evidence(store, persisted_record)
    run_record: RunRecord = persisted_record

    # Step 4 — best-effort Coverage derivation.
    coverage_outcome: CoverageFactSet | CoverageUnavailable = derive_coverage_facts(
        store, run_record.run_reference
    )
    coverage_facts: CoverageFactSet | None = (
        coverage_outcome if isinstance(coverage_outcome, CoverageFactSet) else None
    )

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

    # Step 6b — opt-in Replay (2026-06-25 decision). One whole-run attempt:
    # the Replay engine's attempt granularity is the original run (its
    # classifier does the per-test divergence analysis internally), so a
    # single ``replay_run(..., reruns=N)`` call replays every test — the
    # failed ones included — N times and classifies the session.
    # ``replay_outcome is None`` means "not attempted" (flag absent or no
    # failed tests) and preserves the pre-integration ``"not_run"`` slot.
    replay_outcome: ReplayResult | ReplayUnavailable | None = None
    if reruns > 0 and record_has_failed_tests(run_record):
        replay_outcome = await replay_run(
            store,
            run_record.run_reference,
            reruns=reruns,
            timeout=timeout,
        )

    # Refresh the Memory Entry ONCE, after every derivation (Coverage,
    # Regression, Localization, Replay) has written its fact files, so the
    # returned entry's ``has_*`` flags reflect ALL just-derived facts. A
    # single refresh point replaces the earlier per-step refreshes (which
    # fired only after Coverage and after a successful Replay) that left
    # ``has_regression_facts`` / ``has_localization_findings`` reporting
    # just-derived facts as absent (ORC-26). Strictly fresher and simpler:
    # the read is unconditional and downstream of the last write.
    entry = retrieve_run_evidence(store, run_record.run_reference)

    # Step 7 — build StageEligibility from the four per-stage outcomes.
    stage_eligibility = _build_stage_eligibility(
        coverage_outcome=coverage_outcome,
        regression_outcome=regression_outcome,
        localization_outcome=localization_outcome,
        replay_outcome=replay_outcome,
    )

    # Step 8 — bundle the surviving facts.
    bundle = build_fact_bundle(
        run_record=run_record,
        stage_eligibility=stage_eligibility,
        coverage_facts=coverage_facts,
        regression_facts=regression_facts,
        localization_findings=localization_findings,
        replay_results=(
            (replay_outcome,) if isinstance(replay_outcome, ReplayResult) else ()
        ),
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
        warnings=adapter_warnings,
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

    # Regression: baseline selection goes through Regression's shared
    # ``resolve_baseline_for_run`` selector — the ONE place the D5
    # engine-scope filter lives (decision 2026-07-03-engine-selection-policy
    # D5; ``inspect`` and ``status`` route through the same selector, so all
    # three compositions agree by construction). The final read stays
    # cache-only (``get_regression_facts``, never ``compare_runs``) because
    # this path re-derives nothing.
    from novetest.regression import (
        REASON_NO_COMPARABLE_BASELINE as _REASON_NO_COMPARABLE_BASELINE,
    )
    from novetest.regression import get_regression_facts as _get_regression_facts
    from novetest.regression import resolve_baseline_for_run as _resolve_baseline

    regression_outcome: RegressionFactSet | RegressionUnavailable
    baseline_ref = _resolve_baseline(store, target_entry)
    if baseline_ref is None:
        regression_outcome = RegressionUnavailable(
            reason=_REASON_NO_COMPARABLE_BASELINE,
            # A bare ``novetest test`` records an EMPTY target expression —
            # render the pinned placeholder instead of ``detail: ""``
            # (mirrors regression's S36-close pin; free-text only).
            detail=target_entry.run_record.target_expression
            or "(entire workspace)",
            baseline_run_reference=None,
            target_run_reference=ref,
        )
    else:
        regression_outcome = _get_regression_facts(store, baseline_ref, ref)
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

    # Replay: cache-only read (mirrors ``inspect``). A cached Replay Result
    # (produced by ``test --reruns`` or the standalone ``replay`` verb)
    # folds into the bundle so re-derivation matches the live-path output;
    # a cache miss means "never attempted" → the ``not_run`` slot (the
    # live path's attempted-but-unavailable state persists nothing, so it
    # is indistinguishable from never-attempted on re-derive — acceptable:
    # the NFR-ORCH-002 round-trip contract covers persisted facts).
    cached_replay = get_replay_result(store, ref)
    replay_outcome: ReplayResult | None = (
        cached_replay if isinstance(cached_replay, ReplayResult) else None
    )

    stage_eligibility = _build_stage_eligibility(
        coverage_outcome=coverage_outcome,
        regression_outcome=regression_outcome,
        localization_outcome=localization_outcome,
        replay_outcome=replay_outcome,
    )

    bundle = build_fact_bundle(
        run_record=target_entry.run_record,
        stage_eligibility=stage_eligibility,
        coverage_facts=coverage_facts,
        regression_facts=regression_facts,
        localization_findings=localization_findings,
        replay_results=(replay_outcome,) if replay_outcome is not None else (),
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
    replay_outcome: ReplayResult | ReplayUnavailable | None = None,
) -> StageEligibility:
    """Compute the four-slot ``StageEligibility`` from per-engine outcomes.

    Per brief §5 envelope shape (+ the 2026-06-25 ``--reruns`` decision
    for the replay slot):

    - ``coverage``     → ``"available"`` iff CoverageFactSet
    - ``regression``   → ``"available"`` iff RegressionFactSet
    - ``localization`` → the finding's ``mode`` when available, else
      ``"unavailable"``
    - ``replay``       → ``"not_run"`` when no attempt was made
      (``replay_outcome is None`` — flag absent or no failed tests;
      byte-preserves the pre-integration slot), ``"available"`` for a
      completed attempt (a ``ReplayResult`` of ANY classification,
      including the valid ``unable_to_replay`` — mirroring the standalone
      ``replay`` verb's exit-0 treatment), ``"unavailable"`` when the
      attempt could not start (``ReplayUnavailable``).

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
    if replay_outcome is None:
        replay_state = "not_run"
        replay_reason: str | None = "replay_not_run"
    elif isinstance(replay_outcome, ReplayResult):
        replay_state = "available"
        replay_reason = None
    else:
        replay_state = "unavailable"
        replay_reason = replay_outcome.reason

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
        "replay": replay_reason,
    }
    return StageEligibility(
        coverage=coverage_state,
        regression=regression_state,
        localization=localization_state,
        replay=replay_state,
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
