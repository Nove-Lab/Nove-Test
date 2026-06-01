"""NFR-LOC-002 perf benchmark for ``derive_localization_findings`` — aggregate mode.

Aggregate mode skips the dense ``Spectra.matrix`` entirely and instead
parses per-test failure traces to attribute failures to files at
file-level granularity. The hot path is the failure-log regex over 500
synthesized pytest tracebacks plus a 500-file Ochiai sweep. Expected
median: well under 1 second (the brief predicts sub-second).

Methodology mirrors the per-test benchmark — 1 untimed warm-up + 5 timed
runs, internal budget 5.0 s (the same headroom-vs-ceiling ratio
Coverage's perf precedent uses). The aggregate mode is the easiest of
the three; the budget exists mainly so a regression that bloats the
file-iteration cost shows up immediately.
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
    PerfInputs,
    build_aggregate_inputs,
)


BUDGET_SECONDS: float = 5.0
NFR_CEILING_SECONDS: float = 8.0
TIMED_RUNS: int = 5


@pytest.fixture(scope="session")
def aggregate_perf_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[ProjectStore, PerfInputs]:
    """Build a Project Store with NFR-scale aggregate-granularity evidence."""
    workspace = tmp_path_factory.mktemp("perf_loc_aggregate_ws")
    store = create_project_store(workspace)
    inputs = build_aggregate_inputs(store)
    return store, inputs


def test_perf_derive_aggregate_meets_nfr_loc_002(
    aggregate_perf_inputs: tuple[ProjectStore, PerfInputs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-LOC-002: aggregate-mode SBFL on 500-failed × 50k locations under budget."""
    store, inputs = aggregate_perf_inputs

    if inputs.findings_cache_path.exists():
        inputs.findings_cache_path.unlink()
    warm_up = derive_localization_findings(store, inputs.run_reference)
    assert isinstance(warm_up, LocalizationFinding)
    assert warm_up.mode == "sbfl_aggregate", (
        f"aggregate fixture must dispatch to sbfl_aggregate; "
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
        assert finding.mode == "sbfl_aggregate"

    median = statistics.median(durations)
    mean = statistics.mean(durations)
    stdev = statistics.stdev(durations) if len(durations) >= 2 else 0.0
    with capsys.disabled():
        print(
            f"\n[NFR-LOC-002 / sbfl_aggregate] "
            f"500 failed × {COVERED_LOCATIONS:,} locations: "
            f"median={median:.3f}s mean={mean:.3f}s stdev={stdev:.3f}s "
            f"over {TIMED_RUNS} runs "
            f"(internal budget {BUDGET_SECONDS}s, NFR ceiling "
            f"{NFR_CEILING_SECONDS}s) "
            f"timings={[round(d, 3) for d in durations]}"
        )

    assert median < BUDGET_SECONDS, (
        f"NFR-LOC-002 aggregate internal budget exceeded: median={median:.3f}s "
        f">= {BUDGET_SECONDS}s; durations={[round(d, 3) for d in durations]}"
    )
    assert median < NFR_CEILING_SECONDS, (
        f"NFR-LOC-002 ceiling exceeded: median={median:.3f}s "
        f">= {NFR_CEILING_SECONDS}s; durations={[round(d, 3) for d in durations]}"
    )
