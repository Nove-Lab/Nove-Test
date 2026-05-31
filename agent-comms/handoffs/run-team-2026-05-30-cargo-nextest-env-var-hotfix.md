---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-31
slug: cargo-nextest-env-var-hotfix
related:
  - agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Handoff: cargo adapter hotfix — set `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`

## TL;DR

Two-line source change inside `_build_child_env()`: add
`env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"`. Without it,
`cargo-nextest ≥ 0.9.50` rejects the `--message-format=libtest-json`
flag the adapter passes, exits 95, and the build-failure heuristic
misclassifies the failure as `adapter-unparseable-output` — every
`novetest run` against a Rust workspace on an equipped host returned
exit `4` with empty data. Plus one unit test pinning the env var's
presence + a docstring bullet explaining the requirement. Pre-flight
host check passed (cargo-nextest 0.9.137 on this dev box) — both
cargo integration tests **RAN AND PASSED** on the equipped host.

## Worktree

- Path: `/home/yjshin/dev/novetest-cargo-nextest-env-var-hotfix`
- Branch: `worktree-run-team-cargo-nextest-env-var-hotfix`
- Base commit: `e90f61e` (current `main` tip at session start —
  `comms: decide Issue 2 — typed metadata slot on NativeResult (b
  chosen)`)
- Tip commit: set by `git commit` (see "Commit message" below)

## Files written / modified

### Source (1 file modified)

- `src/novetest/run/adapters/cargo_adapter.py`
  - `_build_child_env()` body: added single line
    `env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"` after the
    existing `NO_COLOR` assignment, before `return env`. Surgical
    only — the three existing env var assignments are unchanged.
  - `_build_child_env()` docstring: extended the bulleted env-var
    list with a fourth bullet pinning **why** the new env var is
    required. Pinned in the docstring:
    - References `decisions/2026-05-25-supported-engine-matrix.md`
      for the cargo-nextest 0.9.50 floor.
    - Explains the gate's purpose (nextest 0.9.50+ requires it
      before accepting `--message-format=libtest-json`).
    - Documents the consequence of omission (exit 95 + zero
      events → build-failure heuristic misclassifies as
      `adapter-unparseable-output`).
  - The "Notably absent" sub-list is unchanged (`RUSTFLAGS` /
    `CARGO_INCREMENTAL` still excluded for the
    build-cache-preservation reason from the adapter's original
    landing slice).

### Tests (1 file modified)

- `tests/unit/run/adapters/test_cargo_adapter.py`
  - Imports: extended the `from
    novetest.run.adapters.cargo_adapter import (...)` block with
    `_build_child_env` (private symbol — fine within the unit test
    module that owns this file's coverage; the file already
    monkey-patches the module-level `run_subprocess` and adapter
    internals, so importing a private helper is consistent).
  - Added one new test at the end of the file:
    `test_build_child_env_pins_nextest_libtest_json_gate` — pure
    synchronous function test (no async, no monkeypatch, no
    fixtures, no subprocess stub). Asserts that the dict returned
    by `_build_child_env()` contains all four pinned env vars:
    - `NEXTEST_EXPERIMENTAL_LIBTEST_JSON == "1"` (the new one;
      asserted first because it is the load-bearing key for this
      hotfix).
    - `CARGO_TERM_COLOR == "never"`,
      `RUST_BACKTRACE == "1"`, `NO_COLOR == "1"` (the three
      pre-existing keys — asserted in the same test for
      symmetry, so the test pins the full determinism surface
      and would catch a future regression that drops any of the
      four).
    Docstring explains the failure-mode chain and references the
    supported-engine-matrix decision.
  - No other test in the file is modified. The 16 prior
    `run_cargo`-shaped tests (happy-path / argv / failure-log /
    integration-binary node-id / build-failure heuristic / skip
    action / missing-binary / FileNotFoundError / timeout /
    malformed-json / coverage on+off / missing-coverage-lcov /
    engine-version probe paths) still cover the rest of the
    adapter verbatim — total cases in this file go from 16 → 17.

### Comms / WORKLOG

- `WORKLOG.md`: top entry added (`2026-05-31 — phase3 /
  cargo-nextest-env-var-hotfix`).
- `agent-comms/handoffs/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`:
  this file.
- `agent-comms/INDEX.md`: regenerated via
  `python3 tools/regen_comms_index.py` post-handoff.

### Files NOT touched (per task brief Out-of-scope)

- `src/novetest/run/adapters/cargo_adapter.py:263` build-failure
  heuristic — Manual Test surfaced this as a low-priority UX
  polish; separate slice, not load-bearing for this hotfix.
