---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-05-20
slug: coverage-compare-perf
related:
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Task: NFR-COV-002 performance benchmark — `coverage diff` at 50k locations

> **QUEUED — ready to dispatch.** The `jest-istanbul-parser` slice this
> task was blocked on merged 2026-05-20 (`e01df3c`). This is the next
> Coverage slice — Phase 2 DoD #4, the last open Phase 2 bullet. Scoped
> from a `performance-engineer` specialist review on 2026-05-20.

## Scope / Mission

Close **Phase 2 DoD #4**: "Performance NFR-COV-002 met on a fixture with
50k covered locations."

NFR-COV-002 (verbatim): *"The system shall generate coverage comparison
results for two stored runs with up to 50,000 covered locations within 5
seconds when the needed evidence is already stored locally."*

This is a performance bar on the **coverage comparison** path —
`compare_coverage_facts` in `src/novetest/coverage/compare.py` (the
internal of `novetest coverage diff`). "Evidence already stored locally"
means both runs' `coverage_facts.json` are already persisted; test
execution and `derive_coverage_facts` are OUT of the timed region.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-coverage-team.md`
2. `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
   frozen `coverage_facts.json` v1 schema
3. `src/novetest/coverage/compare.py`, `retrieval.py`, `persistence.py`
4. `src/novetest/models/coverage_fact_set.py`
5. The `tests/release/` directory + `.github/workflows/ci.yml`'s
   "pytest (release smoke)" step — the precedent for a test tree that
   sits OUTSIDE the default `pytest` collection

## Interpretation (pinned)

A "covered location" = one entry in a file's `executed_lines` OR one
`[from_line, to_line]` pair in `executed_branches`. The 50k target is
`sum(len(executed_lines) + len(executed_branches))` across all files of
ONE `CoverageFactSet`. Both sides of the comparison independently reach
~50k. Timed region: load both stored JSON files from disk + parse to
`CoverageFactSet` + run `compare_coverage_facts` to a returned
`CoverageDelta`. Use `mapping_granularity: "aggregate"` on both sides
(simplest conforming choice; keeps generated files small).

## Files to write / modify

- `tests/perf/__init__.py` and `tests/perf/coverage/__init__.py` — NEW.
- `tests/perf/coverage/generate_large_fact_set.py` — NEW. Pure generator:
  `generate_fact_set(run_id, num_files, lines_per_file, branches_per_file,
  *, file_offset=0) -> CoverageFactSet`. No disk I/O; stdlib +
  `novetest.models` only.
- `tests/perf/coverage/test_perf_compare.py` — NEW. The benchmark test.

**Deliberate placement decision:** the perf test lives under a NEW
`tests/perf/` tree, which is OUTSIDE `[tool.pytest.ini_options].testpaths`
in `pyproject.toml` (same pattern as `tests/release/`). This means the
default `uv run pytest -q` never collects it — so **no pytest marker and
no `pyproject.toml` edit is needed** (`pyproject.toml` is Run/Release
territory, not yours). A dedicated CI lane opts in explicitly via
`uv run pytest tests/perf`.

## Files NOT to touch

- `pyproject.toml` — Run/Release territory. The `tests/perf/` placement
  is specifically chosen so you do NOT need to touch it.
- `.github/workflows/**` — the CI perf lane is a SEPARATE companion
  Release task (see "Companion task" below); do not edit workflows.
- `src/**` unless a profiling-driven optimization is needed — see below.

## Fixture strategy (pinned)

Programmatic generator, NOT a real 50k-line software project. The NFR
says evidence is already stored, so no test execution belongs here.

- **Shape:** 500 files x (80 executed lines + 20 executed branch pairs)
  = exactly 50,000 covered locations per fact set. File paths
  `src/pkg/module_{i:04d}.py`.
- **Non-trivial delta** (a zero-change delta hits the early-return guard
  and is artificially fast):
  - files 0-399: common to both runs; target gains 5 newly-covered
    lines + 1 changed branch each -> 400 `FileCoverageDelta` entries
  - files 400-449: baseline-only -> `files_removed`
  - files 450-499: target-only -> `files_added`
- **Generated at test time** (session-scoped fixture), NOT committed —
  each `coverage_facts.json` is ~4-6 MB; committing multi-MB blobs is
  inappropriate. The fixture writes through the REAL `write_coverage_facts`
  + `store_run_evidence` so files are byte-identical to production output.

## Benchmark methodology (pinned)

- Timed region: `compare_coverage_facts(store, baseline_ref, target_ref)`
  — the real public function, including the on-disk load.
- Harness: plain `time.perf_counter` (do NOT add `pytest-benchmark` —
  new dev dependency for one test, and its auto-iteration suits
  micro-benchmarks, not ~1-2s calls).
- 1 untimed warm-up call (page-cache priming) + 5 timed calls; assert on
  the **median**.
- **Pass criterion:** `median < 3.0` seconds. The 3.0s internal budget
  vs the 5.0s NFR gives ~40% headroom for shared-CI-runner variance
  (GitHub Actions wall-clock variance is ±30-40% for I/O-bound Python).
  Passing the 3s budget on a shared runner means NFR-COV-002's 5s is met
  on any realistic hardware. Do NOT put a wall-clock assertion in the
  default pytest suite.

## Likely bottlenecks (from the performance-engineer review)

- **Deserialization dominates (~60-70%):** `CoverageFactSet.from_dict`
  does ~120k Python-level `int()` calls across both sides. Watch tuple
  construction in `FileCoverage.from_dict`.
- **`_file_delta` set ops (~20-30%):** ~1,600 small set constructions +
  differences over 400 common files. No O(n^2) — set difference is
  O(smaller). `sorted()` calls are on <=80-element sets, negligible.
- **Minor:** the defensive `dict(d["summary"])` copy in `from_dict`
  is 1,000 extra shallow copies; acceptable, just be aware.
- No O(n^2) pattern exists in `compare.py` — algorithm is O(files x
  locations-per-file) with O(1) dict lookups. If the 3s budget is
  missed, profile `from_dict` first.
- Any `src/novetest/coverage/` optimization driven by profiling is in
  scope; keep changes surgical and re-verify the frozen schema.

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green, and confirms `tests/perf/` is NOT
  collected by the default run.
- `uv run pytest tests/perf` — the perf test runs and passes.
- `uv run mypy` — clean.

## Companion task (PM note — not your responsibility)

A small Release task will add a CI lane that runs `uv run pytest
tests/perf` (a non-blocking job, since a 5s budget on shared runners
should not gate PRs). PM dispatches that separately. Your handoff should
state that the perf test is runnable via `uv run pytest tests/perf` so
the Release lane can wire it.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code.

## Reporting

Write `agent-comms/handoffs/coverage-team-<date>-coverage-compare-perf.md`.
Append a `WORKLOG.md` entry (touches `tests/`), run
`python3 tools/regen_comms_index.py`, stage with source.

**DoD bullets believed closed:** claim Phase 2 DoD #4 in the handoff's
"DoD bullets believed closed" list. PM verifies and ticks during cleanup.
Report the observed median time.
