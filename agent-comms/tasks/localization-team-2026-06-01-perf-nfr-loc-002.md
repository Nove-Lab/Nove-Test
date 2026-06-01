---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-01
slug: perf-nfr-loc-002
related:
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/localization-strategy.md
  - design/requirements-analysis/requirements-specification/groups/localization.md
  - tests/perf/coverage/test_perf_compare.py
  - src/novetest/localization/sbfl/spectra.py
  - src/novetest/localization/derive.py
---

# Task: Phase 4 §4 #3 — perf NFR-LOC-002 benchmark + closure

## TL;DR

The LAST remaining Phase 4 §4 DoD bullet. Build a perf benchmark at
NFR-LOC-002's documented scale (500 failed tests + 50k covered
locations) and demonstrate `derive_localization_findings` completes
within 8 seconds. Mirror the Phase 2 §NFR-COV-002 precedent
(`tests/perf/coverage/test_perf_compare.py`, commit `5489c7e`) for
directory structure, statistical methodology, and budget headroom.

This slice closes **Phase 4** (the remaining 1/4 bullet is this one;
the other 3 are already ticked). After this slice, Phase 4 →
**100% complete** → MVP scope shrinks to Phase 3 JUnit/.NET +
Phase 5 + Phase 6.

Per `src/novetest/localization/sbfl/spectra.py` docstring's
self-claimed gate: "Dense representation only at this slice. ... for
Phase 4 entry the dense path satisfies NFR-LOC-002." This slice
**empirically validates that claim**. If validated → ship as-is. If
not validated → optimize (sparse representation OR vectorization
review OR Top-N early pruning) until validated.

## Why this slice exists (product framing)

NFR-LOC-002 is a **published MVP exit criterion**. The localization
strategy doc (`design/implementation-plan/localization-strategy.md`)
explicitly carries Open Q #11 about spectra matrix size on large
suites — this slice closes the question with empirical data.

Practical scale: 500 failed tests + 50k covered locations is the
Defects4J-class real bug scale. Without this NFR, AI agents
debugging real-world projects could hit unpredictable seconds-to-
minutes localization times on the per-test mode. With it pinned,
agent + user experience is **bounded predictably**.

After this slice:
- Phase 4 ✅ complete (3/4 → 4/4 bullets ticked)
- `derive_localization_findings` is performance-pinned at the
  documented scale
