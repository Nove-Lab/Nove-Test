---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-21
slug: coverage-compare-perf
related:
  - tasks/coverage-team-2026-05-20-coverage-compare-perf.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Handoff: NFR-COV-002 50k-location perf benchmark for `coverage diff`

## Worktree

- Path: `/home/yjshin/dev/novetest-coverage-compare-perf`
- Branch: `coverage/coverage-compare-perf` (branched from `main` @ `69c6c74`)

## Files added (all NEW; no `src/` change, no `pyproject.toml` change)

- `tests/perf/__init__.py` — perf-tree package shell.
- `tests/perf/coverage/__init__.py` — coverage perf package shell.
- `tests/perf/coverage/generate_large_fact_set.py` — pure `CoverageFactSet`
  generator: `generate_fact_set(run_id, num_files, lines_per_file,
  branches_per_file, *, file_offset=0)` + companion `perturb_for_delta`.
  Stdlib + `novetest.models` only; no disk I/O.
- `tests/perf/coverage/test_perf_compare.py` — the benchmark (3 tests).
- `WORKLOG.md` — appended `2026-05-21 — phase2 / coverage-compare-perf`.
- `agent-comms/` — this handoff + regenerated `INDEX.md`.

`tests/perf/` is deliberately OUTSIDE `[tool.pytest.ini_options].testpaths`
(`tests/unit` + `tests/integration`) — same precedent as `tests/release/`.
The default `uv run pytest` never collects it; **no pytest marker and no
`pyproject.toml` edit was needed** (`pyproject.toml` is Run/Release
territory). Opt in explicitly with `uv run pytest tests/perf`.

## Verification

- `uv run pytest tests/perf` → **3 passed**. Observed
  **`median=0.024s`** over 5 timed runs (internal budget 3.0s; NFR-COV-002
  ceiling 5.0s — ~125x headroom on the dev box).
- `uv run pytest -q` → **337 passed + 3 skipped** — baseline unchanged
  (the 3 skips are the pre-existing Node-dependent jest integration tests).
  `pytest --collect-only` confirms `tests/perf` is **not** collected by the
  default run.
- `uv run mypy` → **clean, 52 source files, `--strict`** (no `src/` change;
  `[tool.mypy]` scopes to `packages = ["novetest"]` so `tests/perf` is
  correctly outside the type-check surface — the test files still carry
  full type hints).

## DoD bullets believed closed (PM verifies + ticks — not ticked here)

- **Phase 2 DoD #4** — "Performance NFR-COV-002 met on a fixture with 50k
  covered locations." The benchmark exercises `compare_coverage_facts` at
  exactly 50,000 covered locations per side with both runs' evidence
  already stored locally; the median comparison time is far under the 5s
  NFR (and under the 3s internal budget). This is the last open Phase 2
  bullet.

## Contract-shape surprises / notes

1. **The task's pinned numbers are slightly over-constrained.** It pins
   "exactly 50,000 covered locations per fact set" AND a delta with literal
   index ranges "0-399 common / 400-449 removed / 450-499 added". Those
   literal ranges give only 450 files/side = 45,000 locations, which
   contradicts the 50k figure. The interpretation section's "~50k" /
   "both sides independently reach ~50k" gave the latitude to reconcile:
   each side is a full **500-file** fact set at **exactly 50,000**
   locations; the target's `file_offset=50` shift yields 450 common paths,
   50 baseline-only (`files_removed`), 50 target-only (`files_added`).
2. **Common-file transitions are a SWAP, not an additive "gain".**
   `perturb_for_delta` swaps each file's last 5 executed lines + last 1
   branch for fresh locations. A swap keeps the covered-location count
   invariant (both sides stay at exactly 50,000); the literal "gains 5
   newly-covered lines" would push the target to ~52,500. The swap also
   produces a *stronger* per-file delta (5 covered + 5 uncovered lines,
   1 + 1 branches).
3. **`compare.py` has no zero-change early-return.** The task warned that
   "a zero-change delta hits the early-return guard and is artificially
   fast" — in fact `_build_delta`'s compact-payload guard only skips
   *appending* an unchanged `FileCoverageDelta`; `_file_delta` still runs
   its set-diffs for every common path. So a trivial delta is barely
   cheaper. `perturb_for_delta` is retained for *faithfulness* (a realistic
   non-empty delta the test asserts on) rather than for runtime impact.
4. **No `src/` optimization was needed.** The performance-engineer review
   estimated ~1-2s dominated by `from_dict` deserialization; on the dev box
   the median is 0.024s. `compare.py` and `coverage_fact_set.from_dict` are
   untouched — the frozen `coverage_facts.json` v1 schema is unaffected.
5. **Import path.** With pytest `prepend` import mode and
   `tests/perf/__init__.py` / `tests/perf/coverage/__init__.py` but no
   `tests/__init__.py`, `tests/` is inserted on `sys.path`; the benchmark
   imports its generator as `from perf.coverage.generate_large_fact_set
   import ...` (same resolution `tests/release/` relies on).

## For the companion Release task (PM note)

The perf test is runnable as a standalone lane via `uv run pytest
tests/perf`. It needs the dev dependencies already in `pyproject.toml`
(`pytest`, `pytest-asyncio`); no new dependency was added. Recommend a
**non-blocking** CI job — a 5s budget on shared runners should not gate
PRs.
