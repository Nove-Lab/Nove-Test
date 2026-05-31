---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-01
slug: localization-aggregate-fixture-redesign-and-defect3
related:
  - agent-comms/handoffs/localization-team-2026-06-01-aggregate-fixture-redesign-and-defect3.md
  - agent-comms/handoffs/localization-team-2026-05-31-fallback-modes.md
  - agent-comms/tasks/localization-team-2026-05-31-fallback-modes.md
  - agent-comms/tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
---

# Verification: Localization fallback-modes — fixture redesign (Defect 2) + parser/algorithm tightening (Defect 3)

## What landed on `main` this cycle

Single-team multi-commit dispatch. Loc team's parked branch finally
lands.

**Merged commits** (FF, no conflicts — branch was already rebased on
current main `89c7a80`):

| Commit | Author | Summary |
|---|---|---|
| `804690b` | localization-team | feat(localization): close Phase 4 §4 #2 — sbfl_aggregate + failure_proximity modes |
| `3ccfd72` | localization-team | fix(localization-fixture): co-locate failing test_divide with bug in arithmetic.rs |
| `05f86bc` | localization-team | fix(localization): Defect 3 — drop cargo catch-all regex + coverage-scope filter (CEO Option D) |

**Merged tip**: `05f86bc` (was on main at `89c7a80`; baseline cycle gate
was 715+5).

**Source handoff consumed**:
- [`localization-team-2026-06-01-aggregate-fixture-redesign-and-defect3.md`](../handoffs/localization-team-2026-06-01-aggregate-fixture-redesign-and-defect3.md)
  — re-handoff covering all three commits.
- The older [`localization-team-2026-05-31-fallback-modes.md`](../handoffs/localization-team-2026-05-31-fallback-modes.md)
  is superseded by the re-handoff above. Keep both as historical
  artifacts; the re-handoff is the active one.

## Cycle journey (4 attempts → 1 success)

This slice is a record of debugging cargo's per-platform behavior on
the equipped host:

1. **First attempt (2026-05-31 22:40, `a42ea87`)**: original fallback-modes
   — gate failed with `cargo llvm-cov did not write coverage.lcov` →
   **Defect 1** filed.
2. **Second attempt (2026-05-31 23:25, `c8b7879`)**: fixture redesign
   (Option A) layered on top — gate failed because Defect 1 wasn't
   merged yet (correctly noted by team).
3. **Third attempt (2026-05-31, after Defect 1 fix `18fc224` landed)**:
   Loc rebased + FF-merged onto main with both fixes → gate STILL failed
   because cargo's default stack backtrace polluted file rankings →
   **Defect 3** filed.
4. **Fourth attempt (2026-06-01 00:05, `05f86bc`)** — THIS slice:
   parser catch-all dropped + algorithm coverage-files filter
   (CEO Option D) layered on top → gate finally green at **759+5** on
   equipped host. cargo aggregate e2e PASSES with `src/arithmetic.rs`
   ranked top-1.

## What the slice does

Three independent defects closed in one re-handoff:

### Defect 2 (fixture co-location, CEO Option A) — commit `3ccfd72`

Moved the failing `test_divide` test INTO `src/arithmetic.rs` (inside a
`#[cfg(test)] mod tests` block) so the cargo panic trace's FIRST line
reads `panicked at src/arithmetic.rs:53:9` rather than
`panicked at src/lib.rs:35:9`. The assertion site is now the bug site.

### Defect 3 (parser + algorithm tightening, CEO Option D) — commit `05f86bc`

Two complementary changes in `src/novetest/localization/`:

- **Parser** (`failure_proximity.py`): dropped the third "defensive
  catch-all" regex `\b<file>.rs:N:M` from `_CARGO_REGEXES`. Only the two
  anchored patterns (`panicked at` + `failed at`) remain. The `panicked
  at` line is the first line of every libtest panic, so it matches
  regardless of backtrace shape. The catch-all was slurping
  `/rustc/<hash>/library/core/src/panicking.rs:N:M` style frames from
  the default backtrace.