- `src/novetest/run/normalizer.py` — Issue 2 (`nextest_version`
  payload-stash → typed slot) is its own slice per
  `decisions/2026-05-30-native-result-metadata-slot.md` "Dispatch
  ordering" (must land AFTER this hotfix to avoid
  `cargo_adapter.py` merge conflict).
- `src/novetest/models/native_result.py` — same Issue 2 reason.
- `src/novetest/coverage/**` — LCOV parser dispatch on
  `engine_name == "cargo-test"` is a Coverage-team carry-forward.
- `agent-comms/decisions/**` — PM territory.
- `agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`
  — original brief is not edited (status flip to `done` is PM's
  cycle-cleanup step).

## Pre-flight host check evidence (per task brief §"Pre-flight host check")

Per task brief: "unit + integration tests on the host-absent path
are NOT a substitute for the host-present path. Before opening the
handoff [...]"

```
$ . "$HOME/.cargo/env" && cargo nextest --version && echo '---' && cargo --version
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)
release: 0.9.137
commit-hash: 75ddba7e911b44c5c0700dac0415d824403de9bd
commit-date: 2026-05-26
host: x86_64-unknown-linux-gnu
---
cargo 1.96.0 (30a34c682 2026-05-25)
```

- `cargo-nextest 0.9.137` is well above the 0.9.50 floor from
  `decisions/2026-05-25-supported-engine-matrix.md`.
- `cargo 1.96.0` matches the version Manual Test ran the 2026-05-30
  sweep with.

```
$ cd /home/yjshin/dev/novetest-cargo-nextest-env-var-hotfix \
    && . "$HOME/.cargo/env" \
    && uv run pytest -q tests/integration/run/test_cargo_basic.py \
                       tests/integration/run/test_cargo_coverage.py -v
tests/integration/run/test_cargo_basic.py .                              [ 50%]
tests/integration/run/test_cargo_coverage.py .                           [100%]
============================== 2 passed in 1.12s ===============================
```

- **2 passed, 0 skipped, 0 failed** — both cargo integration tests
  **RAN AND PASSED** on the equipped host. Task brief's expected
  post-hotfix outcome met verbatim.
- Total runtime 1.12s (well under the ~3 min budget — the coverage
  fixture's `cargo llvm-cov nextest` path is fast on this dev box
  because the fixture is small and the build cache was warm).

## Verification (full surface)

| Surface | Command | Result |
|---|---|---|
| Adapter unit tests in isolation | `uv run pytest -q tests/unit/run/adapters/test_cargo_adapter.py` | **17 passed in 0.09s** (16 prior + 1 new — `test_build_child_env_pins_nextest_libtest_json_gate`) |
| Full unit + integration suite | `uv run pytest -q tests/unit tests/integration` | **676 passed + 7 skipped in 30.26s** (baseline `e90f61e` was 675+7 → +1 net = +1 new test, no regressions; cargo integration tests RAN AND PASSED inside this run, not skipped, because the dev box is Rust-equipped) |
| Cargo integration tests in isolation | (see pre-flight host check above) | **2 passed in 1.12s** (RAN, not skipped) |
| Static typing | `uv run mypy` | **Success: no issues found in 70 source files** (`--strict`; source file count unchanged from `e90f61e` — no new src files) |

## Commit message

```
fix(run): set NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 in cargo adapter env

cargo-nextest >= 0.9.50 (our supported floor per
decisions/2026-05-25-supported-engine-matrix.md) gates the
--message-format=libtest-json flag the adapter passes behind the
NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 env var. Without it, nextest exits
95 with the literal runtime error "libtest JSON output is an
experimental feature and must be enabled with
NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1" and writes zero parseable events;
the build-failure heuristic at cargo_adapter.py:263 then misclassifies
exit-95-with-no-events as adapter-unparseable-output.

Surfaced by Manual Test's 2026-05-30 cargo E2E sweep (Issue 1) — every
novetest run against a real Rust workspace on the equipped host
returned exit 4 with empty data and no actionable error.

Two-line source change inside _build_child_env() + a docstring bullet
pinning the requirement + one unit test asserting the env var is
present in the returned dict (alongside the three existing determinism
keys for symmetry).

Pre-flight host check passed: cargo-nextest 0.9.137 on this dev box,
both tests/integration/run/test_cargo_*.py RAN AND PASSED (2 passed in
1.12s) — task DoD bar met.

Verified: 676 passed + 7 skipped (was 675+7 at e90f61e; +1 net test,
no regressions). mypy --strict clean, 70 source files (unchanged).

Closes Issue 1 from the 2026-05-30 cargo sweep. Trigger-(b) closure
of decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
completes when Manual Test re-runs the sweep against this commit.
```

