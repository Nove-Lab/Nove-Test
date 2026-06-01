"""NFR-LOC-002 perf benchmark for ``derive_localization_findings`` — failure_proximity mode.

failure_proximity is the no-coverage fallback — there is no
``CoverageFactSet`` to load, no spectra matrix to build, and no SBFL
formula sweep. The hot path is just the per-engine failure-log regex
over 500 synthesized pytest tracebacks. Expected median: well under 100
milliseconds (the cheapest of the three modes).

Methodology mirrors the per-test and aggregate benchmarks — 1 untimed
warm-up + 5 timed runs, internal budget 5.0 s. The budget is the same
across all three modes for consistency; the failure_proximity mode is
overwhelmingly under-budget and the assertion mostly catches
catastrophic regressions (e.g. a regex backtracking blowup).
"""

from __future__ import annotations

import statistics
import time

import pytest

from novetest.localization.derive import derive_localization_findings
from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.models.localization_finding import LocalizationFinding

from perf.localization.generate_large_inputs import (
    NUM_FAILED_TESTS,
    PerfInputs,
    build_failure_proximity_inputs,
)


BUDGET_SECONDS: float = 5.0
NFR_CEILING_SECONDS: float = 8.0
TIMED_RUNS: int = 5


@pytest.fixture(scope="session")
def failure_proximity_perf_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[ProjectStore, PerfInputs]:
    """Build a Project Store with NFR-scale failure-only evidence (no coverage)."""
    workspace = tmp_path_factory.mktemp("perf_loc_proximity_ws")
    store = create_project_store(workspace)
    inputs = build_failure_proximity_inputs(store)
    return store, inputs


def test_perf_derive_failure_proximity_meets_nfr_loc_002(
    failure_proximity_perf_inputs: tuple[ProjectStore, PerfInputs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-LOC-002: failure_proximity on 500 failed-log parses stays under budget."""
    store, inputs = failure_proximity_perf_inputs

    if inputs.findings_cache_path.exists():
        inputs.findings_cache_path.unlink()
    warm_up = derive_localization_findings(store, inputs.run_reference)
    assert isinstance(warm_up, LocalizationFinding)
    assert warm_up.mode == "failure_proximity", (
        f"failure_proximity fixture must dispatch to failure_proximity; "
        f"got {warm_up.mode!r}"
    )

    durations: list[float] = []
    for _ in range(TIMED_RUNS):
        if inputs.findings_cache_path.exists():
            inputs.findings_cache_path.unlink()
        start = time.perf_counter()
        finding = derive_localization_findings(store, inputs.run_reference)
        durations.append(time.perf_counter() - start)
        assert isinstance(finding, LocalizationFinding)
        assert finding.mode == "failure_proximity"

    median = statistics.median(durations)
    mean = statistics.mean(durations)
    stdev = statistics.stdev(durations) if len(durations) >= 2 else 0.0
    with capsys.disabled():
        print(
            f"\n[NFR-LOC-002 / failure_proximity] "
            f"{NUM_FAILED_TESTS} failed-log parses: "
            f"median={median:.3f}s mean={mean:.3f}s stdev={stdev:.3f}s "
            f"over {TIMED_RUNS} runs "
            f"(internal budget {BUDGET_SECONDS}s, NFR ceiling "
            f"{NFR_CEILING_SECONDS}s) "
            f"timings={[round(d, 3) for d in durations]}"
        )

    assert median < BUDGET_SECONDS, (
        f"NFR-LOC-002 failure_proximity internal budget exceeded: "
        f"median={median:.3f}s >= {BUDGET_SECONDS}s; "
        f"durations={[round(d, 3) for d in durations]}"
    )
    assert median < NFR_CEILING_SECONDS, (
        f"NFR-LOC-002 ceiling exceeded: median={median:.3f}s "
        f">= {NFR_CEILING_SECONDS}s; durations={[round(d, 3) for d in durations]}"
    )
