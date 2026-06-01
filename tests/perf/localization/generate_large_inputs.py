"""Programmatic NFR-scale input generators for the NFR-LOC-002 benchmark.

Mirrors ``tests/perf/coverage/generate_large_fact_set.py`` in structure
and methodology. Three builder functions — one per Localization mode —
synthesize ``CoverageFactSet`` + ``RunRecord`` pairs at the NFR-LOC-002
scale (**500 failed-test references × 50,000 covered locations**) and
persist them through the real ``write_coverage_facts`` /
``store_run_evidence`` helpers so the timed region in the test bodies
measures the production read-from-disk + parse + SBFL-pipeline cost
(matching NFR's *"when required evidence is already stored locally"*
semantics).

Determinism: a fixed RNG seed pins every random choice so two runs
produce byte-identical fact sets / line_contexts / failure logs. This is
required so Manual Test can re-run the benchmark and compare timings
across hosts (same property as the Coverage perf helper).

Memory footprint (per-test mode):
- 3500 (tests) × 50000 (locations) ``line_contexts`` map: ~50 MB of
  Python objects, ~80 MB of pretty-printed JSON on disk.
- Dense ``Spectra.matrix`` (uint8): 3500 × 50000 = **175 MB**.
- Peak during ``derive_localization_findings``: ~400-500 MB.
- 500 stub Python files (~600 B each): ~300 KB on disk.

The brief tolerates this footprint on dev hosts with ≥ 2 GB free RAM;
CI cells with constrained memory may skip the perf suite (perf is
opt-in via the ``tests/perf`` path).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from novetest.coverage.persistence import write_coverage_facts
from novetest.localization.persistence import localization_findings_path
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# ---------------------------------------------------------------------------
# NFR-LOC-002 scale knobs (LOAD-BEARING — keep aligned with the brief)
# ---------------------------------------------------------------------------

# 500 source files × 100 lines/file = 50,000 covered locations exactly.
NUM_FILES: int = 500
LINES_PER_FILE: int = 100
COVERED_LOCATIONS: int = NUM_FILES * LINES_PER_FILE  # 50,000

# 500 failed-test references (the NFR ceiling) + 3,000 passing test rows.
# 6:1 passing-to-failing matches Defects4J-class real bug ratios; passing
# count is benchmark-realistic, NOT NFR-mandated. See brief §5.2.1.
NUM_FAILED_TESTS: int = 500
NUM_PASSING_TESTS: int = 3000

# Each test attests ~500 locations = ~1% of total — sparse enough to NOT
# saturate the matrix, dense enough to drive real SBFL distinctions.
PER_TEST_HIT_COUNT: int = 500

# First 10 files are the "buggy" cluster. Failed tests sample heavily from
# them; passing tests spread evenly. This gives the SBFL formulas a real
# signal to recover (rank a buggy file at the top) rather than a uniformly
# random matrix where every formula returns near-zero scores.
NUM_BUGGY_FILES: int = 10
BUGGY_FILE_HIT_FRACTION: float = 0.70  # failed tests draw 70% from buggy cluster

# Fixed seed for reproducibility (same property as the Coverage perf helper).
# Arbitrary but fixed; any value works as long as it never changes.
RNG_SEED: int = 0xC002

# Fixed epoch-ms stamp so the generated RunRecord is byte-deterministic.
_CREATED_AT: int = 1_700_000_000_000

# Single ULID per builder so cross-mode tests are isolated by run-id.
_RUN_ID_PER_TEST: str = "01PERFLOCPERTEST0000000000"
_RUN_ID_AGGREGATE: str = "01PERFLOCAGGREGATE0000000A"
_RUN_ID_PROXIMITY: str = "01PERFLOCPROXIMITY00000000"


# ---------------------------------------------------------------------------
# Public dataclasses returned by each builder
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PerfInputs:
    """Bundle of synthesized inputs handed to a perf-test body.

    - ``run_reference`` — the ``RunReference`` whose evidence is on disk.
    - ``findings_cache_path`` — the ``localization_findings.json`` path the
      test body unlinks between iterations to force a cold-derive (the
      cache-read path is meaningless for an NFR that constrains the
      *production* of localization results, per the brief §5.3 callout
      about the Defect 5 fix).
    """

    run_reference: RunReference
    findings_cache_path: Path


# ---------------------------------------------------------------------------
# Per-test mode — the SBFL worst case
# ---------------------------------------------------------------------------


def build_per_test_inputs(store: ProjectStore) -> PerfInputs:
    """Synthesize NFR-scale inputs for the ``sbfl_per_test`` benchmark.

    Steps:
    1. Stamp 500 stub Python files at ``<project_root>/src/buggy_pkg/`` so
       the symbol resolver finds real qualnames (the resolver is called
       once per location; missing files cost ~30 μs per failed
       ``read_text`` syscall — 50k locations × 30 μs = 1.5 s of wasted
       cold-path budget if the files are absent).
    2. Build the per-test coverage matrix in memory:
       - Each test draws ``PER_TEST_HIT_COUNT`` location indices.
       - Failed tests sample 70% from the "buggy cluster" (first 10 files)
         and 30% spread; passing tests spread evenly.
       - Deterministic RNG via ``RNG_SEED``.
    3. Build a per-test ``CoverageFactSet`` (``mapping_granularity =
       "per-test"``) with ``line_contexts`` populated for every line that
       was hit by ≥ 1 test.
    4. Build a ``RunRecord`` with 500 failed + 3000 passing
       ``TestResult`` rows.
    5. Persist both to the real ``ProjectStore`` via
       ``store_run_evidence`` + ``write_coverage_facts``.
    """
    project_root = store.path.parent
    _write_stub_python_files(project_root)

    rng = random.Random(RNG_SEED)
    location_to_tests = _generate_per_test_coverage(rng)
    coverage_facts = _build_per_test_coverage_facts(
        run_id=_RUN_ID_PER_TEST,
        location_to_tests=location_to_tests,
    )
    record = _build_run_record(
        run_id=_RUN_ID_PER_TEST,
        engine_name="pytest",
        ecosystem="python",
        with_failure_traces=False,
    )
    store_run_evidence(store, record)
    write_coverage_facts(store, coverage_facts)
    return PerfInputs(
        run_reference=record.run_reference,
        findings_cache_path=localization_findings_path(
            store, record.run_reference.run_id
        ),
    )


# ---------------------------------------------------------------------------
# Aggregate mode — file-level fallback
# ---------------------------------------------------------------------------


def build_aggregate_inputs(store: ProjectStore) -> PerfInputs:
    """Synthesize NFR-scale inputs for the ``sbfl_aggregate`` benchmark.

    Differences from per-test:
    - ``CoverageFactSet.mapping_granularity = "aggregate"`` —
      ``line_contexts`` is empty on every ``FileCoverage`` (per-test
      attribution is absent).
    - Each failed ``TestResult.failure_reference`` carries a
      pytest-style traceback string mentioning the buggy files at
      specific lines — the ``parse_failure_log`` step lifts these to
      attribute failures to files.

    Memory expectation: dominated by the 500-file ``CoverageFactSet``
    plus 500 × ~1 KB failure strings. ~5 MB peak. Much smaller than
    per-test.
    """
    rng = random.Random(RNG_SEED + 1)
    coverage_facts = _build_aggregate_coverage_facts(_RUN_ID_AGGREGATE)
    record = _build_run_record(
        run_id=_RUN_ID_AGGREGATE,
        engine_name="pytest",
        ecosystem="python",
        with_failure_traces=True,
        rng=rng,
    )
    store_run_evidence(store, record)
    write_coverage_facts(store, coverage_facts)
    return PerfInputs(
        run_reference=record.run_reference,
        findings_cache_path=localization_findings_path(
            store, record.run_reference.run_id
        ),
    )


# ---------------------------------------------------------------------------
# failure_proximity mode — no coverage at all
# ---------------------------------------------------------------------------


def build_failure_proximity_inputs(store: ProjectStore) -> PerfInputs:
    """Synthesize NFR-scale inputs for the ``failure_proximity`` benchmark.

    Mode triggered by ``CoverageUnavailable`` upstream — we deliberately
    do NOT persist any ``CoverageFactSet``. Each of the 500 failed
    ``TestResult`` rows carries a pytest-style traceback string mentioning
    the buggy files. Passing tests are not used by this mode so we omit
    them to keep the fixture lean (the algorithm's ``_FAILED_OUTCOMES``
    filter skips passing rows anyway).

    Memory expectation: just the 500 traceback strings (~500 KB total).
    The cheapest mode by far.
    """
    rng = random.Random(RNG_SEED + 2)
    record = _build_failed_only_record(
        run_id=_RUN_ID_PROXIMITY,
        engine_name="pytest",
        ecosystem="python",
        rng=rng,
    )
    store_run_evidence(store, record)
    return PerfInputs(
        run_reference=record.run_reference,
        findings_cache_path=localization_findings_path(
            store, record.run_reference.run_id
        ),
    )


# ---------------------------------------------------------------------------
# Internals — per-test coverage matrix synthesis
# ---------------------------------------------------------------------------


def _generate_per_test_coverage(
    rng: random.Random,
) -> dict[int, list[str]]:
    """Sample which tests touched which (location-index) lines.

    Returns ``{location_index: [test_id, ...]}``. The location index spans
    ``[0, COVERED_LOCATIONS)``; the index decomposes as
    ``file_idx = i // LINES_PER_FILE``, ``line_no = (i % LINES_PER_FILE) + 1``.

    Sampling shape (see module docstring):
    - Failed tests: 70% of hits from the buggy cluster (first 10 files =
      1000 locations), 30% spread across the remaining 49,000 locations.
    - Passing tests: uniform draw across all 50,000 locations.
    """
    buggy_loc_count = NUM_BUGGY_FILES * LINES_PER_FILE
    buggy_pool = list(range(buggy_loc_count))
    rest_pool = list(range(buggy_loc_count, COVERED_LOCATIONS))
    all_pool = list(range(COVERED_LOCATIONS))

    location_to_tests: dict[int, list[str]] = {
        i: [] for i in range(COVERED_LOCATIONS)
    }

    buggy_hits_per_test = int(PER_TEST_HIT_COUNT * BUGGY_FILE_HIT_FRACTION)
    spread_hits_per_test = PER_TEST_HIT_COUNT - buggy_hits_per_test

    # Failed tests cluster on the buggy files; this is the SBFL signal.
    for i in range(NUM_FAILED_TESTS):
        test_id = f"tests/test_perf.py::test_failed_{i:04d}"
        chosen_buggy = rng.sample(buggy_pool, buggy_hits_per_test)
        chosen_spread = rng.sample(rest_pool, spread_hits_per_test)
        for loc_idx in chosen_buggy:
            location_to_tests[loc_idx].append(test_id)
        for loc_idx in chosen_spread:
            location_to_tests[loc_idx].append(test_id)

    # Passing tests spread evenly across the whole codebase.
    for i in range(NUM_PASSING_TESTS):
        test_id = f"tests/test_perf.py::test_passing_{i:04d}"
        chosen = rng.sample(all_pool, PER_TEST_HIT_COUNT)
        for loc_idx in chosen:
            location_to_tests[loc_idx].append(test_id)

    return location_to_tests


def _build_per_test_coverage_facts(
    *,
    run_id: str,
    location_to_tests: dict[int, list[str]],
) -> CoverageFactSet:
    """Assemble the per-test ``CoverageFactSet`` from the sampled coverage.

    One ``FileCoverage`` per file (500 total). ``line_contexts`` is the
    line-keyed dict of test-id tuples on each file.
    """
    files: list[FileCoverage] = []
    for file_idx in range(NUM_FILES):
        file_path = _stub_file_path_for(file_idx)
        executed_lines: list[int] = []
        line_contexts: dict[int, tuple[str, ...]] = {}
        for line_offset in range(LINES_PER_FILE):
            loc_idx = file_idx * LINES_PER_FILE + line_offset
            line_no = line_offset + 1
            tests = location_to_tests.get(loc_idx) or []
            if tests:
                executed_lines.append(line_no)
                line_contexts[line_no] = tuple(tests)

        summary = CoverageSummary(
            num_statements=LINES_PER_FILE,
            covered_statements=len(executed_lines),
            missing_statements=LINES_PER_FILE - len(executed_lines),
            excluded_statements=0,
            num_branches=0,
            covered_branches=0,
            missing_branches=0,
            percent_covered=(
                round(100 * len(executed_lines) / LINES_PER_FILE, 2)
                if LINES_PER_FILE
                else 100.0
            ),
        )
        files.append(
            FileCoverage(
                file_path=file_path,
                executed_lines=tuple(executed_lines),
                missing_lines=tuple(),
                excluded_lines=tuple(),
                executed_branches=tuple(),
                missing_branches=tuple(),
                summary=summary,
                line_contexts=line_contexts,
            )
        )

    total_statements = NUM_FILES * LINES_PER_FILE
    covered = sum(len(f.executed_lines) for f in files)
    aggregate_summary = CoverageSummary(
        num_statements=total_statements,
        covered_statements=covered,
        missing_statements=total_statements - covered,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=round(100 * covered / total_statements, 2),
    )
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=_CREATED_AT),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=aggregate_summary,
        files=tuple(files),
        derived_at=_CREATED_AT,
        metadata={"generator": "tests/perf/localization/generate_large_inputs.py"},
    )


# ---------------------------------------------------------------------------
# Internals — aggregate-mode coverage synthesis
# ---------------------------------------------------------------------------


def _build_aggregate_coverage_facts(run_id: str) -> CoverageFactSet:
    """Assemble an aggregate-granularity ``CoverageFactSet``.

    Every file is "covered" (the aggregate path uses presence-in-coverage
    as the gate for ``ep``), but per-test attribution is absent —
    ``line_contexts`` is the empty dict on every ``FileCoverage``.
    """
    files: list[FileCoverage] = []
    for file_idx in range(NUM_FILES):
        file_path = _stub_file_path_for(file_idx)
        executed_lines = tuple(range(1, LINES_PER_FILE + 1))
        summary = CoverageSummary(
            num_statements=LINES_PER_FILE,
            covered_statements=LINES_PER_FILE,
            missing_statements=0,
            excluded_statements=0,
            num_branches=0,
            covered_branches=0,
            missing_branches=0,
            percent_covered=100.0,
        )
        files.append(
            FileCoverage(
                file_path=file_path,
                executed_lines=executed_lines,
                missing_lines=tuple(),
                excluded_lines=tuple(),
                executed_branches=tuple(),
                missing_branches=tuple(),
                summary=summary,
                line_contexts={},
            )
        )
    aggregate_summary = CoverageSummary(
        num_statements=NUM_FILES * LINES_PER_FILE,
        covered_statements=NUM_FILES * LINES_PER_FILE,
        missing_statements=0,
        excluded_statements=0,
        num_branches=0,
        covered_branches=0,
        missing_branches=0,
        percent_covered=100.0,
    )
    return CoverageFactSet(
        run_reference=RunReference(run_id=run_id, created_at=_CREATED_AT),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="aggregate",
        summary=aggregate_summary,
        files=tuple(files),
        derived_at=_CREATED_AT,
        metadata={"generator": "tests/perf/localization/generate_large_inputs.py"},
    )


# ---------------------------------------------------------------------------
# Internals — RunRecord synthesis (shared by aggregate + per-test)
# ---------------------------------------------------------------------------


def _build_run_record(
    *,
    run_id: str,
    engine_name: str,
    ecosystem: str,
    with_failure_traces: bool,
    rng: random.Random | None = None,
) -> RunRecord:
    """Build a ``RunRecord`` with 500 failed + 3000 passing ``TestResult`` rows.

    When ``with_failure_traces`` is True, each failed test's
    ``failure_reference`` is a pytest-style traceback string mentioning
    a buggy file at a buggy line — for the aggregate mode's
    ``parse_failure_log`` step. Per-test mode does not consume the
    failure_reference field, so we pass ``False`` there to keep the
    fixture cheap.
    """
    test_results: list[TestResult] = []
    for i in range(NUM_FAILED_TESTS):
        node_id = f"tests/test_perf.py::test_failed_{i:04d}"
        failure_reference: str | None
        if with_failure_traces:
            assert rng is not None, "rng required when with_failure_traces=True"
            failure_reference = _synthesize_pytest_traceback(i, rng)
        else:
            failure_reference = None
        test_results.append(
            TestResult(
                node_id=node_id,
                outcome="failed",
                duration_ms=1,
                failure_reference=failure_reference,
            )
        )
    for i in range(NUM_PASSING_TESTS):
        node_id = f"tests/test_perf.py::test_passing_{i:04d}"
        test_results.append(
            TestResult(
                node_id=node_id,
                outcome="passed",
                duration_ms=1,
                failure_reference=None,
            )
        )

    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=_CREATED_AT),
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        ecosystem=ecosystem,
        status="failed",
        started_at=_CREATED_AT,
        completed_at=_CREATED_AT + 1000,
        summary_counts={
            "passed": NUM_PASSING_TESTS,
            "failed": NUM_FAILED_TESTS,
        },
        test_results=tuple(test_results),
        artifact_paths={},
        metadata={"generator": "tests/perf/localization/generate_large_inputs.py"},
    )


def _build_failed_only_record(
    *,
    run_id: str,
    engine_name: str,
    ecosystem: str,
    rng: random.Random,
) -> RunRecord:
    """``RunRecord`` for failure_proximity mode (no passing tests required)."""
    test_results: list[TestResult] = []
    for i in range(NUM_FAILED_TESTS):
        node_id = f"tests/test_perf.py::test_failed_{i:04d}"
        test_results.append(
            TestResult(
                node_id=node_id,
                outcome="failed",
                duration_ms=1,
                failure_reference=_synthesize_pytest_traceback(i, rng),
            )
        )
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=_CREATED_AT),
        target_expression="tests/",
        target_type="dir",
        engine_name=engine_name,
        ecosystem=ecosystem,
        status="failed",
        started_at=_CREATED_AT,
        completed_at=_CREATED_AT + 1000,
        summary_counts={"failed": NUM_FAILED_TESTS},
        test_results=tuple(test_results),
        artifact_paths={},
        metadata={"generator": "tests/perf/localization/generate_large_inputs.py"},
    )


def _synthesize_pytest_traceback(test_index: int, rng: random.Random) -> str:
    """Build a pytest-shaped traceback string mentioning a buggy file.

    Format matches the ``_PYTEST_REGEXES`` patterns in
    ``localization/failure_proximity.py`` so ``parse_failure_log`` lifts
    the file:line tuples. We rotate through the buggy file cluster
    (first 10 files) so different failed tests blame different lines —
    that distribution is what gives the SBFL aggregate mode its real
    file-level signal.
    """
    buggy_file_idx = test_index % NUM_BUGGY_FILES
    buggy_line = rng.randint(1, LINES_PER_FILE)
    file_path = _stub_file_path_for(buggy_file_idx)
    test_file = "tests/test_perf.py"
    test_line = 100 + (test_index % 50)
    return (
        f"E       AssertionError: synthesized failure {test_index}\n"
        f"\n"
        f'  File "{test_file}", line {test_line}, in '
        f"test_failed_{test_index:04d}\n"
        f"    assert calc.run() == 42\n"
        f'  File "{file_path}", line {buggy_line}, in func_{buggy_line // 10}\n'
        f"    return _broken_helper(x)\n"
        f"{file_path}:{buggy_line}: AssertionError\n"
    )


# ---------------------------------------------------------------------------
# Internals — stub Python files (the symbol resolver's read targets)
# ---------------------------------------------------------------------------


def _stub_file_path_for(file_idx: int) -> str:
    """Project-relative path for stub file ``file_idx``.

    Per-test mode's ``_aggregate_by_symbol`` calls the resolver with the
    absolute path = ``<project_root>/<this path>``. The stub files are
    written under the project root so the resolver actually parses them.
    """
    return f"src/buggy_pkg/module_{file_idx:04d}.py"


def _write_stub_python_files(project_root: Path) -> None:
    """Create 500 stub Python source files at the project root.

    Each stub has exactly ``LINES_PER_FILE`` (= 100) lines and 10
    functions of 10 lines each. Identical content across files keeps the
    bytes-on-disk cost minimal (~600 B × 500 = ~300 KB) and avoids any
    pathological AST-walk variance from real-world syntactic noise.
    """
    src_dir = project_root / "src" / "buggy_pkg"
    src_dir.mkdir(parents=True, exist_ok=True)
    content = _STUB_FILE_CONTENT
    # Bytes-identical content — same parse result for every file. Idempotent
    # so a re-run of the session fixture is a no-op when stubs already exist.
    for file_idx in range(NUM_FILES):
        target = src_dir / f"module_{file_idx:04d}.py"
        if target.exists() and target.read_text(encoding="utf-8") == content:
            continue
        target.write_text(content, encoding="utf-8")


def _build_stub_content() -> str:
    """Generate the 100-line stub content used in every stub file."""
    lines: list[str] = []
    # 10 functions × 10 lines = 100 lines, 1-indexed for clarity.
    # Each function body is straight-line code so symbol_resolver collects
    # one extent per function with a clean (start, end) range.
    for fn_idx in range(10):
        # Function header + body fills 10 source lines.
        lines.append(f"def func_{fn_idx}(x: int) -> int:")
        for j in range(8):
            lines.append(f"    v{j} = x + {fn_idx * 10 + j}")
        lines.append(f"    return v7")
    assert len(lines) == LINES_PER_FILE, (
        f"stub must be exactly {LINES_PER_FILE} lines; got {len(lines)}"
    )
    return "\n".join(lines) + "\n"


_STUB_FILE_CONTENT: str = _build_stub_content()
