---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-05-21
slug: coverage-compare-perf
source-handoffs:
  - handoffs/coverage-team-2026-05-21-coverage-compare-perf.md
---

# Verification: NFR-COV-002 50k-location perf benchmark for `coverage diff`

## Merged commit

- `5489c7e` — `test(coverage): NFR-COV-002 50k-location perf benchmark for coverage diff`
- Rebased onto `main`; one conflict resolved during rebase (see Notes).

## Source handoff consumed

- `handoffs/coverage-team-2026-05-21-coverage-compare-perf.md` (Coverage
  team, status `ready-to-merge`).

## What changed

A performance benchmark for `compare_coverage_facts` at 50,000 covered
locations per side. All files are NEW — no `src/` change, no `pyproject.toml`
change.

- `tests/perf/__init__.py`, `tests/perf/coverage/__init__.py` — package shells.
- `tests/perf/coverage/generate_large_fact_set.py` — pure `CoverageFactSet`
  generator (`generate_fact_set(...)` + `perturb_for_delta(...)`).
- `tests/perf/coverage/test_perf_compare.py` — the benchmark (3 tests).

`tests/perf/` is deliberately OUTSIDE `[tool.pytest.ini_options].testpaths`
(same precedent as `tests/release/`), so the default `uv run pytest` never
collects it. No pytest marker, no `pyproject.toml` edit was needed.

## Verification steps for Manual Test

1. Run the perf suite explicitly (it is opt-in):
   ```
   uv run pytest tests/perf -q
   ```
   Expect: `3 passed`. A diagnostic line is printed, observed at merge:
   ```
   [NFR-COV-002] compare_coverage_facts at 50,000 covered locations/side: median=0.024s over 5 runs (internal budget 3.0s, NFR ceiling 5.0s)
   ```
   The pass/fail gate is the **median**, asserted under the 3.0s internal
   budget (NFR-COV-002 ceiling is 5.0s).

2. Confirm `tests/perf` is NOT collected by the default gate:
   ```
   uv run pytest -q tests/unit tests/integration
   ```
   Expect: `337 passed, 3 skipped` — unchanged baseline, the 3 perf tests
   do not appear in the count.

3. Type-check sanity:
   ```
   uv run mypy
   ```
   Expect: `Success: no issues found in 52 source files` — `tests/perf` is
   correctly outside the `[tool.mypy] packages = ["novetest"]` surface.

## Critical edge cases worth probing

- **Noisy-machine margin.** The benchmark passed at `median=0.024s` on the
  merge box — ~125x under the 3.0s internal budget. On a shared/loaded
  runner the median will be higher; the gate should still pass with wide
  margin, but a *single* timed run is not the gate (it takes the median of
  5 timed runs after 1 warm-up). If it ever fails, suspect runner
  contention before suspecting a `compare.py` regression.
- The benchmark uses a genuine non-trivial delta (50 files added / 50
  removed / 450 per-file deltas) — there is no zero-change fast path in
  `compare.py` that would make a trivial delta artificially fast.
- `compare_coverage_facts` / `compare.py` / `coverage_fact_set.from_dict`
  are **untouched** by this slice — no `src/` optimization was needed.

## Notes from the merge

- **Rebase conflict resolved:** `WORKLOG.md` conflicted because the
  jest-charmap slice (`310bc87`, merged just before this one) also added a
  top entry. Resolved surgically: both entries kept, ordered newest-commit
  first (`coverage-compare-perf` above `jest-charmap-encoding`). No content
  of either entry was altered — pure ordering merge.
- DoD: the handoff believes this closes **Phase 2 DoD #4** (NFR-COV-002 met
  on a 50k-location fixture). PM verifies + ticks `delivery-phasing.md` —
  not ticked by Main Branch.
