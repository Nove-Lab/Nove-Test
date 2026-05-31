---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-31
slug: build-failure-heuristic-polish
related:
  - agent-comms/tasks/run-team-2026-05-31-build-failure-heuristic-polish.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Handoff: cargo build-failure heuristic — `misconfigured-environment` polish

## TL;DR

Diagnostic UX polish on the cargo adapter's `unparseable-output` branches: when nextest's stderr carries the literal `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, the adapter now raises a specific `misconfigured-environment` `AdapterInvocationError` kind (with override-diagnosis prose pointing at the env var by name) instead of the generic `unparseable-output` (which mis-frames the symptom as a compile failure). Polish applies symmetrically to both the build-failure path and the coverage path. **2 files modified, +109/-7 lines, 0 new src files.** Pre-flight gates all green. Ready to merge.

## Worktree

- **Path:** `/home/yjshin/dev/novetest-build-failure-heuristic-polish`
- **Branch:** `worktree-run-team-build-failure-heuristic-polish`
- **Base commit:** `061e741c5682a4ae5f58cd4d58ac98b7bd020830` (main HEAD: `comms: queue next parallel cycle — Localization fallback modes (1A) + cargo build-failure polish (3B)`)
- **Tip commit:** TBD (will be filled in after the commit below; see Verification §"Commit message" for the staged diff shape)

## Files modified

| File | Lines | Nature |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +45 / −1 | Added `_NEXTEST_LIBTEST_JSON_ENV_LITERAL` module constant + `_libtest_json_env_misconfigured_error` helper. Inserted env-var-literal detection BEFORE both existing `unparseable-output` raises (build-failure path + coverage path). |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +62 / −0 | Added `test_build_failure_heuristic_surfaces_env_var_literal` and `test_collect_coverage_env_var_literal_surfaces_misconfigured_environment` (one per branch). |
| `WORKLOG.md` | +9 / −0 | Top entry `2026-05-31 — phase3 / cargo-build-failure-heuristic-polish` per format. |
| `agent-comms/handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md` | NEW | This file. |
| `agent-comms/INDEX.md` | regen | `python3 tools/regen_comms_index.py` output. |

**Source-file count: 71 → 71** (no new src files; only a string constant + helper function added inside the existing `cargo_adapter.py`).

## DoD bullets believed closed (PM verifies + ticks)

All 7 from task brief §DoD:

- [x] New error branch in `cargo_adapter.py` (line ~305 — was `:263` in brief; coverage slice merging in between shifted line numbers) detects `NEXTEST_EXPERIMENTAL_LIBTEST_JSON` literal in stderr and raises with specific `kind="misconfigured-environment"`.
- [x] **(Optional but recommended)** Symmetric branch in coverage-path handling at line ~342 (was `:286-292` in brief) — implemented; `cargo llvm-cov nextest` wraps nextest and forwards the same `--message-format=libtest-json` argv, so the same env-var requirement applies and the same diagnostic should fire there.
- [x] Unit test pinning the new behavior — implemented. **+2 tests, not +1** (one per branch); see "Open question for PM" below for the rationale.
- [x] Existing generic `unparseable-output` fallback intact for non-matching stderr — verified by `test_build_failure_shape_raises_unparseable` (still passes — its stderr is compile-error text with no env-var literal) and `test_collect_coverage_missing_lcov_raises_unparseable` (still passes — its stub returns empty stderr, no env-var literal).
- [x] Existing cargo integration tests still pass on equipped host (2 passed).
- [x] Full suite green (714 + 5), mypy strict clean (71 source files).
- [x] No `delivery-phasing.md` checkbox implications — this is diagnostic UX polish, not a phase-gated feature.

## `kind` choice rationale (task brief Handoff §2)

**Added one new kind: `"misconfigured-environment"`.** No existing kind fit — the brief's docstring at `errors.py:43` mentions `missing-plugin` / `missing-engine` / `unparseable-output` / `timed-out`; in code `missing-binary` is also used. None convey "environment is configured wrong, this isn't a build failure". The brief explicitly suggested either `"misconfigured-environment"` or `"engine-runtime-misconfigured"`; picked the former because:

1. **Mirrors the existing adjective-noun naming pattern** (`unparseable-output`, `missing-binary`, `missing-plugin`).
2. **Reads more naturally as a CLI error code** — "misconfigured-environment" vs "engine-runtime-misconfigured" is shorter and less Greek-prefixy.
3. **The brief signaled this was first-preference** by listing it first.

`AdapterInvocationError.kind` stays plain `str` (no enum, no `Literal[...]` constraint) — the existing convention. The `errors.py:43` docstring lists four canonical kinds but is non-exhaustive (`missing-binary` is also absent from it); didn't extend the docstring this slice to avoid scope creep. If a future slice formalizes `kind` as a `StrEnum`, the existing five + this new sixth all live in one place to migrate.

## Did you implement the optional symmetric coverage-path branch? (task brief Handoff §3)

**Yes.** Rationale: `cargo llvm-cov nextest` wraps nextest internally and forwards `--message-format=libtest-json`; the env-var gate fires identically on the coverage path. Shipping the source polish only on the build-failure branch would have left a symmetric symptom unrecognized in coverage mode, where it is *more* likely to bite a user (coverage runs are typically debugging or CI-quality-gate flows where a misleading diagnostic costs more time). Cost was ~7 lines of source + 1 test.

## Existing test count + 1 new — actually +2 (task brief Handoff §4)

**Brief expected +1; this slice ships +2.** The +2 is the natural consequence of implementing §2 (the recommended-optional symmetric branch). Reasoning:

- One test per code branch is the existing convention in `test_cargo_adapter.py` (build-failure path has `test_build_failure_shape_raises_unparseable`; coverage path has `test_collect_coverage_missing_lcov_raises_unparseable` — same source-path / one-test-per-branch mirror).
- Shipping the symmetric coverage-path source while testing only the build-failure path would have left the coverage branch as untested defensive code — failure mode here is silent regression on the next polish pass.
- The new test (`test_collect_coverage_env_var_literal_surfaces_misconfigured_environment`) is ~50 lines, takes <0.01s, and locks the spawn-path label `"cargo llvm-cov nextest"` distinct from `"cargo nextest"` — proves the helper's `mode` kwarg is wired through correctly from both call sites (which would otherwise be a silent bug if swapped).

Net: **712 + 5 (baseline) → 714 + 5 (tip)** on equipped host, both new tests accounted for, zero regressions.

## Pre-flight check evidence

### #1 Full gate green

```
$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
[...]
714 passed, 5 skipped in 31.39s
```

Baseline at `061e741` was 712 + 5 on equipped host (per brief; matches the prior cycle's reported tip). **Net: +2 = exactly the 2 new heuristic-polish tests, no regressions.** On a Rust-less box this would read 676 + 7 (per brief: equipped-host 712 ↔ Rust-less 676 differential = 36 cargo integration / coverage tests skipping); my slice's deltas are in `tests/unit/run/adapters/` and run identically regardless of host.

### #2 mypy strict clean

```
$ uv run mypy
Success: no issues found in 71 source files
```

Source-file count unchanged from baseline `061e741` (Coverage's LCOV slice in the prior cycle took count from 70 → 71 by adding `lcov_parser.py`; this slice adds zero src files — only a string constant and a helper function inside the existing `cargo_adapter.py`).

### #3 Cargo integration tests on equipped host

```
$ cargo --version && cargo nextest --version
cargo 1.96.0 (30a34c682 2026-05-25)
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py -v
[...]
2 passed in 1.04s
```

The polish lives purely on the error-detection branches, both of which are dead code on a working environment — the happy path runs identically to baseline, as expected.

### #4 No new src/fixture files

`git diff --stat 061e741..HEAD` (after commit) will show exactly: 5 files changed (`cargo_adapter.py` + `test_cargo_adapter.py` + `WORKLOG.md` + this handoff + `INDEX.md` regen). One new `kind` string constant (`"misconfigured-environment"`) inside `errors.py`-consumer code, no enum formalization needed.

## Commit message (HEREDOC; will be used in commit)

```
refactor(run): surface misconfigured-environment kind on cargo env-var stderr

