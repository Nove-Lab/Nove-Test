---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: open
created: 2026-05-31
slug: localization-aggregate-e2e-defect3-parser-stdlib-pollution
related:
  - agent-comms/handoffs/localization-team-2026-05-31-fallback-modes.md
  - agent-comms/tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - src/novetest/localization/failure_proximity.py
  - tests/integration/localization/test_aggregate_mode_e2e.py
---

# Question: Localization aggregate-e2e — Defect 3 (parser regex catch-all pulls in rustc stdlib paths from cargo's default backtrace)

## TL;DR

Defects 1 + 2 are both surgically fixed and the cargo aggregate e2e
now gets all the way to its final `endswith("arithmetic.rs")`
assertion. But that assertion STILL fails — `src/arithmetic.rs` ranks
**#4**, not #1. The top three entries are all Rust stdlib paths:

```
expected top entry to be src/arithmetic.rs (the seeded bug);
got 'rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/ops/function.rs';
entries=[
  'rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/ops/function.rs',
  'rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/panicking.rs',
  'rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/std/src/panicking.rs',
  'src/arithmetic.rs',
]
```

All four files have `e_f = 1`. They tie. Tie-breaking sorts by file
path ascending → `rustc/...` sorts before `src/...` lexicographically
→ `arithmetic.rs` falls to #4.

Root cause is in the Localization parser, NOT the adapter or the
fixture. Per charter, I rolled back the Loc merge (kept Run's
`--ignore-run-fail` at `18fc224`) and escalate here.

## Both prior defects DID get fixed by this cycle's two slices

**Defect 1 fix (`--ignore-run-fail` Run team swap, `18fc224`)**:
empirically working. `cargo llvm-cov nextest` now writes the LCOV
file even when nextest exits non-zero. CoverageFactSet is built;
the e2e's `isinstance(fact_set, CoverageFactSet)` pre-condition holds.

**Defect 2 fix (Option A fixture redesign, Loc team `320c4ae`)**:
empirically working. The panic trace's FIRST line now reads:

```
thread 'arithmetic::tests::test_divide' (27482) panicked at src/arithmetic.rs:53:9:
```

NOT `src/lib.rs:35:9` (the pre-redesign state). So `arithmetic.rs`
DOES get extracted by the `panicked at` regex and DOES get
`e_f["src/arithmetic.rs"] = 1`. That part of the fix works as
designed.

Both fixes are in good shape; this is a third independent defect
the team's pre-flight didn't catch (because they developed on
Rust-less and the e2e was skip-guarded there).

## Defect 3 — parser regex catch-all pollutes the file set

### Root cause

`src/novetest/localization/failure_proximity.py` (line 116-121, on
the parked `c8b7879` Loc worktree tip):

```python
_CARGO_REGEXES = (
    # Standard libtest panic: ``thread '...' panicked at <path>:<line>:<col>``.
    re.compile(rf"panicked at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # ``assertion `...` failed at <path>:<line>:<col>`` — newer rustc forms.
    re.compile(rf"failed at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # Catch-all (the load-bearing problem here):
    re.compile(rf"\b({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
)
```

The catch-all regex matches **any** `<path>.rs:<line>:<col>` substring
in the failure log. It was probably added as a defensive net for
"newer rustc forms" the first two regexes miss. But cargo nextest
emits a **full stack backtrace by default** (without needing
`RUST_BACKTRACE=1`), and the catch-all regex slurps every frame's
path — including stdlib paths.

### What the persisted failure log looks like

Captured from a real `novetest run --coverage` against the redesigned
`localization-aggregate-only` fixture, on equipped host, with both
Defect 1 and Defect 2 fixes applied:

```
$ cat .novetest/run/artifacts/run_<RID>/native/failures/<safe_name>.log
thread 'arithmetic::tests::test_divide' (27482) panicked at src/arithmetic.rs:53:9:
assertion `left == right` failed
  left: 12
 right: 5
stack backtrace:
   0: __rustc::rust_begin_unwind
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/std/src/panicking.rs:689:5
   1: core::panicking::panic_fmt
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/panicking.rs:80:14
   2: core::panicking::assert_failed_inner
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/panicking.rs:439:17
   3: core::panicking::assert_failed::<i32, i32>
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/panicking.rs:394:5
   4: localization_aggregate_only::arithmetic::tests::test_divide
             at ./src/arithmetic.rs:53:9
   5: localization_aggregate_only::arithmetic::tests::test_divide::{closure#0}
             at ./src/arithmetic.rs:52:21
   6: <localization_aggregate_only::arithmetic::tests::test_divide::{closure#0} as core::ops::function::FnOnce<()>>::call_once
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/ops/function.rs:250:5
   7: <fn() -> core::result::Result<(), alloc::string::String> as core::ops::function::FnOnce<()>>::call_once
             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/ops/function.rs:250:5
note: Some details are omitted, run with `RUST_BACKTRACE=full` for a verbose backtrace.
```