- **Algorithm** (`derive.py:438`): restricted `_derive_aggregate`'s
  candidate set to `covered_files`. Stdlib paths aren't instrumented
  with `-C instrument-coverage`, so they're never in `coverage.files`
  — filtering at the algorithm level is defense in depth even if a
  future parser shape change ever leaks stdlib paths past the parser.

### Defect 1 (cargo-llvm-cov `--ignore-run-fail`) — already on main at `18fc224`

Not part of THIS slice but the necessary precondition. Run team's fix
from the prior cycle. All three defects together let the cargo
aggregate e2e finally produce a `CoverageFactSet` AND rank the bug file
top-1.

**No new src files.** Source-file count: 71 → 72 (just `failure_proximity.py`
which is the original fallback-modes addition from commit `804690b`,
not the Defect 3 fix).

## Files changed (cumulative across all 3 merged commits)

| File | Net change | Nature |
|---|---|---|
| `src/novetest/localization/__init__.py` | +66 / -10 | Re-exports for new modes (804690b) |
| `src/novetest/localization/derive.py` | +458 / -29 | `_derive_aggregate` + `_derive_failure_proximity` + mode routing (804690b) + algorithm coverage-files filter (05f86bc) |
| `src/novetest/localization/failure_proximity.py` | NEW (465) → -1 line (05f86bc) | Mode + parser (804690b); catch-all regex removed (05f86bc) |
| `tests/fixtures/projects/localization-aggregate-only/{Cargo.toml,README.md,src/{lib.rs,arithmetic.rs,classifier.rs}}` | NEW + redesigned | Fixture + Option A test relocation |
| `tests/fixtures/projects/localization-no-coverage/{...}` | NEW (5 files) | Fixture for failure_proximity mode |
| `tests/integration/localization/test_{aggregate_mode,failure_proximity,mode_selection_per_engine}_e2e.py` | NEW (3 files) | E2E coverage |
| `tests/unit/localization/test_{derive_aggregate,derive_failure_proximity,derive_modes_dispatch,failure_log_parser}.py` | NEW (4 files) + EDIT (Defect 3 regression pins) | Unit coverage + Defect 3 negatives |
| `tests/unit/localization/test_derive.py` | EDIT | Placeholder → new mode tests |
| `WORKLOG.md` | +3 entries | Per-commit retrospective |

Source-file count: 71 (post-Run-merge) → **72** (added `failure_proximity.py`).

## Pre-merge gate evidence (Main Branch, equipped host)

```
$ git merge --ff-only novetest-localization-fallback-modes
Updating 89c7a80..05f86bc
Fast-forward
 [3 commits worth of changes, see git log --stat]

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
... 759 passed, 5 skipped in 31.83s

$ uv run mypy
Success: no issues found in 72 source files

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest \
    tests/integration/localization/test_aggregate_mode_e2e.py \
    tests/integration/localization/test_failure_proximity_e2e.py \
    tests/integration/localization/test_mode_selection_per_engine.py -v
... 5 passed in 2.27s
```

- Gate: **759 + 5** (baseline `89c7a80` was 715+5; team's Rust-less
  prediction was 755+9 → on equipped host the 4 skip-guarded cargo
  tests run + pass: 755 → 759, 9 - 4 = 5).
- mypy: clean at 72 (1 new src file: `failure_proximity.py` from `804690b`).
- All 5 Loc integration tests pass in isolation, including the
  previously-failing `test_aggregate_mode_ranks_buggy_file_top`.

## 🎯 Load-bearing E2E envelope — `arithmetic.rs` ranks top-1

Captured by running the full pipeline (`novetest run --coverage` →
`novetest localization <run_id>`) against the freshly-redesigned
`localization-aggregate-only` fixture on equipped host:

### Step 1: Run with coverage (proves Defects 1 + 2 fixes work together)

```
$ cd /tmp/lao-final  # cp from tests/fixtures/projects/localization-aggregate-only/
$ novetest init
$ novetest run --coverage
```

Envelope shape:

