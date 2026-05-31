---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-31
slug: cargo-llvm-cov-ignore-run-fail
related:
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Task: cargo adapter — swap `--no-fail-fast` for `--ignore-run-fail` on `cargo llvm-cov nextest` invocation (Defect 1)

## TL;DR

`cargo llvm-cov nextest --no-fail-fast` does NOT write the LCOV file
when the inner cargo-nextest exits non-zero (i.e., any failing test).
Swap to `--ignore-run-fail` on the coverage-collection argv ONLY.
The two flags are mutually exclusive; `--ignore-run-fail` is the
cargo-llvm-cov form that means "tests can fail, still emit the
coverage report". Without this fix, `novetest run --coverage` against
any cargo workspace with at least one failing test returns
`adapter-unparseable-output`.

**Surfaced by Main Branch's 2026-05-31 gate failure** on the
Localization fallback-modes slice. Empirical reproduction in
`agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
§"Defect 1 — Reproduction".

Tiny surgical fix: **1-line src change + 1-line test**.

## Why this slice exists (product framing)

The cargo adapter was first verified end-to-end on 2026-05-31
against a fixture where all tests PASS (`cargo-test-basic-coverage`).
The coverage path's `--no-fail-fast` flag was correct for that case
(no failures → exit 0 → coverage written). But when ANY cargo test
fails, cargo-nextest exits 100, cargo-llvm-cov refuses to write
LCOV with `--no-fail-fast`, and the adapter's existing fallback
"cargo llvm-cov did not write coverage.lcov" error fires.

Real-world consequence: any Rust developer with a failing test on
their workspace gets `adapter-unparseable-output` when they run
`novetest run --coverage`. Which is **exactly the use case
Localization needs** (Localization runs against runs with failures).

This is also the precondition for the Localization fallback-modes
slice (parked at `a42ea87` per the 2026-05-31 question doc). That
slice MUST land after this fix — it depends on this fix to make
its aggregate-mode e2e test pass.

## Scope (what this slice DOES)

### 1. Swap the flag

**Where**: `src/novetest/run/adapters/cargo_adapter.py` — the
cargo-llvm-cov argv assembly path.

The current argv (per Main Branch's empirical observation in the
question doc §Defect 1) is:
```
cargo llvm-cov nextest --no-fail-fast --workspace \
  --message-format=libtest-json --lcov --output-path coverage.lcov
```

Change to:
```
cargo llvm-cov nextest --ignore-run-fail --workspace \
  --message-format=libtest-json --lcov --output-path coverage.lcov