The first `panicked at` regex captures only line 1 →
`("src/arithmetic.rs", 53)`. The catch-all regex captures every
`at <path>.rs:N:M` line, including:
- `rustc/.../std/src/panicking.rs:689` (line 0)
- `rustc/.../core/src/panicking.rs:80` (line 1) — distinct from line 0
- `rustc/.../core/src/panicking.rs:439` (line 2) — dedupe with above
- `rustc/.../core/src/panicking.rs:394` (line 3) — dedupe
- `./src/arithmetic.rs:53` (line 4) — dedupe with first regex's hit
- `./src/arithmetic.rs:52` (line 5)
- `rustc/.../core/src/ops/function.rs:250` (lines 6, 7) — same path

Net: 4 distinct files get `e_f = 1`:
1. `src/arithmetic.rs` — the real bug location ✓
2. `rustc/.../core/src/ops/function.rs` — Rust stdlib FnOnce
3. `rustc/.../core/src/panicking.rs` — Rust stdlib panic infra
4. `rustc/.../std/src/panicking.rs` — Rust stdlib panic infra

All four tie at score=1.0 (Ochiai). Lexicographic tie-break (`-c[1][formula], c[0]`
in `_derive_aggregate` line 477) sorts file path ASCENDING for ties →
`rustc/...` (`r`) comes BEFORE `src/...` (`s`) → `arithmetic.rs` is #4.

### Algorithm side does the right thing (no fix needed there)

`_derive_aggregate` correctly:
- Lifts `e_f` for each file the parser returns.
- Computes Ochiai (etc) per file.
- Filters out files with score=0.
- Sorts by score desc, then by file path asc for ties.

The bug is purely upstream — the parser hands `_derive_aggregate` a
file set that includes stdlib paths. The algorithm faithfully ranks
what it's given.

## Suggested fix paths (Localization team — choose ONE)

### Option A — drop the catch-all regex

Remove the third regex `\b(...)\.rs:(\d+):\d+` from the cargo regex
tuple. Rely only on the two anchored patterns (`panicked at` and
`failed at`). With this change, the parser would extract only
`("src/arithmetic.rs", 53)` from the example log → `e_f["src/arithmetic.rs"]=1`,
every other file at e_f=0, only arithmetic.rs survives Step 5's
score-zero filter → arithmetic.rs ranks #1.

Risk: the catch-all was probably added to handle "newer rustc forms"
where the panic prefix is different. The handoff §"Failure log parser
per-engine status" table only lists 3 cargo unit tests; dropping the
catch-all could break one of them. Need to re-run the parser unit
suite to confirm.

### Option B — filter parser output to drop external/stdlib paths

Keep all three regexes. Post-process the extracted tuples: drop any
file whose path starts with `/rustc/`, `rustc/`, `~/.cargo/registry/`,
`cargo/registry/`, or other known-external prefixes. Or whitelist:
only keep paths starting with `src/` or `./src/` or `../src/`.

Risk: false-positive whitelist may drop legitimate workspace-relative
paths from monorepos / nested crates. Need a thoughtful prefix list.

### Option C — algorithm-level filter (only consider files in coverage)

In `_derive_aggregate` line 421, change:
```python
all_files = sorted(covered_files | set(file_to_failed_tests.keys()))
```
to:
```python
all_files = sorted(covered_files | (set(file_to_failed_tests.keys()) & covered_files))
# OR simply:
all_files = sorted(covered_files)
```

So `e_f` only counts for files that ARE in the project's coverage.
Stdlib files aren't compiled with `-C instrument-coverage`, so they're
never in `coverage.files`. Filtering at the algorithm level drops
them naturally.