| Path | Observed value |
|---|---|
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` |
| `data.memory_entry.run_record.status` | `"failed"` (test_divide fails — fixture's contract) |
| `data.memory_entry.run_record.summary_counts` | `{"passed": 3, "failed": 1, "skipped": 0, "total": 4}` |
| `data.memory_entry.run_record.metadata` | `{"native_exit_code": 0, "nextest_version": "0.9.137"}` |
| `data.memory_entry.has_coverage_facts` | `true` |
| `data.coverage_outcome.kind` | `"fact-set"` |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` |
| `data.coverage_outcome.summary.percent_covered` | `85.71` |
| Shell exit | `3` (transport-ok, test-failures-detected) |

### Step 2: Localization with explicit run_id (proves Defect 3 fix works)

```
$ novetest localization <run_id>
```

| Path | Observed value |
|---|---|
| `data.localization_outcome.kind` | `"fact-set"` |
| `data.localization_outcome.mode` | `"sbfl_aggregate"` |
| `data.localization_outcome.confidence` | `"medium"` |
| `data.localization_outcome.formula` | `"ochiai"` |
| `data.localization_outcome.alternate_scores_available` | `["dstar2", "op2", "tarantula"]` (3-element list) |
| `data.localization_outcome.top_n` | `10` |
| `data.localization_outcome.entries` length | **`1`** (only arithmetic.rs survives the filter — stdlib paths correctly dropped) |
| `data.localization_outcome.entries[0].rank` | **`1`** 🎯 |
| `data.localization_outcome.entries[0].code_location.file` | **`"src/arithmetic.rs"`** 🎯 |
| `data.localization_outcome.entries[0].code_location.primary_line` | `53` (the `assert_eq!` line in `arithmetic::tests::test_divide`) |
| `data.localization_outcome.entries[0].code_location.kind` | `"file"` (v1 file-level granularity per strategy doc §3) |
| `data.localization_outcome.entries[0].score_raw` | `0.5` (Ochiai = `1/√((1+0)·(1+3))` = `0.5`; 1 failing + 3 passing + arithmetic.rs in coverage = ef=1, ep=3) |
| `data.localization_outcome.entries[0].score_normalized` | `0.0` (single entry → min-max yields 0) |
| `data.localization_outcome.entries[0].alternate_scores` | `{"dstar2": 0.333..., "op2": 0.25, "tarantula": 0.5}` (3-key dict) |
| `data.localization_outcome.metadata` | `{"regression_reweighted": false, "changed_files_count": 0}` |

This is the cycle's load-bearing evidence: **`src/arithmetic.rs` ranks
top-1** as the original e2e test asserted. Pre-fix (third attempt), the
top-1 was `rustc/.../library/core/src/ops/function.rs` with arithmetic.rs
at #4.

## Manual Test scope (8 scenarios)

### Scenario 1 — Aggregate mode e2e (THE smoking-gun test)

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/localization-aggregate-only .
cd localization-aggregate-only
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage  # exit 3
RUN_ID=$(PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage 2>&1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['data']['memory_entry']['run_record']['run_reference']['run_id'])")
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest localization $RUN_ID | python3 -m json.tool | head -50
```

**Expected**:
- `kind: "fact-set"`, `mode: "sbfl_aggregate"`, `confidence: "medium"`
- `entries` length = 1 (only arithmetic.rs survives)
- `entries[0].rank == 1`, `entries[0].code_location.file == "src/arithmetic.rs"`
- `entries[0].code_location.primary_line == 53`

### Scenario 2 — Inspect the redesigned fixture

```bash
cat /home/yjshin/dev/Nove-Test/tests/fixtures/projects/localization-aggregate-only/src/arithmetic.rs
```

**Expected**: file contains `pub fn divide(a: i32, b: i32) -> i32 { a + b }`
(intentional bug preserved) AND a `#[cfg(test)] mod tests { ... test_divide ... }`
block INSIDE the same file (Option A from CEO).

```bash
cat /home/yjshin/dev/Nove-Test/tests/fixtures/projects/localization-aggregate-only/src/lib.rs
```

