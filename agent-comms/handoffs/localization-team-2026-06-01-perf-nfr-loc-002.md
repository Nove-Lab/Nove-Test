---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-01
slug: perf-nfr-loc-002
base_commit: 6a3b801
worktree: /home/yjshin/dev/novetest-localization-perf-nfr-loc-002
branch: novetest-localization-perf-nfr-loc-002
related:
  - tasks/localization-team-2026-06-01-perf-nfr-loc-002.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/localization-strategy.md
  - design/requirements-analysis/requirements-specification/groups/localization.md
---

# Handoff: Phase 4 §4 #3 — perf NFR-LOC-002 closure

## TL;DR

- **Branch A outcome confirmed** (median **1.33 s** vs 8.0 s NFR ceiling
  + 5.0 s internal budget).
- **Branch trigger was Branch C** (initial median 9.85 s) → resolved
  via three surgical vectorization patches to `derive.py` (NOT a
  sparse-representation pivot in `spectra.py`); brief §5.5 Branch C
  authorized "vectorization improvements" explicitly.
- **3 perf tests added** (per-test / aggregate / failure_proximity) +
  1 helper module + 1 perf-tree init.
- **2 src files modified** (`derive.py` perf patches + `spectra.py`
  docstring); 0 new src files; source-file count stays at **72**.
- **Default suite gate green**: 771 + 10 (matches main baseline `6a3b801`).
- **mypy `--strict` clean**: 72 src files.
- **Phase 4 §4 #3 DoD bullet** ready to tick at PM cycle close →
  Phase 4 → **100% complete**.

## DoD bullets believed closed (PM verifies + ticks)

All 11 bullets from `tasks/localization-team-2026-06-01-perf-nfr-loc-002.md`
§"DoD":

- [x] `tests/perf/localization/` directory exists with helper + 3
      mode-specific test modules.
- [x] Builders synthesize CoverageFactSet + RunRecord at exact NFR-LOC-002
      scale (500 failed + 3000 passing TestResults + 50000 covered
      locations + per-test attribution for per-test mode).
- [x] Per-test mode median time **< 8.0 s** (NFR ceiling) AND
      **< 5.0 s internal budget** → **median 1.33 s** measured.
- [x] Aggregate mode median time < 5.0 s internal budget → **0.039 s**.
- [x] failure_proximity mode median time < 5.0 s internal budget →
      **0.018 s**.
- [x] `uv run pytest tests/perf -v` collects + passes all 3 new tests
      (plus the 3 pre-existing NFR-COV-002 tests still green).
- [x] `uv run pytest -q tests/unit tests/integration` still passes at
      baseline (no regression to the default suite; perf is outside
      `testpaths`).
- [x] `uv run mypy` clean on the new files.
- [x] `localization-strategy.md` §Open Items #3 (Open Q #11 — sparse
      matrix threshold) note added with empirical outcome.
- [x] `spectra.py` docstring updated reflecting empirical validation.
- [x] Handoff captures verbatim median time + mean + stdev for each of
      the 3 modes (this §"Empirical timings" + §"Branch outcome").

And the related (out-of-DoD-list, requires PM action):

- **`delivery-phasing.md:188`** Phase 4 §4 #3 bullet (`- [ ]`) — PM
  ticks at cycle close; this slice is the empirical closure.

## §"Empirical timings" — verbatim pytest output

Captured at the worktree tip via `uv run pytest tests/perf -v 2>&1 | tee
/tmp/perf-loc.log`:

```
[NFR-COV-002] compare_coverage_facts at 50,000 covered locations/side: median=0.035s over 5 runs (internal budget 3.0s, NFR ceiling 5.0s)
[NFR-LOC-002 / sbfl_aggregate] 500 failed × 50,000 locations: median=0.039s mean=0.041s stdev=0.006s over 5 runs (internal budget 5.0s, NFR ceiling 8.0s) timings=[0.039, 0.048, 0.036, 0.035, 0.046]
[NFR-LOC-002 / failure_proximity] 500 failed-log parses: median=0.018s mean=0.018s stdev=0.001s over 5 runs (internal budget 5.0s, NFR ceiling 8.0s) timings=[0.018, 0.018, 0.018, 0.017, 0.019]
[NFR-LOC-002 / sbfl_per_test] 3500 tests × 50,000 locations: median=1.328s mean=1.345s stdev=0.065s over 5 runs (internal budget 5.0s, NFR ceiling 8.0s) timings=[1.328, 1.423, 1.291, 1.403, 1.28]

============================== 7 passed in 10.72s ==============================
```