Risk: if a bug is in a workspace file that wasn't covered by any
test (zero coverage), this filter would drop it too. But files with
zero coverage typically don't appear in failing tests' panic traces
either (they weren't executed), so the practical impact is bounded.

### Option D — combine A + C (defense in depth)

Drop the catch-all regex (A) AND restrict to coverage files (C).
Maximum noise rejection; minimal risk of dropping legitimate signals.

## Why this wasn't caught earlier

The slice's original handoff §"Failure log parser per-engine status":

> "cargo-test | `panicked at` + `failed at` + catch-all `\.rs:` |
>  ✓ (3 cases) | SKIP-GUARDED (real cargo path runs on equipped
>  host; on dev box → skipped)"

The team unit-tested the catch-all with hand-crafted inputs but never
exercised it against a real cargo nextest backtrace. The full
backtrace + stdlib pollution is a real-cargo-only phenomenon.

The Defect 2 fixture redesign was developed in the same "Rust-less"
environment, so the team couldn't observe Defect 3 even after their
fix — they correctly noted in the WORKLOG entry:

> "Equipped-host empirical validation ... is pending because (a)
>  this dev box has no cargo toolchain on PATH ... and (b) Defect 1
>  ... is NOT YET MERGED into main."

Both conditions held; the team couldn't validate end-to-end. Defect 3
only surfaces when BOTH fixes are present AND on equipped host —
exactly the configuration Main Branch's gate runs in.

## What Main Branch did

1. **Rebased Run worktree** onto current main (`6b291e8`) → clean
   linear → tip `18fc224`. FF-merged → main updated.
2. **Gate after Run merge**: 715 + 5 passed, mypy 71 src clean.
   Matches Run's handoff prediction.
3. **Rebased Loc worktree** onto new tip (`18fc224`) → two WORKLOG
   conflicts (one per Loc commit) → resolved surgically with
   incoming-on-top convention → tips `f30a141` + `320c4ae`.
4. **FF-merged Loc** → main updated.
5. **Combined gate**: 1 FAILED + 755 passed + 5 skipped. The new
   failure is Defect 3 (this question).
6. **Rolled back Loc** → main back to `18fc224` (Run-only).
7. **Re-verified gate post-rollback**: 715 + 5 passed, mypy 71 src
   clean. Stable Run-only state.
8. **Captured Defect 3 evidence** (this doc).

## Recommended path forward

1. **Main Branch pushes Run-only this cycle** (`061e741..18fc224` =
   1 src commit + 1 verification commit + 1 question commit = 3
   pushed commits). Run's `--ignore-run-fail` unblocks any cargo
   user's `novetest run --coverage` against a failing workspace —
   independent value.
2. **PM dispatches a Loc team follow-up slice** implementing one of
   Options A/B/C/D above. **Recommended: Option D** (drop catch-all
   + algorithm-level coverage filter). Both are surgical: one regex
   removal + one line change in `_derive_aggregate`.
3. **Loc team re-rebases** their `novetest-localization-fallback-modes`
   worktree (currently at rebased tips `f30a141` + `320c4ae`) onto
   the next main, adds the Option D commit, and re-tests on equipped
   host.
4. **Optional cycle improvement**: require Run-eligible slices to
   include "verified on equipped host" in the handoff's pre-flight
   evidence, OR add a CI matrix entry that runs the integration
   suite on a Rust-toolchain-equipped image. This is the third
   parked Loc slice in two cycles for equipped-host-only defects.

## Status of the Loc worktree

The Loc team's worktree at
`/home/yjshin/dev/novetest-localization-fallback-modes` is preserved
at the **rebased tips** `f30a141` (fallback-modes) + `320c4ae`
(fixture-redesign). The team's next iteration:
- builds on top of `320c4ae` with the parser/algorithm fix
- OR resets `320c4ae` and reworks the fixture redesign approach if
  Option D's algorithm filter makes the fixture redesign unnecessary

Either path is reasonable; Option D would technically work even
WITHOUT the fixture redesign (the algorithm-level coverage filter
would drop `lib.rs` since its `e_f` would be 0 vs `arithmetic.rs`
under the un-redesigned fixture would also be 0 — wait, that doesn't
work without the redesign). On reflection, Option D needs the
fixture redesign to be useful for THIS fixture — keep both.

---

Filed by: novetest-main-branch-team
Date: 2026-05-31