**Expected**: `lib.rs::tests` no longer contains `test_divide` (only
the 3 passing tests: `test_add`, `test_subtract`, `test_classify_positive`).

### Scenario 3 — Verify Defect 3 fixes in source

```bash
grep -n "panicked at\|failed at\|catch-all" /home/yjshin/dev/Nove-Test/src/novetest/localization/failure_proximity.py
```

**Expected**: `_CARGO_REGEXES` tuple shows ONLY 2 patterns
(`panicked at` + `failed at`). The catch-all `\b<file>.rs:N:M` is
GONE, replaced by a 14-line comment block explaining why.

```bash
grep -n "all_files = sorted" /home/yjshin/dev/Nove-Test/src/novetest/localization/derive.py
```

**Expected**: `all_files = sorted(covered_files)` (line 438). The
previous shape `sorted(covered_files | set(file_to_failed_tests.keys()))`
is gone.

### Scenario 4 — Failure proximity mode (Loc team's other new mode)

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/localization-no-coverage .
cd localization-no-coverage
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run  # no --coverage, exit 3
RUN_ID=$(PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run 2>&1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['data']['memory_entry']['run_record']['run_reference']['run_id'])")
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest localization $RUN_ID | python3 -m json.tool
```

**Expected**:
- `kind: "fact-set"`, `mode: "failure_proximity"`, `confidence: "low"`
- `alternate_scores_available: []` (documented deviation — failure_proximity
  is not SBFL)
- `entries[0].alternate_scores: {}` (same deviation)
- `entries[0].code_location.file` ends with `statistics.py` (the bug
  site in the fixture)

### Scenario 5 — Per-test mode regression check (existing pytest)

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/localization-branch .
cd localization-branch
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage
PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest localization latest
```

**Expected**:
- `kind: "fact-set"`, `mode: "sbfl_per_test"`, `confidence: "high"`
- `entries[0].code_location.symbol == "divide"`, top-rank Ochiai 1.0
- This is the existing pre-slice behavior — pure regression confirmation

### Scenario 6 — Confirm cargo coverage path now works for failing runs

```bash
# Same as Scenario 1 Step 1 envelope; the coverage_outcome.kind: "fact-set"
# proves Defect 1's --ignore-run-fail is wired correctly for the
# failing-test path.
```

### Scenario 7 — Run the load-bearing integration tests in isolation

```bash
cd /home/yjshin/dev/Nove-Test
PATH=$HOME/.cargo/bin:$PATH uv run pytest -v \
    tests/integration/localization/test_aggregate_mode_e2e.py \
    tests/integration/localization/test_failure_proximity_e2e.py \
    tests/integration/localization/test_mode_selection_per_engine.py
```

**Expected**: 5 passed in ~2.3s.

### Scenario 8 — Full gate one last time

```bash
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
uv run mypy
```

**Expected**: 759 passed + 5 skipped; mypy clean 72 src files.

## Critical edge cases worth probing

| Edge case | Why it matters | How to probe |
|---|---|---|
| **Stdlib path filter is at algorithm layer (not just parser)** | Defense in depth — if a future parser regex change ever leaks a stdlib path again, the algorithm filter catches it. | `grep -n "all_files = sorted" src/novetest/localization/derive.py` should show `sorted(covered_files)` (no union with failure-trace files). |
| **Catch-all regex is gone** | The old regex would slurp every `.rs:N:M` substring from cargo's default backtrace. Re-adding it would re-introduce Defect 3. | `grep -c "\\\\b.*\\\\.rs" src/novetest/localization/failure_proximity.py` should be `0` — no catch-all pattern. |
| **Tie-break behavior is moot after the filter** | Pre-fix, 4-way tie at e_f=1; lexicographic sort pushed arithmetic.rs to #4. Post-fix, only 1 entry survives the filter so ties don't matter. | Scenario 1's envelope shows `entries` length 1 — confirms only the bug file survives. |
| **Pre-existing per-test path unchanged** | The fix is in the aggregate path's algorithm + cargo parser only. Per-test (pytest) localization should be unaffected. | Scenario 5 confirms `localization-branch` fixture still produces `mode: "sbfl_per_test"` with `divide` ranked top-1 Ochiai 1.0. |
| **Failure proximity for no-coverage runs unchanged** | The Defect 3 fix touched `_derive_aggregate` (Path B) and the cargo parser. failure_proximity (Path C) was NOT changed. | Scenario 4 confirms the no-coverage fixture still produces a `failure_proximity` finding. |