- Open Q #11 (sparse matrix threshold) gets a concrete answer
  (either "dense suffices at NFR scale" OR "sparse needed; here's the
  threshold")
- MVP gate: one bullet less to land

## NFR-LOC-002 verbatim (source of truth)

From `design/requirements-analysis/requirements-specification/groups/localization.md`:

> The system shall produce localization results for a run with **up to
> 500 failed-test references** and **50,000 covered locations** within
> **8 seconds** when required evidence is already stored locally.

Key phrasing parsed:
- "produce localization results" — `derive_localization_findings(store, run_reference, formula=..., top_n=...)` is the public API entrypoint to time
- "up to 500 failed-test references" — fixture has 500 `TestResult` rows with `outcome == "failed"`
- "50,000 covered locations" — `CoverageFactSet.files[*].line_contexts` aggregates to 50,000 distinct `(file_path, line)` tuples
- "within 8 seconds" — hard NFR ceiling; internal pass budget is tighter (see §5.4 statistical methodology)
- "when required evidence is already stored locally" — `coverage_facts.json` + `record.json` pre-written to the store BEFORE the timed region (mirrors Phase 2 NFR-COV-002's stored-locally semantics)

## Reference precedent — `tests/perf/coverage/test_perf_compare.py` (commit `5489c7e`)

Phase 2 §NFR-COV-002 (50,000 covered locations within 5s) was closed
2026-05-21. **Mirror this slice on that file's structure**:

### What the Coverage precedent pinned

1. **File location**: `tests/perf/coverage/test_perf_compare.py`
   — OUTSIDE `[tool.pytest.ini_options].testpaths` so `uv run pytest`
   default DOES NOT collect it. Explicit invocation:
   `uv run pytest tests/perf` to run perf tests.
2. **Helper module**: `tests/perf/coverage/generate_large_fact_set.py`
   — synthesizes the in-memory CoverageFactSet at the NFR scale
   (avoids needing a real 50k-line fixture project).
3. **Timed region**: the **real public API** call, including on-disk
   load + `from_dict` parse. Test execution is OUT of scope (the
   evidence is pre-stored).
4. **Statistical methodology**: 1 untimed warm-up call (page-cache
   priming) + 5 timed calls; assert on **median**.
5. **Budget headroom**: internal budget < NFR ceiling. Coverage used
   3.0s internal vs 5.0s NFR (40% headroom for CI variance).
   **For Localization, use 5.0s internal vs 8.0s NFR** (37.5%
   headroom — matches Coverage's 60% ratio; see §5.4).
6. **Result reporting**: median time (rounded to ms or finer)
   captured in the test output + in the handoff for PM records.
7. **Observed outcome on Coverage**: median 0.024s vs 5.0s NFR
   (Manual Test report). The Coverage path was ~200x under budget.
   Localization per-test mode may not have the same headroom — the
   matrix is dense and bigger.

The Coverage precedent's exact source is the LIVING template for
this slice. Read it before implementing.

## Scope (what this slice DOES)

### 5.1 Build the perf-benchmark directory structure

**Create**:
- `tests/perf/localization/__init__.py`
- `tests/perf/localization/generate_large_inputs.py` (helper —
  synthesizes the CoverageFactSet + RunRecord pair at NFR scale)
- `tests/perf/localization/test_perf_derive_per_test.py` (the
  load-bearing perf test — per-test mode, the SBFL matrix worst case)
- `tests/perf/localization/test_perf_derive_aggregate.py` (secondary
  — aggregate mode at same scale; should be much easier)
- `tests/perf/localization/test_perf_derive_failure_proximity.py`
  (tertiary — failure_proximity mode parsing 500 failure logs)

Mirror `tests/perf/coverage/` shape exactly (one helper module + one
test module per timed surface). The localization slice has 3 timed
surfaces (3 modes) vs Coverage's 1 (just `compare_coverage_facts`),
hence 3 test files instead of 1.

### 5.2 `generate_large_inputs.py` — synthesize NFR-scale inputs in-memory

The helper module exposes 3 builder functions, one per mode. Each
returns:
- A `CoverageFactSet` (per-test or aggregate as appropriate)
- A `RunRecord` (with 500 failed + 3000 passing TestResults; see
  §5.2.1 for the passing count rationale)
- A `RunReference`

The builders **write to a real `ProjectStore`** (via
`write_coverage_facts` + `store_run_evidence`) before the test
begins. The timed region (in §5.3) reads from this store — matching
NFR's "evidence is already stored locally" semantics.

#### 5.2.1 Per-test mode builder: `build_per_test_inputs(store)`

**Inputs to synthesize**:
- 500 failed TestResults + **3000 passing TestResults** = 3500 total
  - Rationale for 3000 passing: realistic Defects4J-class projects
    have 5-10x passing-to-failing ratio. 6x = 3000 passing. The NFR
    only constrains the failed count (≤500); passing count is a
    realistic-benchmark choice, not NFR-dictated.
  - Lower bound (degenerate): 0 passing → SBFL ranks degenerate (all
    failed tests touch everything → ties everywhere). Not useful.
  - Upper bound (pessimistic): 10000 passing → ~10x more matrix
    rows. Defensible but not in NFR. Skip — stick with 3000.
- 50,000 covered locations distributed across **500 source files ×
  100 lines per file** = 50,000 (file, line) pairs
  - Rationale: real projects rarely have a 50k-line single file. 500
    × 100 mirrors a medium-large monorepo. Iteration over 500 files
    also stresses the spectra builder's outer loop.
- **Per-test coverage attribution** (the `line_contexts` field):
  each test executes a **realistic-sparse** subset of locations:
  - Each test touches ~500 locations on average (1% of total)
  - Distribution: failed tests cluster around a "buggy file"
    (`src/buggy_<N>.py`) with high overlap; passing tests spread
    more evenly
  - **Goal**: produce a spectra that is **NOT** uniformly dense
    (which would not exercise the realistic case) AND NOT
    pathologically sparse (which would understate the worst case)
  - Concretely: implement as `seed_per_test_coverage(...)` with
    deterministic RNG (fixed seed) so the benchmark is **reproducible
    across runs** (Coverage perf has the same property — Manual Test
    re-runs need to match)

Memory expectation: numpy uint8 matrix at 3500 × 50000 = **175 MB**
of dense matrix. Add ~20% overhead for index dicts, location tuples,
test_outcomes array, etc. Total ~210MB. Tractable for any modern
development host; the CEO's dev box has been verified at this scale
indirectly (cargo coverage + LCOV parse handled ~62-line LCOV cleanly
— this is the multi-MB regime instead).

If a CI cell has constrained memory (e.g., 1GB containers), this
benchmark may not run there — that's fine because perf benchmarks are
outside `pytest -q` by design.

#### 5.2.2 Aggregate mode builder: `build_aggregate_inputs(store)`

**Inputs**:
- 500 failed + 3000 passing TestResults (same as per-test)
- 50,000 covered locations (same scale)
- `CoverageFactSet.mapping_granularity = "aggregate"` (no per-test
  `line_contexts`; only file-level `executed_lines`)
- Failure log files attached to TestResults so the algorithm's
  `parse_failure_log` step can lift file references

Memory expectation: much smaller — no matrix. Just the aggregate
coverage dict + 500 failure log strings (~1KB each = 500KB). Total
~2-5MB.

#### 5.2.3 failure_proximity mode builder: `build_failure_proximity_inputs(store)`

**Inputs**:
- 500 failed TestResults (no passing tests required — aggregate path
  doesn't use them)
- `CoverageFactSet` is **NOT stored** (mode triggered by
  `CoverageUnavailable` upstream)
- 500 failure log files with realistic stack trace shapes (pytest +
  cargo + jest + go test mixed if cross-engine probe is desired; OR
  single-engine 500 logs)

Memory expectation: minimal — just the 500 log files. <1MB.

### 5.3 Test bodies — per-mode benchmarks

Each test module mirrors `test_perf_compare.py`'s pattern:

```python
def test_perf_derive_per_test_meets_nfr_loc_002(tmp_path):
    store = create_project_store(tmp_path)
    inputs = build_per_test_inputs(store)
    # Untimed: cache priming
    derive_localization_findings(store, inputs.run_reference)

    # Timed: 5 calls
    timings = []
    for _ in range(5):
        # Cache the persisted findings would interfere — UNLINK
        # before each call so we measure the cold-derive path
        # (matches NFR's "produce localization results" semantics:
        # the timed work is the actual SBFL pipeline, not a
        # cache-read).
        findings_file = inputs.findings_cache_path
        if findings_file.exists():
            findings_file.unlink()

        start = time.perf_counter()
        result = derive_localization_findings(store, inputs.run_reference)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        assert isinstance(result, LocalizationFinding)
        assert result.mode == "sbfl_per_test"

    median = statistics.median(timings)
    print(f"NFR-LOC-002 per-test median: {median:.3f}s")  # captured by pytest

    INTERNAL_BUDGET_S = 5.0   # < 8.0s NFR; matches Coverage's 60% ratio
    assert median < INTERNAL_BUDGET_S, (
        f"NFR-LOC-002 per-test: median {median:.3f}s exceeds internal "
        f"budget {INTERNAL_BUDGET_S}s (NFR ceiling 8.0s). "
        f"timings={timings}"
    )
```

**Critical point on cache invalidation**: the slice's Defect-5 fix
(2026-06-01, `4895847`) made the orchestration layer unlink the
findings file before re-derive on flag mismatch. The perf test
should explicitly unlink between iterations so it measures the
**cold-derive path**, NOT the cache-read path (which would be ~0
seconds and meaningless). The NFR specifies "produce localization
results" — that means the actual SBFL pipeline, not a cache hit.

Mirror this pattern for the aggregate and failure_proximity modes,
with their respective assertions on `result.mode`.

### 5.4 Statistical methodology

Mirror Coverage perf precedent verbatim:

| Aspect | Value | Rationale |
|---|---|---|
| Warm-up iterations | 1 (untimed) | Page-cache priming |
| Timed iterations | 5 | Enough for stable median; cheap to run |
| Statistic | median | Robust to one slow outlier from background CPU contention |
| Worst-case check | none (median only) | Coverage didn't either; CI variance can spike one iteration |
| Internal budget | 5.0s | < 8.0s NFR; 37.5% headroom for CI variance |
| Hardware assumption | development host with ≥2GB RAM | Documented; not enforced |
| Reproducibility | fixed RNG seed in `generate_large_inputs.py` | Across runs same matrix is built |

Optional stretch: also report mean + stdev in the print output so
Manual Test can see distribution shape. Not gated on the assertion.

### 5.5 Tuning paths (BRANCH POINT — depends on §5.3 measurement)

**Branch A** — Per-test dense path passes 5.0s budget on first measurement:
- **Action**: ship as-is. Add a 1-line comment in `spectra.py`
  noting that NFR-LOC-002 was empirically validated against dense
  representation; the sparse-fallback Open Q #11 stays open as
  documented forward-looking concern for **larger-than-NFR scales**
  (post-MVP).
- **Closes**: Phase 4 §4 #3, Open Q #11 partially (downsized to
  "post-MVP scale-up question" rather than "MVP gate")

**Branch B** — Per-test dense path EXCEEDS 5.0s budget but PASSES
8.0s NFR ceiling (5.0s < median < 8.0s):
- **Action**: ship the benchmark + documentation of the measurement.
  Phase 4 §4 #3 ✅ ticks (NFR met). BUT file a low-priority
  follow-up task: "Localization perf budget headroom" —
  investigate sparse representation OR vectorization
  improvements that would restore ~60% headroom (matching
  Coverage's pattern).
- **Closes**: Phase 4 §4 #3
- **Queues**: follow-up task for sparse repr

**Branch C** — Per-test dense path EXCEEDS 8.0s NFR ceiling:
- **Action**: this slice CANNOT close until the NFR is met.
  Implement sparse representation in `sbfl/spectra.py` (scipy.sparse
  csr_matrix or hand-rolled equivalent). Re-measure. Iterate until
  median < 5.0s internal budget.
- **Effort**: +2-4 days
- **Closes**: Phase 4 §4 #3, Open Q #11

**PM recommendation on which branch is likely**: based on the
`spectra.py` docstring's self-claim ("for Phase 4 entry the dense
path satisfies NFR-LOC-002") and the numpy-vectorized formula
implementations, Branch A or Branch B are likely. The matrix size
(175MB) is large but numpy operations on dense uint8 arrays are
extremely fast — the formula compute should be sub-second. The
likely bottleneck (if any) is `build_spectra`'s two-pass walk over
`line_contexts` (pure Python dict ops, not numpy). If the budget is
tight, that's the first place to look at vectorization.

### 5.6 Documentation updates (always — both branches)

Regardless of branch outcome, **always** update:

1. **`design/implementation-plan/localization-strategy.md` Open
   Items section**: append a note for Open Q #11 stating the
   empirical outcome of this slice's measurement. Example:
   > "Open Q #11 outcome 2026-06-01: at NFR-LOC-002 scale (500
   > failed × 50k locations), the dense representation
   > [validates / does not validate] within the 8s budget.
   > Median observed: X.XXXs. [Sparse representation deferred to
   > post-MVP / required during the slice / implemented at commit
   > Y]."

2. **`src/novetest/localization/sbfl/spectra.py` docstring**: the
   current docstring's "for Phase 4 entry the dense path satisfies
   NFR-LOC-002" claim becomes either validated (small note pointing
   at the perf test) OR superseded (sparse path lands in this
   slice). Update accordingly.

3. **WORKLOG.md**: standard cycle entry.

## Out of scope (do NOT touch)

- **`derive_localization_findings`'s public API surface** — perf
  pinned by benchmark, not by API change.
- **The 4 formula modules** (`ochiai.py`, `op2.py`, `dstar.py`,
  `tarantula.py`) — already numpy-vectorized; should not need
  changes unless the formulas turn out to be the bottleneck (which
  the precedent's behavior strongly suggests they won't).
- **The CLI / orchestration surface** — perf is engine-level; CLI
  surface stays unchanged.
- **Coverage / Memory / Run** territories — this slice is purely
  Localization.
- **`localization-strategy.md` design content** beyond the Open
  Items note in §5.6.
- **Mode dispatch logic** — the 3 modes were closed in the
  2026-06-01 D5/D6 cycle. This slice only benchmarks them.
- **CI matrix changes** — perf tests stay opt-in via the
  `tests/perf` path. Release team's future CI work may add a
  scheduled perf lane; not this slice's concern.

## Concrete file map (pinned)

| File | Action | Lines (estimate) |
|---|---|---|
| `tests/perf/localization/__init__.py` | NEW | ~5 |
| `tests/perf/localization/generate_large_inputs.py` | NEW | ~250-350 (3 builders + helpers) |
| `tests/perf/localization/test_perf_derive_per_test.py` | NEW | ~80-120 |
| `tests/perf/localization/test_perf_derive_aggregate.py` | NEW | ~80-100 |
| `tests/perf/localization/test_perf_derive_failure_proximity.py` | NEW | ~70-100 |
| `src/novetest/localization/sbfl/spectra.py` | EDIT (docstring only — Branch A/B) OR src change (Branch C, sparse repr) | +5 / -2 (A/B) OR +100 / -30 (C) |
| `design/implementation-plan/localization-strategy.md` | EDIT (§Open Items note for Q#11) | +8 / -0 |
| `WORKLOG.md` | EDIT (top entry) | +8 / -0 |
| `agent-comms/handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md` | NEW | the handoff itself |

NOTE on Branch C: if sparse representation lands in this slice, the
`sbfl/{ochiai,op2,dstar,tarantula}.py` formula modules need to
accept BOTH dense and sparse spectra (or only sparse with a
conversion at the edge). Implementer's choice on API shape.

## Pre-flight checks (before opening handoff)

1. **Read the Coverage precedent**:
   `tests/perf/coverage/{test_perf_compare.py,generate_large_fact_set.py}`
   — DO NOT skip this. The structural details (warm-up + 5 timed +
   median assertion + budget pattern + RNG seed for reproducibility)
   are all there and should be mirrored.

2. **Full gate green** (regular suite):
   `uv run pytest -q tests/unit tests/integration`
   - Baseline tip (`6660a54`): **776 + 5** on equipped host.
   - Your tip after this slice = baseline (no regression to the
     default suite; perf tests are OUTSIDE `testpaths`).

3. **Perf suite passes**:
   `uv run pytest tests/perf -v`
   - All 3 new tests pass.
   - Print outputs show median times for each mode.
   - Coverage's existing `test_perf_compare` still passes.

4. **mypy strict clean** on the new tests/perf/localization files.

5. **Manual run with timing capture** — capture verbatim output for
   the handoff:
   ```sh
   uv run pytest tests/perf/localization -v 2>&1 | tee /tmp/perf-loc.log
   ```
   Each test should print its median + (recommended) mean+stdev.
   Paste these into the handoff verbatim — PM uses them as the
   empirical record for the Open Q #11 note + the DoD tick rationale.

6. **Memory sanity** — `tests/perf/localization/test_perf_derive_per_test.py`
   should not OOM on a development host with ≥2GB free RAM. If
   memory becomes a constraint, document the high-water mark in
   the handoff.

## DoD (definition of done for this slice)

- [ ] `tests/perf/localization/` directory exists with helper +
      3 mode-specific test modules.
- [ ] Builders synthesize CoverageFactSet + RunRecord at exact
      NFR-LOC-002 scale (500 failed + 3000 passing TestResults +
      50000 covered locations + per-test attribution for per-test
      mode).
- [ ] Per-test mode median time **< 8.0s** (NFR ceiling) AND
      **< 5.0s internal budget** (if 5.0s ≤ median < 8.0s, see
      §5.5 Branch B disposition).
- [ ] Aggregate mode median time **< 5.0s internal budget** (much
      easier; should be sub-second).
- [ ] failure_proximity mode median time **< 5.0s internal budget**
      (easiest; should be sub-100ms).
- [ ] `uv run pytest tests/perf -v` collects + passes all 3 new
      tests.
- [ ] `uv run pytest -q tests/unit tests/integration` still passes
      at baseline (no regression to the default suite; perf is
      outside `testpaths` and shouldn't be touched by `-q`).
- [ ] `uv run mypy` clean on the new files.
- [ ] `localization-strategy.md` Open Items §Q#11 note added with
      empirical outcome.
- [ ] `spectra.py` docstring updated reflecting empirical validation
      OR sparse-repr landing (depending on branch).
- [ ] Handoff captures verbatim median time + (recommended) mean +
      stdev for each of the 3 modes.

## Handoff format

Standard handoff at
`agent-comms/handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **§"Empirical timings"** — verbatim pytest print output for the
   3 mode tests. Include median, mean, stdev (if measured),
   individual timings list.
3. **§"Branch outcome"** — explicit statement of which §5.5 branch
   the slice ended up in (A / B / C). If B or C, follow-up
   recommendations.
4. **§"Open Q #11 disposition"** — quote the addendum you added to
   `localization-strategy.md` Open Items.
5. **§"`spectra.py` docstring update"** — the diff (small).
6. **§"Phase 4 §4 #3 closure rationale"** — explicit assertion that
   the NFR is empirically met. PM ticks the DoD bullet at cycle
   close.
7. **Open questions for PM** — anything the brief didn't anticipate
   (especially: any vectorization-vs-sparse design decisions made
   under Branch C; any memory-pressure observations on the dev
   host).

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry (newest on top, 5-bullet format).
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + new `agent-comms/` files + `INDEX.md` +
   `design/implementation-plan/localization-strategy.md` (Open Q
   note) + new `tests/perf/localization/*` + (Branch C only)
   modified `src/novetest/localization/sbfl/*` alongside the
   commit. The PreToolUse hook will block if `src/` or `tests/`
   are staged without `WORKLOG.md`.

## Cross-references

- **Phase 4 §4 #3 DoD bullet location**:
  `design/implementation-plan/delivery-phasing.md:188`
  — currently `- [ ]`; PM ticks at cycle close.
- **NFR-LOC-002 verbatim**:
  `design/requirements-analysis/requirements-specification/groups/localization.md`
  line 25.
- **Coverage perf precedent (LIVING template)**:
  `tests/perf/coverage/test_perf_compare.py` (the file's docstring
  pins the full methodology; mirror it).
- **Coverage perf helper** (LIVING template for `generate_large_inputs.py`):
  `tests/perf/coverage/generate_large_fact_set.py`.
- **Spectra current implementation** (the dense path being
  benchmarked):
  `src/novetest/localization/sbfl/spectra.py`.
- **Open Q #11 (sparse matrix threshold)**:
  `design/implementation-plan/localization-strategy.md` §Open
  Items.
- **Defect 5 cache-invalidation fix (relevant for cold-derive
  timing semantics)**:
  `agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`
  §"Defect 5".
- **Strategy doc on degradation modes (per-mode complexity
  background)**:
  `design/implementation-plan/localization-strategy.md` §2.
- **History of the 6-defect arc that LED to this slice**:
  `agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`.

## Estimated effort

- **Branch A (dense passes 5.0s)**: ~2 days. Benchmark scaffolding +
  measurement + documentation.
- **Branch B (dense between 5.0-8.0s)**: ~2.5 days. Same as A + a
  follow-up task brief.
- **Branch C (dense fails 8.0s)**: ~5-7 days. Same as A + sparse
  representation implementation in `sbfl/spectra.py` + formula
  module adaptations + re-measure cycle until pass.

PM's expected outcome: **Branch A**, ~2 days. (`spectra.py`
docstring self-claim is the implementing team's prediction; numpy
vectorization makes formula compute fast; the matrix size is large
but well within numpy's comfort zone.)