Per-mode summary:

| Mode | Median | Mean | Stdev | All 5 timings (s) | Budget | NFR ceiling |
|---|---|---|---|---|---|---|
| sbfl_per_test | **1.328 s** | 1.345 s | 0.065 s | 1.328, 1.423, 1.291, 1.403, 1.28 | 5.0 s | 8.0 s |
| sbfl_aggregate | **0.039 s** | 0.041 s | 0.006 s | 0.039, 0.048, 0.036, 0.035, 0.046 | 5.0 s | 8.0 s |
| failure_proximity | **0.018 s** | 0.018 s | 0.001 s | 0.018, 0.018, 0.018, 0.017, 0.019 | 5.0 s | 8.0 s |

### Pre-optimization measurement (Branch C trigger)

For the record — the first run on the same fixture BEFORE the three
vectorization patches landed:

```
[NFR-LOC-002 / sbfl_per_test] median=9.849s, durations=[9.849, 9.748, 9.753, 10.621, 10.266]
```

The dense path WITHOUT the patches would have been Branch C
(> 8.0 s NFR ceiling). cProfile against that pre-patch run identified:

```
  ncalls  cumtime  filename:lineno(function)
       1   9.991   derive.py:802(_aggregate_by_symbol)
    5000   6.945   derive.py:902(_related_failed_tests)    ← #1 hot path
   50000   2.687   derive.py:886(_resolve_repo_path)       ← #2 hot path
       1   1.634   derive.py:717(_count_vectors)
      17   0.697   {method 'astype' of 'numpy.ndarray' objects} ← in _count_vectors
       1   0.547   sbfl/spectra.py:67(build_spectra)
       1   0.599   coverage/persistence.py:53(read_coverage_facts)
```

The three patches target frames #1, #2, and the `.astype` allocation
inside `_count_vectors` respectively. See §"`derive.py` perf patches"
below for the diff narrative.

## §"Branch outcome"

**Branch A** (per §5.5 of the brief) — dense representation passes both
the 8.0 s NFR ceiling and the 5.0 s internal budget at NFR scale, with
~73% headroom (1.33 s vs 5.0 s budget).

**However**: this slice's path to Branch A passed through a **Branch C
trigger** (initial median 9.85 s before optimization). The brief §5.5
Branch C explicitly authorized "vectorization improvements" as an
alternative to sparse representation; this slice took that path. The
final outcome maps to Branch A per the brief's measurement-of-record
methodology (post-patches median is what gets logged).

Net effect on Open Q #11: sparse representation is **NOT** the binding
NFR constraint at NFR-LOC-002 scale; it stays a forward-looking
post-MVP concern for >NFR scales.

## §"Open Q #11 disposition"

Added to `design/implementation-plan/localization-strategy.md` §Open
Items #3:

```markdown
3. **Spectra-matrix size limits.** For very large suites (>10k tests x >100k lines), decide between sparse representation, sampling, or partition-by-target. Empirically validate at Phase 4 against the largest fixture project.
   - **Outcome 2026-06-01 (NFR-LOC-002 perf slice).** At the NFR-LOC-002 scale (500 failed-test references × 50,000 covered locations on a per-test spectra of shape 3500 × 50000), the **dense** representation passes both the 8.0 s NFR ceiling and the 5.0 s internal budget — median measured at **1.33 s** on the reference dev host via `tests/perf/localization/test_perf_derive_per_test.py`. Sparse representation is **not** the binding NFR constraint at this scale and is **deferred to post-MVP** for larger-than-NFR suites. The actual hot paths the slice surfaced were in `derive.py` (per-location `Path.resolve` + per-failed-row `.sum()` calls in `_aggregate_by_symbol`); both were vectorized in place without changing the spectra representation. Phase 4 §4 #3 is closed by this measurement.
```

## §"`spectra.py` docstring update"

Module-level docstring extended (no code change to `spectra.py`'s
behavior). Diff:

```diff
 Dense representation only at this slice. A sparse fallback is Open
 Question #11 (``design/implementation-plan/localization-strategy.md``
-Open Items / engine-adapters.md) — revisit when a real fixture exceeds
-the threshold; for Phase 4 entry the dense path satisfies NFR-LOC-002.
+Open Items §3 / engine-adapters.md) — revisit when a real fixture
+exceeds the threshold; for Phase 4 entry the dense path satisfies
+NFR-LOC-002.
+
+**Empirically validated 2026-06-01** at the NFR-LOC-002 scale (500
+failed-test references × 50,000 covered locations, per-test spectra
+of shape 3500 × 50000) via
+``tests/perf/localization/test_perf_derive_per_test.py``: median
+1.33 s on the reference dev host vs the 8.0 s NFR ceiling — comfortably
+under the 5.0 s internal budget. Open Q #11 (sparse repr threshold) is
+**not** the binding NFR constraint at this scale; the hot paths the
+perf slice surfaced were in ``derive.py`` (per-location
+``Path.resolve`` and per-failed-row ``.sum()`` calls in
+``_aggregate_by_symbol``) and were addressed there. Sparse
+representation stays a forward-looking concern for
+**larger-than-NFR** suites (post-MVP).
```