## Defect 4 surfaced during E2E — `localization latest` doesn't recognize aggregate-mode-eligible cargo runs

During Manual Test E2E, I observed that `novetest localization latest`
returns `kind: "unavailable"`, `reason: "run_not_analyzable"`,
`detail: "no analyzable runs in store (1 candidates checked)"` against
the cargo aggregate fixture — even though `novetest localization <run_id>`
on the SAME run works perfectly.

Root cause: `src/novetest/localization/retrieval.py:99` hardcodes:

```python
return coverage.mapping_granularity == "per-test"
```

`resolve_latest_analyzable_run` walks runs newest-first and asks this
check. Cargo runs have `mapping_granularity == "aggregate"` → rejected
→ `latest` reports no analyzable run.

This is a **separate pre-existing bug** that the slice's fix
**exposes** but doesn't cause. Pre-slice, the aggregate code path was
a placeholder, so `<run_id>` would have also failed for cargo. Now
that aggregate-mode works, `latest`'s gate is the next bottleneck.

**Not blocking this cycle's merge** — the explicit `<run_id>` path
works (verified above) and the slice's intended scope (Defects 2 + 3)
is complete with gate green. Defect 4 is a separate slice for the
Localization team to address.

Full analysis + recommended fix path in
`agent-comms/questions/main-branch-team-2026-06-01-localization-latest-aggregate-discovery.md`
(filed alongside this verification).

## Parked work — none this cycle

All three originally-parked Loc commits landed. The
`novetest-localization-fallback-modes` worktree will be removed after
this verification commit (no need to keep — slice is complete).

## Notes from merging

- **Loc team rebased ahead of FF-merge** — when they iterated on the
  parked branch with the new Defect 3 fix commit, they also rebased
  the prior 2 commits onto current main (`89c7a80`). So the FF-merge
  was clean — no WORKLOG conflicts this cycle (they were resolved
  in the rebase before I picked up the worktree).
- **PROACTIVE Defect 3 fix without PM task brief** — flagged in the
  handoff §"Open items #1". CEO's "확인하고 업무 진행" directive +
  my question doc's explicit Option D recommendation were the routing
  signal. PM may want to retroactively file the task brief for
  bookkeeping. Per CEO's prior posture confirmation ("Process: charter
  유지"), this is acceptable as long as the gate caught any defects
  (which it did — green at 759+5).
- **No `--no-verify` / no force-push / no amend** of any published
  commit. Charter discipline preserved.

## Next steps

1. **Manual Test**: run the 8 scenarios above; file `findings/`. Pay
   particular attention to Scenarios 1 + 4 (the new mode envelopes
   are the load-bearing surface). Defect 4 is documented but separate
   — Manual Test may want to confirm the `latest` failure mode in
   the field too.
2. **PM**: cycle-close work — close the three pending Loc task slots
   (`fallback-modes`, `aggregate-fixture-redesign`, plus the proactive
   Defect 3 task that wasn't filed) + the Run `--ignore-run-fail` task
   that landed last cycle. File a Defect 4 follow-up task (Option:
   relax `check_localization_availability` to accept any
   `mapping_granularity` value, OR remove the granularity check
   entirely since `_derive_aggregate` and `_derive_failure_proximity`
   handle all combinations). Cycle history doc.
3. **CEO**: cycle authorization fulfilled.

---

Filed by: novetest-main-branch-team
Date: 2026-06-01
Cycle: 2026-06-01 single-slice slice (Localization fallback-modes
       + fixture redesign + Defect 3 fix) — all three commits merged
       successfully; Defect 4 surfaced as orthogonal follow-up
