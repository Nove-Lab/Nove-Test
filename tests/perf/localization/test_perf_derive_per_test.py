"""NFR-LOC-002 perf benchmark for ``derive_localization_findings`` — per-test mode.

NFR-LOC-002 (verbatim, ``design/requirements-analysis/requirements-
specification/groups/localization.md``):

> The system shall produce localization results for a run with **up to
> 500 failed-test references** and **50,000 covered locations** within
> **8 seconds** when required evidence is already stored locally.

Per-test mode is the SBFL worst case — it builds a dense
``Spectra.matrix`` of shape ``(3500, 50000)`` (~175 MB uint8) and runs
all four formulas (Ochiai / Op2 / DStar / Tarantula) over it. The
matrix size and the symbol-resolver walk dominate the cold-derive cost.

This module lives under ``tests/perf/``, which is OUTSIDE
``[tool.pytest.ini_options].testpaths`` — so the default ``uv run
pytest`` never collects it. Run explicitly::

    uv run pytest tests/perf

Methodology (mirrors ``tests/perf/coverage/test_perf_compare.py``):

- 1 untimed warm-up call (page-cache priming) + 5 timed calls; assert on
  the median.
- Internal budget: **5.0 s** (37.5% headroom vs the 8.0 s NFR ceiling) —
  same headroom ratio Coverage's perf precedent uses (3.0 s vs 5.0 s NFR).
- Each timed iteration deletes the persisted ``localization_findings.json``
  BEFORE the timed region so we measure the cold-derive path, NOT the
  cache-read path (the Defect 5 fix landed 2026-06-01 made
  ``derive_localization_findings`` cache-hit fast; we explicitly opt out
  of that fast path so the NFR's "produce localization results" wording
  is honored).
"""

from __future__ import annotations

import statistics
import time

import pytest

from novetest.localization.derive import derive_localization_findings
from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.models.localization_finding import LocalizationFinding

from perf.localization.generate_large_inputs import (
    COVERED_LOCATIONS,
    NUM_FAILED_TESTS,
    NUM_PASSING_TESTS,
    PerfInputs,
    build_per_test_inputs,
)


# Benchmark budget: 5.0s internal vs the 8.0s NFR-LOC-002 ceiling.
BUDGET_SECONDS: float = 5.0
NFR_CEILING_SECONDS: float = 8.0
TIMED_RUNS: int = 5


@pytest.fixture(scope="session")
def per_test_perf_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[ProjectStore, PerfInputs]:
    """Build a Project Store with NFR-scale per-test evidence already stored.

    Session-scoped — the per-test fixture is the most expensive of the
    three to construct (~180 MB Python objects + ~80 MB JSON write).
    Built once per session and shared across all timing iterations.
    """
    workspace = tmp_path_factory.mktemp("perf_loc_per_test_ws")
    store = create_project_store(workspace)
    inputs = build_per_test_inputs(store)
    return store, inputs


def test_per_test_fixture_persists_at_nfr_scale(
    per_test_perf_inputs: tuple[ProjectStore, PerfInputs],
) -> None:
    """Sanity-check the fixture: 500 failed + 3000 passing, 50k locations."""
    store, inputs = per_test_perf_inputs
    # The findings cache is empty before the first derive (it would only
    # exist if a previous iteration left a stale file behind).
    if inputs.findings_cache_path.exists():
        inputs.findings_cache_path.unlink()
    # Sanity assertions on the bare fixture scale — guards against a
    # generator regression silently shrinking the benchmark.
    assert NUM_FAILED_TESTS == 500
    assert NUM_PASSING_TESTS == 3000
    assert COVERED_LOCATIONS == 50_000


def test_perf_derive_per_test_meets_nfr_loc_002(
    per_test_perf_inputs: tuple[ProjectStore, PerfInputs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-LOC-002: per-test SBFL on 3500 tests × 50k locations stays under budget."""
    store, inputs = per_test_perf_inputs

    # Untimed warm-up — primes the page cache + the ast resolver's
    # _RESOLVER_CACHE so the timed runs measure steady-state cost. The
    # warm-up writes the findings file; the timed loop unlinks it before
    # each iteration to force re-derivation.
    if inputs.findings_cache_path.exists():
        inputs.findings_cache_path.unlink()
    warm_up = derive_localization_findings(store, inputs.run_reference)
    assert isinstance(warm_up, LocalizationFinding)
    assert warm_up.mode == "sbfl_per_test", (
        f"per-test fixture must dispatch to sbfl_per_test; got {warm_up.mode!r}"
    )

    durations: list[float] = []
    for _ in range(TIMED_RUNS):
        if inputs.findings_cache_path.exists():
            inputs.findings_cache_path.unlink()
        start = time.perf_counter()
        finding = derive_localization_findings(store, inputs.run_reference)
        durations.append(time.perf_counter() - start)
        assert isinstance(finding, LocalizationFinding)
        assert finding.mode == "sbfl_per_test"

    median = statistics.median(durations)
    mean = statistics.mean(durations)
    stdev = statistics.stdev(durations) if len(durations) >= 2 else 0.0
    with capsys.disabled():
        print(
            f"\n[NFR-LOC-002 / sbfl_per_test] "
            f"3500 tests × {COVERED_LOCATIONS:,} locations: "
            f"median={median:.3f}s mean={mean:.3f}s stdev={stdev:.3f}s "
            f"over {TIMED_RUNS} runs "
            f"(internal budget {BUDGET_SECONDS}s, NFR ceiling "
            f"{NFR_CEILING_SECONDS}s) "
            f"timings={[round(d, 3) for d in durations]}"
        )

    assert median < BUDGET_SECONDS, (
        f"NFR-LOC-002 per-test internal budget exceeded: median={median:.3f}s "
        f">= {BUDGET_SECONDS}s; NFR ceiling {NFR_CEILING_SECONDS}s; "
        f"durations={[round(d, 3) for d in durations]}"
    )
    # Defense-in-depth: also assert the NFR ceiling. If we ever flip the
    # internal budget without raising the NFR, this check still catches a
    # regression past the published 8.0s ceiling.
    assert median < NFR_CEILING_SECONDS, (
        f"NFR-LOC-002 ceiling exceeded: median={median:.3f}s "
        f">= {NFR_CEILING_SECONDS}s; durations={[round(d, 3) for d in durations]}"
    )
