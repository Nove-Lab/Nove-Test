---
from: novetest-pm-team
to: all
type: history
created: 2026-06-01
slug: phase4-complete-perf-nfr-loc-002
related:
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/localization-strategy.md
  - design/requirements-analysis/requirements-specification/groups/localization.md
---

# History: 2026-06-01 cycle — **Phase 4 §4 #3 perf NFR-LOC-002 closed; Phase 4 → 100% complete**

Solo Localization-team cycle. Verdict **passed**. This slice closes
the last unticked Phase 4 §4 DoD bullet (`delivery-phasing.md:188`).
**Phase 4 → 100% complete.** Remaining MVP scope: Phase 3 JUnit/.NET
adapters (gated on Open Q #4/#5) + Phase 5 (Replay engine + SQLite
derived index) + Phase 6 (MCP transport / release polish).

## Slice in scope

| Team | Commit | Verdict |
|---|---|---|
| Localization (perf NFR-LOC-002) | `36c6b82` | passed |

Lineage: PM brief queued (`6a3b801`) → Localization team handoff
→ Main Branch FF-merge as `36c6b82` → Manual Test findings
(`f7e611e`).

## What shipped

### The empirical NFR validation

3 perf tests live under `tests/perf/localization/` — outside
`[tool.pytest.ini_options].testpaths`, so they don't run on the
default `pytest -q` invocation (same pattern as the Coverage
NFR-COV-002 precedent `tests/perf/coverage/`).

The headline assertion (per-test mode, 3500 tests × 50,000 covered
locations, 5 timed iterations + 1 warm-up, median assertion):

```
[NFR-LOC-002 / sbfl_per_test] 3500 tests × 50,000 locations:
  median=1.328s mean=1.345s stdev=0.065s over 5 runs
  (internal budget 5.0s, NFR ceiling 8.0s)
  timings=[1.328, 1.423, 1.291, 1.403, 1.28]
```

Plus the two other modes for completeness:

| Mode | Median (team host) | Budget | NFR ceiling |
|---|---|---|---|
| `sbfl_per_test` | **1.328 s** | 5.0 s | 8.0 s |
| `sbfl_aggregate` | 0.039 s | 5.0 s | 8.0 s |
| `failure_proximity` | 0.018 s | 5.0 s | 8.0 s |

### Cross-host validation (3 data points)

| Source | per-test median | Stdev | host class |
|---|---|---|---|
| Team handoff | 1.328 s | 0.065 s | fast Intel laptop |
| Main Branch worktree | 1.297 s | 0.048 s | fast Intel laptop |
| Manual Test host | 1.281 s | 0.049 s | fast Intel laptop (i7-13700H, 20 logical cores) |

All three medians sit in a ~50 ms window. Same regime confirmed.
**Caveat**: all three hosts are fast Intel laptops; no slow CI
runner / ARM / sub-2-GHz core data point yet. See "Carry-forwards"
below.

## The non-obvious story: Branch C trigger → Branch A outcome

The brief §5.5 anticipated three branches based on initial
measurement:

- Branch A: dense path < 5.0 s budget → ship as-is
- Branch B: 5.0 s ≤ median < 8.0 s → ship + queue follow-up
- Branch C: median ≥ 8.0 s → sparse representation OR vectorization

**Initial pre-patch measurement on the same fixture: median 9.85 s.**
This was a Branch C trigger.

The team chose the **vectorization path** (brief §5.5 Branch C
explicitly authorized "vectorization improvements" as an alternative
to sparse representation). cProfile against the pre-patch run
identified three hot paths:

```
  ncalls  cumtime  function
       1   9.991   derive.py:_aggregate_by_symbol  (outer)
    5000   6.945   derive.py:_related_failed_tests  ← #1
   50000   2.687   derive.py:_resolve_repo_path    ← #2
       1   1.634   derive.py:_count_vectors        ← #3
```

Three surgical patches to `derive.py` private helpers:

1. **`_count_vectors`** — drop the upfront `matrix.astype(np.int64)`
   intermediate copy. Replaced with `sum(axis=0, dtype=np.int64)` on
   the masked uint8 cells. Saves ~0.7 s wall + 1.4 GB intermediate
   at NFR scale.
2. **`_aggregate_by_symbol`** — memoize per-file `Path.resolve()`.
   50,000 location entries collapse to ~500 distinct files; per-file
   memo turns 50,000 `realpath`/`lstat` syscall chains into 500.
   Saves ~2.7 s.