```

**CRITICAL constraint**: The flag swap is on the
**`cargo llvm-cov nextest`** invocation ONLY. The non-coverage path
(`cargo nextest run` invoked directly, without the cargo-llvm-cov
wrapper) MUST keep `--no-fail-fast` because `--ignore-run-fail` is
a **cargo-llvm-cov flag**, not a cargo-nextest flag. Passing it to
plain cargo-nextest would error.

If the argv is currently constructed via a shared list that BOTH
paths consume, refactor minimally to split: e.g., a
`_build_llvm_cov_argv()` vs `_build_nextest_argv()` distinction,
OR a single helper with a `coverage: bool` flag that branches on
which fail-fast variant to emit.

### 2. Docstring note

Add a 2-3 sentence docstring note on the cargo-llvm-cov argv
assembly explaining WHY `--ignore-run-fail` rather than
`--no-fail-fast`: nextest exits non-zero on test failure;
cargo-llvm-cov with `--no-fail-fast` refuses to emit the LCOV report
under that condition; `--ignore-run-fail` internally implies
`--no-fail-fast` but ALSO emits the report. Reference the question
doc's §Defect 1 for the empirical evidence.

### 3. Unit test pinning the new argv

**Where**: `tests/unit/run/adapters/test_cargo_adapter.py`

Add ONE new test that asserts the cargo-llvm-cov argv contains
`--ignore-run-fail` and does NOT contain `--no-fail-fast` for the
coverage-collection invocation. Mirror existing argv-assertion test
patterns in the file (there should be tests that assert the
non-coverage path's argv contains `--no-fail-fast` — keep those
intact; they're now the regression-pinning tests for the
non-coverage path).

If no per-flag argv-content unit test exists today (only happy-path
shape tests), add ONE that captures the cargo-llvm-cov full argv
in a fixture call and asserts both invariants:
- `--ignore-run-fail` IS in the argv (coverage path)
- `--no-fail-fast` is NOT in the argv (coverage path)

The non-coverage path's existing tests should remain green
unchanged — verify by running `tests/unit/run/adapters/test_cargo_adapter.py`
in isolation pre/post.

## Out of scope (do NOT touch)

- **Non-coverage cargo nextest argv** — `--no-fail-fast` stays
  there. `--ignore-run-fail` is cargo-llvm-cov-specific.
- **Any other adapter** — pytest / jest / gotest are unrelated.
- **`_build_child_env()`** — env-var setup is correct; the 2026-05-31
  hotfix and the build-failure heuristic polish (3B, just merged
  at `8910bf1`) cover that surface.
- **Build-failure heuristic at `cargo_adapter.py:282`** — out of
  scope. The 3B polish slice (`misconfigured-environment` kind)
  already shipped; that branch correctly fires for env-var-related
  misconfigurations. The Defect 1 case (cargo-llvm-cov refusing to
  write LCOV) hits a DIFFERENT branch (`cargo llvm-cov did not write
  coverage.lcov`); that branch's behavior is correct (it's surfacing
  the symptom) — this slice fixes the ROOT cause upstream so the
  branch doesn't fire on failing-test runs.
- **`cargo-test-basic-coverage` fixture** — all tests pass there;
  not affected by this fix. Don't touch the fixture.

## Pre-flight checks (before opening handoff)

1. **Equipped host**: `cargo`, `cargo-nextest`, `cargo-llvm-cov` all
   on PATH (same precondition as recent cargo slices).
2. **Empirical reproduction** of the bug pre-fix on the
   `localization-aggregate-only` fixture (lives at
   `tests/fixtures/projects/localization-aggregate-only/` — already
   on disk from the parked Localization worktree's commits, OR
   you may need to fetch from `a42ea87` worktree path):

   ```sh
   . "$HOME/.cargo/env"
   cp -r /home/yjshin/dev/novetest-localization-fallback-modes/tests/fixtures/projects/localization-aggregate-only /tmp/lao-probe
   cd /tmp/lao-probe
   NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
     --no-fail-fast --workspace --message-format=libtest-json \
     --lcov --output-path coverage.lcov
   echo "lcov written: $(test -f coverage.lcov && echo YES || echo NO)"
   # Expected pre-fix: "lcov written: NO"
   ```

3. **Empirical proof of fix** after swap:
   ```sh
   NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 cargo llvm-cov nextest \
     --ignore-run-fail --workspace --message-format=libtest-json \
     --lcov --output-path coverage.lcov
   echo "lcov written: $(test -f coverage.lcov && echo YES || echo NO)"
   # Expected post-fix: "lcov written: YES"
   ```

   The fixture's `divide` function is intentionally broken (`a + b`
   instead of `a / b`); `test_divide` is intentionally failing. The
   probe above is the SAME failure scenario the Localization e2e
   reproduces.

4. **`novetest run --coverage` end-to-end** on the same fixture:
   ```sh
   cd /tmp/lao-probe
   uv run --project /home/yjshin/dev/Nove-Test novetest init
   uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage
   echo "exit=$?"
   # Expected post-fix: exit 3 (test-failures-detected), ok: true (transport ok),
   # has_coverage_facts: true, coverage_outcome.kind: "fact-set"
   ```

5. **Full gate green**:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline at `345b663`: **714 + 5** on equipped host, **676 + 7**
     on Rust-less.
   - Your tip = baseline + 1 new argv test. No regressions on the
     ~14 existing cargo unit tests.

6. **mypy strict clean**: `uv run mypy` → no issues, **71 source
   files** (unchanged; this slice adds no new modules).

## DoD

- [ ] cargo-llvm-cov argv uses `--ignore-run-fail` instead of
      `--no-fail-fast`.
- [ ] Non-coverage cargo-nextest argv UNCHANGED (still uses
      `--no-fail-fast`).
- [ ] Docstring at the argv-assembly site documents the flag-swap
      rationale.
- [ ] Unit test asserts `--ignore-run-fail` IN cargo-llvm-cov argv
      AND `--no-fail-fast` NOT IN cargo-llvm-cov argv.
- [ ] Non-coverage path's existing argv tests still pass (regression
      pinning).
- [ ] Empirical `lcov_written: YES` proof on the
      `localization-aggregate-only` fixture documented in the handoff.
- [ ] `novetest run --coverage` E2E against the fixture produces
      `has_coverage_facts: true` post-fix.
- [ ] Full pytest suite green; mypy strict clean.

## Handoff format

Standard handoff at
`agent-comms/handoffs/run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Pre-flight proof-of-fix evidence** — paste the verbatim
   `lcov_written: YES` shell output from §"Pre-flight check #3".
3. **End-to-end smoke evidence** — paste the verbatim envelope from
   `novetest run --coverage` showing `has_coverage_facts: true` and
   `coverage_outcome.kind: "fact-set"` against the
   `localization-aggregate-only` fixture.
4. **DoD implications** — none on `delivery-phasing.md` (bug fix to
   a landed adapter). This slice unblocks the Localization
   fallback-modes slice's e2e test.
5. **Open questions for PM** — anything that surfaced (especially:
   was the argv refactor needed to split the two paths cleanly, or
   was a single helper sufficient?).

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + new `agent-comms/` files + `INDEX.md`
   alongside source.

## Cross-references

- **Empirical reproduction + empirical fix proof**:
  `agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
  §"Defect 1".
- **Parked Localization worktree** (will rebase + re-test their
  aggregate-mode e2e AFTER this fix lands; their fixture is the
  test workload for your pre-flight):
  `/home/yjshin/dev/novetest-localization-fallback-modes` @ `a42ea87`.
- **Sibling fix slice** (Localization fixture redesign, parallel
  dispatch but their handoff blocks on THIS fix being on main):
  `agent-comms/tasks/localization-team-2026-05-31-aggregate-fixture-redesign.md`.
- **cargo adapter execution-path posture** (unchanged by this slice):
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`.