## DoD bullets believed closed

**None** — this is a bug fix to a landed adapter (commit `6d9f463`),
not a new DoD-tracked feature. Per task brief Handoff §3:
"No `delivery-phasing.md` checkbox implications".

The hotfix closes Issue 1 from the 2026-05-30 cargo E2E sweep
(findings file deleted at cycle close 2026-05-30; reproducer + proof
of fix inlined in the task brief for self-containment). PM closes
Issue 1 in cycle-cleanup; no `- [ ]` ticks in
`design/implementation-plan/delivery-phasing.md` from this slice.

## Why these specific decisions

(In case Main Branch needs to defend the diff during a merge review.)

1. **Single new env var assignment, no refactor to a constant list /
   helper.** Karpathy "wait for the third instance" — the four env
   vars are still a flat assignment block, not a data-driven loop.
   Adding the fourth assignment in place keeps the cognitive cost
   minimal and the diff microscopic.

2. **Docstring bullet form mirrors the existing three.** Each of
   the existing three env vars in the docstring has the shape
   "``<NAME>=<value>`` short rationale". The new bullet uses the
   same shape and additionally documents the consequence-of-omission
   chain (exit 95 → zero events → heuristic misclassification)
   because that consequence is what made the original adapter
   slice ship without this env var (it was untested on an equipped
   host, per `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`).

3. **Pure-function unit test, no async/monkeypatch machinery.**
   `_build_child_env()` is synchronous and dependency-free; the
   test imports the helper directly, calls it, and asserts on the
   returned dict. No need for the `_stub_cargo_on_path` autouse
   fixture (which targets `run_cargo`'s `shutil.which("cargo")`
   guard, not this helper). The test pins the full four-key
   determinism surface (not just the new key) so a future
   regression that drops any of the four would surface as a test
   failure here rather than as an environment-conditional
   integration test failure.

4. **The four env vars are asserted in one test, not four.** Task
   brief §3 says "model after the existing
   `CARGO_TERM_COLOR` / `RUST_BACKTRACE` / `NO_COLOR` assertion
   patterns in adjacent unit tests" — but grep shows no such
   existing assertions in the file (the three existing env vars
   were never directly tested before this slice; their presence
   was only observable indirectly through the integration tests).
   So I followed the spirit of the brief (pin the env var
   presence) and consolidated all four assertions into one
   focused test rather than spawning a redundant four-test
   parametrize.

## Open questions / surprises for PM

**None blocking.** Two minor observations:

1. **The three pre-existing env vars in `_build_child_env()` had
   no direct unit-test coverage** before this slice — they were
   only exercised indirectly through the integration tests (which
   skip on Rust-less CI cells). This new test pins all four keys
   for symmetry, so the gap closes incidentally as part of this
   hotfix. No action needed; just noted in case PM wants to
   reference this pattern when the Memory/Run typed-slot Issue 2
   slice lands (that slice will touch `cargo_adapter.py` payload
   construction; the env var coverage is now stable).

2. **The cargo integration tests' fixture in the worktree is
   self-contained** — the fixture `tests/fixtures/projects/cargo-test-basic`
   has its own `Cargo.lock` build artifacts cached under `target/`
   from the 2026-05-30 sweep, so the 1.12s runtime reflects a
   warm-cache run. A clean cargo-build cold-start would take
   longer (~10-30s for the initial compile of even this tiny
   fixture). This is fine for the dev host pre-flight gate but
   Manual Test should expect a slower first run when they verify
   on their box. The task brief's "~3 min" budget is generous
   enough.

## Cross-references

- **Task brief**:
  `agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`
- **Supported-engine matrix** (the 0.9.50 floor):
  `agent-comms/decisions/2026-05-25-supported-engine-matrix.md`
- **Cargo adapter execution-path decision** (nextest-only,
  libtest-json):
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
  §1
- **Polyglot host parity decision** (trigger-(b) closure
  condition):
  `agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  §3
- **Issue 2 (deferred — separate slice)**:
  `agent-comms/decisions/2026-05-30-native-result-metadata-slot.md`
  §"Dispatch ordering"
- **Cycle context with full history**:
  `agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
  §"Issues raised by the cargo sweep" + §"Cargo trigger-(b) status"