3. **`_related_failed_tests`** — vectorize the per-failed-row loop.
   Replaced `for i in failed_row_indices: row.sum() > 0` with one
   `np.ix_` slice + `np.any(submatrix != 0, axis=1)`. Saves ~6 s.

**Result: 9.85 s → 1.328 s (7.4x speedup) without changing public
API, persisted shape, CLI envelope, or any of the 166 existing
Localization unit + integration tests.**

Algorithmic semantics preserved byte-identically: Manual Test
captured 16/16 fields exact on the `localization-branch` fixture
(`divide` top-1 with `score_raw: 1.0` under Ochiai, plus the more
subtle `alternate_scores: {'dstar2': 0.0, 'op2': 1.0,
'tarantula': 1.0}`).

### Why this maps to Branch A (not Branch C) in retrospect

The Branch C trigger fired, but the **disposition** is Branch A
because the post-patch median (1.328 s) passes both the 5.0 s
internal budget and the 8.0 s NFR ceiling at NFR scale. The brief's
measurement-of-record methodology is "post-patches median is what
gets logged" — same as how the Coverage NFR-COV-002 precedent
recorded its closing median, not its development-time intermediate.

### Open Q #11 disposition

Open Q #11 (sparse-matrix representation threshold) is **NOT** the
binding NFR constraint at NFR-LOC-002 scale. The hot paths the perf
slice surfaced were all in `derive.py` (per-location `Path.resolve`
+ per-failed-row `.sum()` calls in `_aggregate_by_symbol`), not in
`spectra.py`'s dense matrix construction.

