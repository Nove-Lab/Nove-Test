"""NFR-COV-002 performance benchmark for ``compare_coverage_facts``.

NFR-COV-002 (verbatim): *"The system shall generate coverage comparison
results for two stored runs with up to 50,000 covered locations within 5
seconds when the needed evidence is already stored locally."*

This module lives under ``tests/perf/``, which is OUTSIDE
``[tool.pytest.ini_options].testpaths`` — so the default ``uv run pytest``
never collects it (same pattern as ``tests/release/``). Run it explicitly::

    uv run pytest tests/perf

Methodology (pinned by the task):

- Timed region is the real public ``compare_coverage_facts(store, baseline,
  target)`` — including the on-disk load + ``from_dict`` parse of both
  ``coverage_facts.json`` files. Test execution and ``derive_coverage_facts``
  are out of scope: the evidence is written to the store by the session
  fixture before any timing starts.
- 1 untimed warm-up call (page-cache priming) + 5 timed calls; we assert on
  the median.
- Pass criterion: ``median < 3.0`` seconds. The 3.0s internal budget against
  the 5.0s NFR leaves ~40% headroom for shared-CI-runner I/O variance.
"""

from __future__ import annotations

import statistics
import time

import pytest

from novetest.coverage.compare import CoverageDelta, compare_coverage_facts
from novetest.coverage.persistence import write_coverage_facts
from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference

from perf.coverage.generate_large_fact_set import (
    generate_fact_set,
    perturb_for_delta,
)


# --- benchmark shape ---------------------------------------------------------

# 500 files x (80 executed lines + 20 executed branch pairs) = exactly 50,000
# covered locations per fact set — the NFR-COV-002 ceiling.
NUM_FILES = 500
LINES_PER_FILE = 80
BRANCHES_PER_FILE = 20
COVERED_LOCATIONS = NUM_FILES * (LINES_PER_FILE + BRANCHES_PER_FILE)  # 50,000

# The target run's files start 50 indices higher than the baseline's, so the
# two runs share 450 paths and each carries 50 paths the other lacks. With
# `perturb_for_delta` applied to the target, every common file yields a real
# `FileCoverageDelta` — the comparison path is exercised non-trivially.
TARGET_FILE_OFFSET = 50
COMMON_FILES = NUM_FILES - TARGET_FILE_OFFSET  # 450
DISJOINT_FILES = TARGET_FILE_OFFSET  # 50 added + 50 removed

CREATED_AT = 1_700_000_000_000
BASELINE_RUN_ID = "01PERFCOMPAREBASELINE00000B"
TARGET_RUN_ID = "01PERFCOMPARETARGET0000000T"

# Benchmark budget: 3.0s internal vs the 5.0s NFR-COV-002 ceiling.
BUDGET_SECONDS = 3.0
TIMED_RUNS = 5


def _run_record(ref: RunReference) -> RunRecord:
    """Minimal RunRecord so ``retrieve_run_evidence`` resolves the run."""
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="passed",
        started_at=ref.created_at,
    )


@pytest.fixture(scope="session")
def perf_store(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[ProjectStore, RunReference, RunReference]:
    """Build a Project Store with two runs' coverage evidence already stored.

    The fixture writes through the REAL ``store_run_evidence`` +
    ``write_coverage_facts`` so the on-disk ``coverage_facts.json`` files are
    byte-identical to production output — the load + parse cost the benchmark
    times is the genuine one.
    """
    workspace = tmp_path_factory.mktemp("perf_ws")
    store = create_project_store(workspace)

    baseline_ref = RunReference(run_id=BASELINE_RUN_ID, created_at=CREATED_AT)
    target_ref = RunReference(run_id=TARGET_RUN_ID, created_at=CREATED_AT)
    store_run_evidence(store, _run_record(baseline_ref))
    store_run_evidence(store, _run_record(target_ref))

    baseline_facts = generate_fact_set(
        BASELINE_RUN_ID, NUM_FILES, LINES_PER_FILE, BRANCHES_PER_FILE
    )
    target_facts = perturb_for_delta(
        generate_fact_set(
            TARGET_RUN_ID,
            NUM_FILES,
            LINES_PER_FILE,
            BRANCHES_PER_FILE,
            file_offset=TARGET_FILE_OFFSET,
        )
    )
    write_coverage_facts(store, baseline_facts)
    write_coverage_facts(store, target_facts)
    return store, baseline_ref, target_ref


def test_generator_yields_exactly_50k_covered_locations() -> None:
    """The generator + perturbation both land on exactly 50,000 locations."""
    base = generate_fact_set(
        BASELINE_RUN_ID, NUM_FILES, LINES_PER_FILE, BRANCHES_PER_FILE
    )
    base_count = sum(
        len(f.executed_lines) + len(f.executed_branches) for f in base.files
    )
    assert base_count == COVERED_LOCATIONS == 50_000

    # `perturb_for_delta` swaps locations rather than adding them, so the
    # covered-location total is invariant — both sides stay at the ceiling.
    perturbed = perturb_for_delta(base)
    perturbed_count = sum(
        len(f.executed_lines) + len(f.executed_branches) for f in perturbed.files
    )
    assert perturbed_count == 50_000


def test_perf_fixture_is_non_trivial_delta(
    perf_store: tuple[ProjectStore, RunReference, RunReference],
) -> None:
    """The benchmark scenario is a real delta, not a zero-change fast path."""
    store, baseline_ref, target_ref = perf_store
    delta = compare_coverage_facts(store, baseline_ref, target_ref)

    assert isinstance(delta, CoverageDelta)
    assert len(delta.files_added) == DISJOINT_FILES == 50
    assert len(delta.files_removed) == DISJOINT_FILES == 50
    # Every common file is perturbed, so none is skipped by the
    # compact-payload guard in `_build_delta`.
    assert len(delta.file_deltas) == COMMON_FILES == 450

    sample = delta.file_deltas[0]
    assert len(sample.newly_covered_lines) == 5
    assert len(sample.newly_uncovered_lines) == 5
    assert len(sample.newly_covered_branches) == 1
    assert len(sample.newly_uncovered_branches) == 1


def test_compare_50k_locations_within_budget(
    perf_store: tuple[ProjectStore, RunReference, RunReference],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-COV-002: comparing two 50k-location runs stays under budget."""
    store, baseline_ref, target_ref = perf_store

    # Untimed warm-up — primes the page cache so the timed runs measure
    # steady-state cost, not first-touch disk I/O.
    warm_up = compare_coverage_facts(store, baseline_ref, target_ref)
    assert isinstance(warm_up, CoverageDelta)

    durations: list[float] = []
    for _ in range(TIMED_RUNS):
        start = time.perf_counter()
        delta = compare_coverage_facts(store, baseline_ref, target_ref)
        durations.append(time.perf_counter() - start)
        assert isinstance(delta, CoverageDelta)

    median = statistics.median(durations)
    with capsys.disabled():
        print(
            f"\n[NFR-COV-002] compare_coverage_facts at {COVERED_LOCATIONS:,} "
            f"covered locations/side: median={median:.3f}s over {TIMED_RUNS} "
            f"runs (internal budget {BUDGET_SECONDS}s, NFR ceiling 5.0s)"
        )

    assert median < BUDGET_SECONDS, (
        f"NFR-COV-002 budget exceeded: median={median:.3f}s "
        f">= {BUDGET_SECONDS}s; durations={[round(d, 3) for d in durations]}"
    )