## §"`derive.py` perf patches"

Three surgical patches; all preserve byte-identical algorithmic output
(166 localization unit + integration tests still pass).

### Patch 1: `_count_vectors` — drop the int64 intermediate copy

Before:
```python
matrix = spectra.matrix.astype(np.int64)   # allocates 8x the matrix bytes
outcomes = spectra.test_outcomes.astype(np.int64)
failed_mask = outcomes == 1
passed_mask = outcomes == 0
...
ef = matrix[failed_mask].sum(axis=0).astype(np.int64)
ep = matrix[passed_mask].sum(axis=0).astype(np.int64)
```

After:
```python
failed_mask = spectra.test_outcomes == 1
passed_mask = spectra.test_outcomes == 0
...
ef = spectra.matrix[failed_mask].sum(axis=0, dtype=np.int64)
ep = spectra.matrix[passed_mask].sum(axis=0, dtype=np.int64)
```

Numpy accumulates in int64 directly while reading the uint8 cells in
place. Saves ~0.7 s wall + 1.4 GB intermediate at NFR scale. Same
numerical result.

### Patch 2: `_aggregate_by_symbol` — memoize per-file path resolution

The loop walks 50 k `spectra.locations` entries but only ~500 distinct
`file_path` strings. The pre-patch code ran `Path.resolve()` per entry
(syscall chain: `realpath` → many `lstat` calls). A per-file memo
collapses 50 k resolves to 500.

Added:
```python
absolute_path_cache: dict[str, Path] = {}
for j, (file_path, line) in enumerate(spectra.locations):
    absolute = absolute_path_cache.get(file_path)
    if absolute is None:
        absolute = _resolve_repo_path(store, file_path)
        absolute_path_cache[file_path] = absolute
    qualname, line_range = resolve_python_symbol(absolute, line)
    ...
```

Saves ~2.7 s at NFR scale.

### Patch 3: `_related_failed_tests` — vectorize the per-failed-row loop

Before (pre-patch):
```python
for i in failed_row_indices:
    row = spectra.matrix[i, col_indices]
    if int(row.sum()) > 0:
        matched_tests.add(spectra.test_ids[i])
```

After:
```python
col_indices_arr = np.asarray(col_indices, dtype=np.intp)
submatrix = spectra.matrix[np.ix_(failed_row_indices, col_indices_arr)]
touched_mask = np.any(submatrix != 0, axis=1)
touched_rows = failed_row_indices[touched_mask]
matched_tests = {spectra.test_ids[int(i)] for i in touched_rows}
```

One matrix slice + one vectorized `np.any` per call instead of 500
× 5000 = 2.5 M `.sum()` calls. Saves ~6 s at NFR scale.

### Why these patches are in scope

The brief §5.5 Branch C: "Implement sparse representation... OR
vectorization improvements... Implementer's choice on API shape."

The brief §"Out of scope" prohibits: public API surface changes,
formula module edits, CLI/orchestration surface edits, Coverage/Memory/
Run engine edits, mode-dispatch logic edits.

`derive.py`'s `_count_vectors`, `_aggregate_by_symbol`, and
`_related_failed_tests` are private helpers inside the Localization
engine's `derive_localization_findings` body. The public API surface,
algorithm semantics, persisted shape, and CLI envelope are all
unchanged. Within the brief's allowed scope.

## §"Phase 4 §4 #3 closure rationale"

NFR-LOC-002 verbatim: *"The system shall produce localization results
for a run with up to 500 failed-test references and 50,000 covered
locations within 8 seconds when required evidence is already stored
locally."*

This slice empirically demonstrates that
`derive_localization_findings(store, run_reference)` — the public API
entrypoint — completes in **median 1.328 s** at the NFR scale
(500 failed-test references in the RunRecord + 50,000 covered
locations in the persisted CoverageFactSet) over 5 timed runs with
1 untimed warm-up, with the evidence pre-stored via the real
`write_coverage_facts` + `store_run_evidence` helpers and the
findings cache explicitly invalidated between each timed iteration to
force the cold-derive path.

