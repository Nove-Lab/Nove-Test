"""``try_get_latest_regression_facts`` — engine-scoped prior selection.

D5 of ``decisions/2026-07-03-engine-selection-policy.md``: cross-run
analyses never cross an engine boundary. The prior lookup delegates to
Regression's shared ``resolve_baseline_for_run`` selector (same
``target_expression`` AND same ``engine_name``), so in a mixed-engine
store (legitimate under D3's transient ``--engine`` override) the probe
finds the same-engine regression-facts cache one step back instead of
asking for a cross-engine pair whose cache can never exist.

Task: ``agent-comms/tasks/localization-team-2026-07-03-engine-scoped-
regression-prior.md`` (D5 audit Finding B). The acceptance case drives
the full ``derive_localization_findings`` aggregate path: series
[pytest, cargo-test, pytest] with a regression-facts cache for the
pytest pair → FLUCCS ``changed_files`` reweighting activates. Pre-fix,
the local engine-blind scan selected the cargo neighbor as baseline,
missed the cache, and silently degraded to "no regression prior".
"""

from __future__ import annotations

from pathlib import Path

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.derive import (
    derive_localization_findings,
    try_get_latest_regression_facts,
)
from novetest.memory.project_store import (
    ProjectStore,
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import retrieve_run_evidence, store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.regression_fact_set import (
    RegressionFactSet,
    RegressionSummary,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.persistence import write_regression_facts


# Deterministic three-run series: t0 < t1 < t2 by created_at.
REF_T0 = RunReference(run_id="01HPRIOR000000000000000AA0", created_at=1_700_000_000_000)
REF_T1 = RunReference(run_id="01HPRIOR000000000000000BB1", created_at=1_700_000_100_000)
REF_T2 = RunReference(run_id="01HPRIOR000000000000000CC2", created_at=1_700_000_200_000)

_PASSING = (
    TestResult(node_id="tests/t.py::t_ok", outcome="passed", duration_ms=1),
)
_FAILING = (
    TestResult(
        node_id="tests/t.py::t_a",
        outcome="failed",
        duration_ms=1,
        failure_reference="src/changed.py:3: e",
    ),
    TestResult(
        node_id="tests/t.py::t_b",
        outcome="failed",
        duration_ms=1,
        failure_reference="src/unchanged.py:7: e",
    ),
)


def _summary(num: int = 1) -> CoverageSummary:
    return CoverageSummary(
        num_statements=num,
        covered_statements=num,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )


def _make_record(
    ref: RunReference,
    *,
    engine_name: str = "pytest",
    test_results: tuple[TestResult, ...] = _PASSING,
) -> RunRecord:
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        engine_version=None,
        ecosystem="python" if engine_name == "pytest" else "rust",
        status="failed",
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=test_results,
    )


def _seed_store(tmp_path: Path, records: tuple[RunRecord, ...]) -> ProjectStore:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    store = create_project_store(workspace)
    for record in records:
        store_run_evidence(store, record)
    return get_project_store_state(workspace / ".novetest")


def _write_aggregate_coverage(
    store: ProjectStore,
    ref: RunReference,
    *,
    covered_files: tuple[str, ...],
) -> None:
    files = tuple(
        FileCoverage(
            file_path=fp,
            executed_lines=(1, 2),
            missing_lines=(),
            excluded_lines=(),
            executed_branches=(),
            missing_branches=(),
            summary=_summary(2),
            line_contexts={},
        )
        for fp in covered_files
    )
    write_coverage_facts(
        store,
        CoverageFactSet(
            run_reference=ref,
            engine_name="pytest",
            ecosystem="python",
            mapping_granularity="aggregate",
            summary=_summary(2 * len(files)),
            files=files,
            derived_at=ref.created_at + 500,
        ),
    )


def _make_regression_facts(
    baseline: RunReference,
    target: RunReference,
    *,
    changed_files: tuple[str, ...],
) -> RegressionFactSet:
    coverage_change = {
        "schema_version": 1,
        "baseline_run_reference": baseline.to_dict(),
        "target_run_reference": target.to_dict(),
        "baseline_granularity": "aggregate",
        "target_granularity": "aggregate",
        "summary_before": _summary(0).to_dict(),
        "summary_after": _summary(0).to_dict(),
        "files_added": list(changed_files),
        "files_removed": [],
        "file_deltas": [],
    }
    return RegressionFactSet(
        baseline_run_reference=baseline,
        target_run_reference=target,
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version=None,
        target_engine_version=None,
        derived_at=target.created_at + 2_000,
        summary=RegressionSummary(
            regressed=0, fixed=0, still_failing=0, still_passing=0,
            still_skipped=0, newly_skipped=0, newly_active=0,
            added=0, removed=0,
            total_baseline_tests=0, total_target_tests=0,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=coverage_change,
    )


# ---------------------------------------------------------------------------
# Acceptance (task criteria): mixed-engine store, full aggregate pipeline
# ---------------------------------------------------------------------------


def test_mixed_engine_store_applies_fluccs_reweighting(tmp_path: Path) -> None:
    """Series [pytest, cargo-test, pytest] + cache for the pytest pair →
    aggregate-mode localization applies the ``changed_files`` reweighting.

    Pre-fix, the engine-blind prior scan picked the cargo neighbor (t1)
    as baseline, found no (t1, t2) cache, and degraded to no-prior
    (``regression_reweighted=False``).
    """
    store = _seed_store(
        tmp_path,
        (
            _make_record(REF_T0),
            _make_record(REF_T1, engine_name="cargo-test"),
            _make_record(REF_T2, test_results=_PASSING + _FAILING),
        ),
    )
    _write_aggregate_coverage(
        store, REF_T2, covered_files=("src/changed.py", "src/unchanged.py")
    )
    write_regression_facts(
        store,
        _make_regression_facts(REF_T0, REF_T2, changed_files=("src/changed.py",)),
    )

    finding = derive_localization_findings(store, REF_T2)

    assert isinstance(finding, LocalizationFinding)
    assert finding.mode == "sbfl_aggregate"
    assert finding.metadata.get("regression_reweighted") is True
    # Identical unboosted (ef, ep, nf, np) for both files — the ×1.5
    # boost on the changed file decides rank 1.
    by_file = {e.code_location.file: e for e in finding.entries}
    assert by_file["src/changed.py"].rank == 1
    assert by_file["src/unchanged.py"].rank == 2


# ---------------------------------------------------------------------------
# Direct probe — engine-scoped selection semantics
# ---------------------------------------------------------------------------


def test_mixed_engine_store_probe_finds_same_engine_pair_one_step_back(
    tmp_path: Path,
) -> None:
    """The probe skips the newer cross-engine sibling and returns the
    cached facts for the same-engine pair (t0, t2)."""
    store = _seed_store(
        tmp_path,
        (
            _make_record(REF_T0),
            _make_record(REF_T1, engine_name="cargo-test"),
            _make_record(REF_T2),
        ),
    )
    write_regression_facts(
        store,
        _make_regression_facts(REF_T0, REF_T2, changed_files=("src/changed.py",)),
    )

    entry = retrieve_run_evidence(store, REF_T2)
    result = try_get_latest_regression_facts(store, entry)

    assert isinstance(result, RegressionFactSet)
    assert result.baseline_run_reference.run_id == REF_T0.run_id
    assert result.target_run_reference.run_id == REF_T2.run_id


def test_single_engine_store_prior_selection_unchanged(tmp_path: Path) -> None:
    """Pure single-engine store: the newest strictly-older sibling stays
    the baseline — pre-D5 behavior pinned."""
    store = _seed_store(
        tmp_path,
        (_make_record(REF_T0), _make_record(REF_T1)),
    )
    write_regression_facts(
        store,
        _make_regression_facts(REF_T0, REF_T1, changed_files=()),
    )

    entry = retrieve_run_evidence(store, REF_T1)
    result = try_get_latest_regression_facts(store, entry)

    assert isinstance(result, RegressionFactSet)
    assert result.baseline_run_reference.run_id == REF_T0.run_id


def test_no_prior_run_returns_none(tmp_path: Path) -> None:
    """Single run in the store (typical first run) → ``None``."""
    store = _seed_store(tmp_path, (_make_record(REF_T0),))

    entry = retrieve_run_evidence(store, REF_T0)
    assert try_get_latest_regression_facts(store, entry) is None


def test_cross_engine_only_priors_return_none(tmp_path: Path) -> None:
    """Only cross-engine priors exist → no comparable baseline → ``None``
    (never a cross-engine pair lookup)."""
    store = _seed_store(
        tmp_path,
        (
            _make_record(REF_T0, engine_name="cargo-test"),
            _make_record(REF_T1),
        ),
    )

    entry = retrieve_run_evidence(store, REF_T1)
    assert try_get_latest_regression_facts(store, entry) is None


def test_prior_without_cached_facts_returns_none(tmp_path: Path) -> None:
    """Same-engine prior exists but the pair was never derived → ``None``
    (pure read; never derives)."""
    store = _seed_store(
        tmp_path,
        (_make_record(REF_T0), _make_record(REF_T1)),
    )

    entry = retrieve_run_evidence(store, REF_T1)
    assert try_get_latest_regression_facts(store, entry) is None