Disposition (now in `localization-strategy.md` §Open Items #3):
**dense representation suffices at NFR scale**; sparse representation
deferred to post-MVP for larger-than-NFR suites (>10k tests ×
>100k lines).

The `spectra.py` module docstring was also updated to reflect this
empirical validation. No code change in `spectra.py`.

## DoD bullets ticked in `delivery-phasing.md`

- **Phase 4 §4 #3** (line 188) — Performance NFR-LOC-002 met.
  **Phase 4 → 100% complete.**

## Phase 4 → 100% complete

All four Phase 4 §4 DoD bullets are now ticked:

| # | Bullet | Closed by | Date |
|---|---|---|---|
| 1 | `localization-branch` ranks top-3 | `385e2dc` | 2026-05-29 |
| 2 | Mode field populated across 3 fixtures | `804690b`+`3ccfd72`+`05f86bc` | 2026-06-01 |
| 3 | NFR-LOC-002 met (500×50k <8s) | `36c6b82` | **2026-06-01 (this cycle)** |
| 4 | All four formulas computed + persisted | `385e2dc` | 2026-05-29 |

## Carry-forwards (NOT queued — Manual Test's recommendations)

### Sub-obs #1: Peak RSS ~3x team estimate

Team estimated ~210 MB peak RSS for the per-test benchmark
(`3500 × 50000` uint8 matrix + indexes). Manual Test measured via
`/usr/bin/time -v`: **609 MB peak** on their host (3x). The team's
estimate was the numpy structures alone; the observed envelope
includes `uv run` + pytest framework + numpy 2.4.6 runtime overhead
+ the actual SBFL working set.

Not a regression — perf test makes no memory assertion. But if a
future cycle wants firmer memory-bound regression detection, a
`psutil.Process().memory_info().rss < 1 GB` smoke assertion would
catch future bloat early.

**Status: deferred carry-forward**, not queued.

### Sub-obs #2: 3-host data set is "all fast Intel"

Team + Main Branch + Manual Test all measured per-test median in
1.28-1.33 s range. None are slow CI runners or ARM hosts or
sub-2-GHz cores. The NFR-COV-002 precedent showed ~10x host
variance; if a slow CI runner sees 13 s, it would EXCEED the 8.0 s
NFR ceiling — uncomfortably possible.

The 5.0 s internal budget gives ~3.7x headroom on the fast hosts.
That margin is generous for fast hosts but unproven for slow ones.

**Status: deferred carry-forward**, not queued. Natural fold-in
when Release team spins up the CI matrix work.

### Sub-obs #3: `derive.py` perf patches as merge-invariant

The 3 vectorization patches and the 3 perf tests must travel
together. The perf tests assert `median < 5.0 s`; without the
patches, median is 9.85 s and the gate fails. This is intentional
(the perf test is the regression-pin), but worth documenting:
**any future revert of one of the 3 patches without also
reverting/relaxing the perf test will re-fail the perf gate**.
This is the desired invariant.

### Sub-obs #4: Optional `decisions/` entry for Open Q #11 deferral

Manual Test asked whether PM wants a dated `decisions/` entry
recording the "Open Q #11 → post-MVP deferral" disposition. PM call:
**NOT queued**. The strategy doc addendum (`localization-strategy.md`
§Open Items #3) is permanent and dated within its narrative (`Outcome
2026-06-01 (NFR-LOC-002 perf slice)`). The history entry you're
reading also date-anchors. A decisions entry would be redundant —
no binding directive is being established, only an empirical
disposition recorded.

## Process notes

### Brief's Branch-point pre-design paid off

The brief §5.5 anticipated 3 outcomes (A/B/C) with concrete
disposition for each. Localization team's measurement hit Branch C
(9.85 s); the brief had already authorized "vectorization
improvements" as a Branch C alternative to sparse representation.
The team didn't need a second PM ping — they had the authorization
to vectorize in the original brief. This kept the slice on schedule.

**Lesson for future perf NFR briefs**: pre-define branches based on
measurement outcome. The Localization team consumed ~3 hours of
debugging in cProfile-land before the patches landed; if Branch C
had not been pre-authorized, that would have been a CEO ping +
context-swap + dispatch delay.

### Algorithmic-equivalence pin lived in existing fixture

The `localization-branch` fixture (`divide`, lines 31-34) already
exists for the Phase 4 §4 #1 DoD bullet. Manual Test reused it to
gate algorithmic equivalence post-patch (16/16 fields byte-identical).
**No new fixture needed.** This is the value of investing in good
fixture coverage early — perf slices get free regression-pinning.

### 3-host cross-verification narrative

Team (1.328 s) → Main Branch (1.297 s) → Manual Test (1.281 s).
All three measured on fast Intel laptops. The stdev within each run
(~50 ms) exceeds the mean drift between hosts (~50 ms). Same regime
confirmed three times. This is the most robust empirical
confirmation pattern Nove Test has shipped to date.

### One sharper Branch C recovery than ever before

Pre-patch measurement → cProfile → 3 surgical patches → post-patch
re-measurement: total cycle within one team-dispatch window. The
team did not need to escalate or open a question. The brief's
explicit cProfile expectation under §5.5 Branch C ("identify the
top frames") guided the team to the right tool. **This is what
"self-contained brief" looks like when measurement surprises.**

## What the next cycle is

Phase 4 → 100% complete. Open options for the next dispatch:

1. **Phase 5 entry** — Replay engine + SQLite derived index. Natural
   next major milestone. Requires PM to scope Phase 5 brief.
2. **Phase 3 JUnit adapter** — gated on Open Q #5 (vendor vs
   download Console Launcher). Needs CEO call first.
3. **Phase 3 .NET adapter** — gated on Open Q #4 (Coverlet
   `PerTestCoverage` config key). Needs CEO call first.
4. **Phase 6 polish slices** — MCP transport, release tooling, peak-
   RSS smoke assertion (sub-obs #1), slow-CI host sampling (sub-obs
   #2), Defect 7 (`failure_proximity` warning loop), Regression
   `fixed_tests` clarification.

**PM recommendation**: Phase 5 entry is the cleanest progression
roadmap-wise; it's the largest remaining structural piece. Phase 3
JUnit/.NET requires CEO Open Q answers before being scopeable.
Phase 6 polish is small-slice work that can backfill between
larger milestones.

## Other deferred items (visible to future PM)

1. **Phase 3 JUnit** — gated on Open Q #5
2. **Phase 3 .NET** — gated on Open Q #4
3. **Defect 7** (`failure_proximity` warning loop) — low priority
4. **Regression engine `fixed_tests` clarification** — Regression
   team triage
5. **UX normalizations** (metadata shape + path absoluteness) —
   pre-MVP polish optional
6. **Memory `delete` polish** — long-standing carry-forward
7. **Envelope freeze v2 amendment** for `failure_proximity`
   deviation — low priority
8. **Peak-RSS smoke assertion** for perf benchmark — sub-obs #1
   carry-forward
9. **Slow-CI host sampling** for NFR-LOC-002 — sub-obs #2
   carry-forward
