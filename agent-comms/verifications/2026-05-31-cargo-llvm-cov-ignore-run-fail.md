---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-31
slug: cargo-llvm-cov-ignore-run-fail
related:
  - agent-comms/handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/tasks/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
---

# Verification: cargo adapter — `--no-fail-fast` → `--ignore-run-fail` (Defect 1 fix)

## What landed on `main` this cycle

Single-slice cycle (parallel sibling — Localization aggregate
fixture redesign — was kicked back AGAIN; see "Parked work" below).

**Merged commit** (FF after rebase, no source conflicts):

| Commit | Author | Summary |
|---|---|---|
| `18fc224` | run-team | fix(run): swap --no-fail-fast for --ignore-run-fail on cargo-llvm-cov path |

**Merged tip**: `18fc224` (was on main at `6b291e8`; baseline cycle
gate was 714+5).

**Source handoff consumed**:
- [`run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`](../handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md)
  — single-handoff slice; status `ready-to-merge`.

## What the slice does

Surgical fix to the cargo adapter's coverage-collection argv. Closes
**Defect 1** from Main Branch's 2026-05-31 equipped-host gate
failure question (`questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`).

Pre-fix: `cargo llvm-cov nextest --no-fail-fast` REFUSES to emit the
LCOV report when the inner cargo-nextest exits non-zero (any failing
test). So `novetest run --coverage` against any cargo workspace with
a failing test → adapter raises `unparseable-output` ("cargo llvm-cov
did not write coverage.lcov").

Post-fix: `cargo llvm-cov nextest --ignore-run-fail` runs every test
AND commits to writing the report regardless of test outcomes. The
two flags are mutually exclusive on cargo-llvm-cov's CLI;
`--ignore-run-fail` internally implies `--no-fail-fast` (confirmed by
empirical stderr trace).

**Critical constraint preserved**: the non-coverage path
(`cargo nextest run` invoked directly, without the cargo-llvm-cov
wrapper) STILL uses `--no-fail-fast`. `--ignore-run-fail` is a
cargo-llvm-cov-specific flag; passing it to plain cargo-nextest would
error.

**No DoD bullet implications.** This is a bug fix to a landed
adapter, not a phase-gated feature.

## Files changed (single commit)

| File | Net change | Nature |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +25 / −2 | 1-line flag swap in the `if collect_coverage:` branch + 19-line docstring block above the coverage argv list explaining the swap rationale + small docstring extension on the non-coverage `else:` branch noting why it stays `--no-fail-fast`. |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +100 / −1 | Updated existing happy-path coverage test's `--no-fail-fast` assertion → `--ignore-run-fail` (mandatory; old assertion would fail post-fix); added focused `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail` pinning BOTH invariants (positive + negative) in isolation. |
| `WORKLOG.md` | +8 / −0 | Top entry `2026-05-31 — phase3 / cargo-llvm-cov-ignore-run-fail`. |
| `agent-comms/handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md` | NEW | 239-line slice handoff. |

**Source-file count: 71 → 71** (no new src files).

## Pre-merge gate evidence (Main Branch, equipped host)

```
$ git rebase main  # in run worktree
Successfully rebased and updated refs/heads/worktree-run-team-cargo-llvm-cov-ignore-run-fail.

$ git merge --ff-only worktree-run-team-cargo-llvm-cov-ignore-run-fail
Updating 6b291e8..18fc224
Fast-forward
 WORKLOG.md                                         |   8 +
 ...am-2026-05-31-cargo-llvm-cov-ignore-run-fail.md | 239 +++++++++++++++++++++
 src/novetest/run/adapters/cargo_adapter.py         |  27 ++-
 tests/unit/run/adapters/test_cargo_adapter.py      | 101 ++++++++-
 4 files changed, 372 insertions(+), 3 deletions(-)

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
... 715 passed, 5 skipped in 29.90s

$ uv run mypy
Success: no issues found in 71 source files
```

- Gate: **715 + 5** (baseline `6b291e8` was 714+5 → +1 = the new
  focused flag-swap test, exactly as Run team predicted).
- mypy: clean at 71 (no new src files).

## Empirical proof of fix (load-bearing)

Captured manually on equipped host using the new
`localization-aggregate-only` fixture (lives in the parked Loc
worktree; copied to `/tmp/lao-defect3` for the probe):

### Pre-fix reproduction (`--no-fail-fast`)

```
$ cp -r .../localization-aggregate-only /tmp/lao-probe
$ cd /tmp/lao-probe
$ NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
    --no-fail-fast --workspace --message-format=libtest-json \
    --lcov --output-path coverage.lcov
[3 passed + 1 failed (test_divide)]
error: test run failed
error: process didn't exit successfully: ... (exit status: 100)
$ ls coverage.lcov
ls: cannot access 'coverage.lcov': No such file or directory
```

### Post-fix proof (`--ignore-run-fail`)

```
$ NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
    --ignore-run-fail --workspace --message-format=libtest-json \
    --lcov --output-path coverage.lcov
[3 passed + 1 failed (test_divide)]
warning: process didn't exit successfully: cargo nextest run --no-fail-fast ... (exit status: 100)
    Finished report saved to coverage.lcov
$ ls -l coverage.lcov
-rw-r--r-- 1 yjshin yjshin 1710 May 31 22:50 coverage.lcov
```

The warning trace `cargo nextest run --no-fail-fast` confirms
`--ignore-run-fail` internally implies `--no-fail-fast` (passes it to
the inner cargo-nextest invocation).

## E2E envelope evidence — `novetest run --coverage` against failing-test fixture

Captured by running the merged adapter on the parked Loc fixture
(redesigned to inline `test_divide` inside `arithmetic.rs` per CEO's
Option A, though that fixture redesign isn't on main — it's still
parked because of Defect 3 below):

```
$ cd /tmp/lao-defect3
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH \
    novetest init  # ok: True
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH \
    novetest run --coverage
```

Envelope shape (Manual Test: pinned paths — these are the ACTUAL
paths from the freshly-merged code, copy-paste them verbatim):

| Path | Observed value |
|---|---|
| `ok` (top-level) | `true` |
| `errors` | `[]` |
| `warnings` | `[]` |
| `data.memory_entry.run_record.run_reference.run_id` | `"01KSZ84Z82NPNKRWJPEMF1TD0N"` (ULID; per-invocation) |
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` |
| `data.memory_entry.run_record.status` | `"failed"` (SuT's `test_divide` did fail — by fixture design) |
| `data.memory_entry.run_record.summary_counts` | `{"passed": 3, "failed": 1, "skipped": 0, "total": 4}` |
| `data.memory_entry.run_record.metadata` | `{"native_exit_code": 0, "nextest_version": "0.9.137"}` (prior 3A typed-slot still wired) |
| `data.memory_entry.run_record.artifact_paths` keys | includes `"coverage_lcov"` (1732 bytes on disk) |
| `data.memory_entry.has_coverage_facts` | `true` ← **load-bearing — was `false` pre-fix** |
| `data.coverage_outcome.kind` | `"fact-set"` ← **was `"unavailable"` pre-fix** |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` |
| `data.coverage_outcome.summary.percent_covered` | `~85.7%` (24/28 statements) |

The shell exit code was **3** (transport-ok, test-failures-detected),
NOT exit 4 (adapter-error). Pre-fix would have been exit 4 with
`code: "adapter-unparseable-output"`.

## Manual Test scope (6 scenarios)

The slice's load-bearing assertion is the new unit test plus the
empirical lcov-written proof above. Manual Test's job:

1. **Confirm cargo happy path unchanged** (all-passing fixture).
2. **Confirm new failing-test-with-coverage path works** (the
   pre-fix bug case is now fixed).
3. **Confirm non-coverage cargo path still uses `--no-fail-fast`**
   (regression-pinning).
4. **Inspect the argv-swap test source** to understand the locked
   invariants.

### Scenario 1 — Happy path: `novetest run --coverage` against `cargo-test-basic-coverage`

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic-coverage .
cd cargo-test-basic-coverage
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage
```

**Expected**: exit 0, all 4 tests pass, `coverage_outcome.kind: fact-set`,
~96% covered. The Run polish slice does NOT change the happy path's
behavior — pure regression confirmation.

### Scenario 2 — NEW: failing-test-with-coverage (the slice's value proposition)

The `localization-aggregate-only` fixture lives in the parked Loc
worktree. Copy it to a scratch dir and run:

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/novetest-localization-fallback-modes/tests/fixtures/projects/localization-aggregate-only .
cd localization-aggregate-only
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage
echo "exit=$?"
```

**Expected**: exit 3 (test-failures-detected), `ok: true`, `errors: []`,
`status: failed`, `has_coverage_facts: true`, `coverage_outcome.kind: fact-set`.
This is the EXACT scenario that was broken pre-fix and works now.

Note: this fixture is from the parked Loc worktree — when the Loc
team's slice eventually lands, the fixture will live in main's
`tests/fixtures/projects/`. For now, copy from the worktree.

### Scenario 3 — Confirm non-coverage path unaffected

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic .
cd cargo-test-basic
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run
```

**Expected**: exit 0, `engine_name: cargo-test`, all tests pass,
artifact_paths does NOT include `coverage_lcov` (no `--coverage` flag).
This path uses `cargo nextest run` (not cargo-llvm-cov) and still
passes `--no-fail-fast` — the slice's constraint preservation.

### Scenario 4 — Inspect the new focused unit test

```bash
cd /home/yjshin/dev/Nove-Test
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
  tests/unit/run/adapters/test_cargo_adapter.py::test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail \
  -v
```

**Expected**: 1 passed. The test asserts:
- `"--ignore-run-fail" in captured_argv` (positive — the swap target)
- `"--no-fail-fast" not in captured_argv` (negative — load-bearing
  against a future polish adding back the old flag thinking it's
  complementary; they are mutually exclusive on cargo-llvm-cov's CLI)
- `"llvm-cov" in captured_argv` (paranoia guard against stub-routing
  bugs)

### Scenario 5 — Targeted regression: non-coverage path argv invariant

```bash
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
  tests/unit/run/adapters/test_cargo_adapter.py::test_argv_uses_default_workspace_when_expression_empty \
  tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_adds_flags_and_registers_artifact \
  tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_false_omits_flags_and_artifact \
  -v
```

**Expected**: 3 passed. These pin:
- Non-coverage default workspace argv (still `--no-fail-fast`).
- Coverage argv shape (now `--ignore-run-fail`).
- No-coverage no-llvm-cov path.

### Scenario 6 — Read the docstring rationale

```bash
sed -n '160,220p' src/novetest/run/adapters/cargo_adapter.py
```

**Expected**: 19-line docstring block above the coverage argv list
explaining:
- `--no-fail-fast` surfaces nextest's non-zero exit as cargo-llvm-cov's
  own failure → suppresses LCOV report.
- `--ignore-run-fail` runs every test AND commits to emitting the
  report.
- The two flags are mutually exclusive on cargo-llvm-cov's CLI.
- Cross-references the question doc for empirical proof.
- Pins that plain cargo-nextest does NOT accept `--ignore-run-fail`
  (cargo-llvm-cov-only flag).

## Critical edge cases worth probing

| Edge case | Why it matters | How to probe |
|---|---|---|
| **Both flags simultaneously would error** | A future polish might naively add `--ignore-run-fail` alongside the existing `--no-fail-fast` thinking they're complementary. They're mutually exclusive on cargo-llvm-cov's CLI. | The new unit test's negative assertion (`"--no-fail-fast" not in captured_argv`) is the guard. Removing the swap would fail it. |
| **Asymmetric path constraint** | `--ignore-run-fail` is a cargo-llvm-cov-specific flag. Plain `cargo nextest run` would error with "unrecognized argument". The non-coverage path must keep `--no-fail-fast`. | `grep "ignore-run-fail" src/novetest/run/adapters/cargo_adapter.py` should show it only in the coverage branch. `grep "no-fail-fast" cargo_adapter.py` should still find it in the non-coverage branch. |
| **Existing all-passing cargo fixture unchanged** | The integration test `tests/integration/run/test_cargo_coverage.py` uses `cargo-test-basic-coverage` (all-passing). Pre/post-fix, this test passes — it doesn't exercise the failure-with-coverage path the fix targets. | Scenario 1 above confirms. |
| **The `coverage_lcov` artifact path is now reliable for failing runs** | Other engines (Coverage engine, inspect command, coverage diff) that consume `coverage_lcov` no longer need to defensively check for absence on failing cargo runs. | Scenario 2's `data.memory_entry.run_record.artifact_paths` includes `"coverage_lcov"` even with `status: failed`. |

## Parked work — Localization aggregate fixture redesign (Defect 3 surfaced)

The Loc team's parallel slice (`worktree-localization-fallback-modes`,
tip `c8b7879` → rebased to `320c4ae`) was attempted-merged this
cycle. Both Defect 1 (this slice) and Defect 2 (the fixture redesign)
were fixed and the cargo aggregate e2e got all the way to its final
`endswith("arithmetic.rs")` assertion. But the assertion STILL fails
because of a NEW defect:

**Defect 3 — Localization parser's catch-all regex `\b<file>.rs:N:M`
matches every frame in cargo nextest's default stack backtrace,
including Rust stdlib paths (`/rustc/.../library/core/src/...`).
Stdlib files get `e_f=1` and tie with the real bug file; lexicographic
tie-break pushes `arithmetic.rs` to rank #4.**

Full analysis + 4 suggested fix options (A: drop catch-all regex /
B: parser-output filter / C: algorithm coverage-files filter /
D: combine A+C) in:
`agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md`

The Loc worktree is preserved at the rebased tips. PM dispatches
follow-up.

**Manual Test scope for THIS cycle is the Run slice only.** Do NOT
probe Localization paths — the parked slice isn't on main. The
`localization` verb's existing pytest path continues working (no
Loc src changes landed).

## Notes from merging

- **Run worktree was based on `e8fe8f1`** (PM's task-queue commit,
  one behind main's `6b291e8`). Clean rebase onto `6b291e8` (just
  comms-only diffs; zero file conflicts). FF-merged.
- **Loc worktree was based on `061e741`** (pre-cycle main, six behind
  current). Rebased onto `18fc224` — hit two WORKLOG.md conflicts
  (one per Loc commit). Resolved surgically with incoming-on-top
  convention. After FF-merge, gate had 1 failure (Defect 3). Rolled
  back to `18fc224`.
- **No `--no-verify` / no force-push / no amend** of any published
  commit. Charter discipline preserved.

## Next steps

1. **Manual Test**: run the 6 scenarios above; file `findings/`.
2. **PM**: triage Defect 3 question per the 4 options above
   (recommend Option D). Dispatch a Loc team fix-up slice.
3. **CEO**: cycle authorization fulfilled — push happened with the
   directive "확인하고 머지 푸시해".

---

Filed by: novetest-main-branch-team
Date: 2026-05-31
Cycle: 2026-05-31 fix-up cycle (cargo-llvm-cov-ignore-run-fail +
       aggregate-fixture-redesign) — Run slice merged, Loc slice
       parked AGAIN (Defect 3 surfaced)