Diagnostic UX polish on cargo adapter's build-failure heuristic. When
nextest's stderr carries `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, raise a
specific `misconfigured-environment` AdapterInvocationError kind
(with override-diagnosis prose) instead of the generic
`unparseable-output` (which mis-frames the symptom as compile
failure). Applies symmetrically to both the build-failure path and
the coverage path; helper keeps the two emissions in sync.

Per tasks/run-team-2026-05-31-build-failure-heuristic-polish.md.
No new src files; no DoD checkbox implications.

- src/novetest/run/adapters/cargo_adapter.py (+45/-1): module-level
  literal constant + helper; insertion before both unparseable-output
  raises.
- tests/unit/run/adapters/test_cargo_adapter.py (+62/-0): two new
  tests, one per code branch — locks kind, env-var literal in
  message, diagnosis prose, AND distinct spawn-path label per branch.
- mypy strict: 71 source files. Full gate: 714+5 (baseline 712+5).
  Cargo integration on equipped host: 2 passed.
```

## Open question for PM (non-blocking)

The task brief's "Existing test count + 1 new" expectation was based on §3's mandate alone. Implementing the recommended-optional §2 symmetric coverage-path branch led to +2 tests (one per branch). The deviation is in the user's favor (more thorough coverage; matches the file's existing one-test-per-branch convention). Flagging here so future briefs that include an "optional" branch can pre-specify whether the test count is `+1` or `+1 per implemented branch`.

No change requested for this slice — proceeding as +2.

## Worklog entry text (pasted; lives at WORKLOG.md top)

```
## 2026-05-31 — phase3 / cargo-build-failure-heuristic-polish

- Landed: Diagnostic UX polish on the cargo adapter's build-failure
  heuristic per `tasks/run-team-2026-05-31-build-failure-heuristic-polish.md`
  — when nextest's stderr carries the literal `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`,
  the adapter now raises a specific `misconfigured-environment`
  `AdapterInvocationError` kind rather than the generic `unparseable-output`.
  [...full 5-bullet entry follows in WORKLOG.md...]
```

(See `WORKLOG.md` top entry for the full text — 5-bullet format, all four pre-flight check results inline, both gotchas pinned.)