1.328 s ≪ 8.0 s NFR ceiling ≪ 5.0 s internal budget. **NFR met.**

The aggregate (0.039 s) and failure_proximity (0.018 s) modes are
also pinned within the same budget for completeness.

Phase 4 §4 #3 DoD bullet (`delivery-phasing.md:188`) is ready to tick.

## §"Open questions for PM"

1. **`delivery-phasing.md:188` tick**: this slice's empirical closure
   gives PM the rationale to tick the bullet. Confirm at cycle close.

2. **Phase 4 → 100% complete**: after this tick, Phase 4 §4 is 4/4.
   The brief's TL;DR says "MVP scope shrinks to Phase 3 JUnit/.NET +
   Phase 5 + Phase 6." Is there a `history/` entry PM wants to land
   for the Phase 4 closure? (Standard cycle close should produce one,
   but flagging in case PM wants a special entry consolidating the
   D1-D6 + perf cycle of June 2026 into a single Phase 4 retrospective.)

3. **`derive.py` perf patches as merge dependency**: the perf-tests
   FAIL without the three vectorization patches (median 9.85 s on the
   pre-patch path). Main Branch should merge the worktree as a single
   commit — the patches and the tests must land together. If a future
   slice ever reverts one of the patches without reverting the perf
   test, the perf gate would re-fail. This is the intended invariant
   (the perf test is the regression-pin), flagging for PM context.

4. **Sparse representation as post-MVP follow-up**: Open Q #11 is
   officially closed for MVP per the §"Open Q #11 disposition" note.
   Does PM want a separate `decisions/` entry recording the post-MVP
   deferral, or is the strategy-doc addendum sufficient? (Strategy doc
   is permanent; a decisions entry would mainly add a date-anchor for
   the "post-MVP" disposition.)

5. **Perf-suite CI gating (FYI, Release team's territory)**: brief's
   §"Out of scope" excludes adding a scheduled CI lane for perf, and I
   honored that. Flagging in case PM wants to queue a Release task for
   it now that the perf suite is in place (3 NFR-LOC-002 tests +
   pre-existing NFR-COV-002 tests = good content for a nightly perf
   lane). Not blocking this slice.

## §"Files changed (manifest for Main Branch FF-merge)"

```
src/novetest/localization/derive.py                     (modified — 3 perf patches)
src/novetest/localization/sbfl/spectra.py               (modified — docstring only)
tests/perf/localization/__init__.py                     (new — ~5 lines)
tests/perf/localization/generate_large_inputs.py        (new — ~370 lines)
tests/perf/localization/test_perf_derive_per_test.py    (new — ~140 lines)
tests/perf/localization/test_perf_derive_aggregate.py   (new — ~95 lines)
tests/perf/localization/test_perf_derive_failure_proximity.py (new — ~90 lines)
design/implementation-plan/localization-strategy.md     (modified — Open Items #3 addendum)
WORKLOG.md                                              (modified — perf-nfr-loc-002 entry)
agent-comms/handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md (new — this file)
agent-comms/INDEX.md                                    (modified — regenerated)
```

Source-file count: **72** (unchanged; 0 new src files).

## §"Verification commands (re-runnable by Main Branch + Manual Test)"

Default suite gate (the merge gate):
```sh
uv run pytest -q tests/unit tests/integration
# Expected: 771 passed, 10 skipped
```

mypy strict gate:
```sh
uv run mypy
# Expected: Success, no issues found in 72 source files
```

Perf suite (opt-in, captures NFR-LOC-002 empirical measurement):
```sh
uv run pytest tests/perf -v
# Expected: 7 passed; sbfl_per_test median around 1.3 s on a 2-GB+ dev host
```

Manual Test re-run note: the perf median will VARY by host (Coverage's
NFR-COV-002 precedent saw the same property). The assertion threshold
(5.0 s internal budget) gives ~3.7x headroom over the 1.33 s reference
median — comfortable margin for slower CI runners while still
catching real regressions. The 8.0 s NFR ceiling is the hard published
bound.

## Activity log

- 2026-06-01: branch created at base `6a3b801`, perf scaffolding
  written, initial pre-patch measurement → 9.85 s median → Branch C
  trigger. cProfile identified `_aggregate_by_symbol` hot paths. Three
  patches applied to `derive.py`. Post-patch measurement → 1.33 s
  median → Branch A outcome. Default suite + mypy clean. Strategy doc
  + spectra docstring + WORKLOG + handoff written. INDEX.md regen
  pending commit.
