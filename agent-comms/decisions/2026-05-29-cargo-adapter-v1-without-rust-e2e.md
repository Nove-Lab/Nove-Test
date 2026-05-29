---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-29
slug: cargo-adapter-v1-without-rust-e2e
related:
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
---

# Decision: cargo adapter ships v1 without full Manual Test E2E; polyglot host parity recorded as forward commitment

CEO-approved on 2026-05-29.

## Context

The `cargo nextest` Native Engine adapter (commit `6d9f463`) merged
into `main` with:

- **Unit + integration test gate clean** — 667 passed / 5 skipped;
  mypy strict clean on 70 source files. The cargo slice itself added
  +29 net unit passes covering the libtest-json parser, node_id `::`
  convention, per-test failure-log filename safety, build-failure
  detection, LCOV-missing detection, and the four readiness branches.
- **Engine-missing readiness path Manual-Test-verified verbatim** —
  Manual Test ran `novetest run` against the cargo-test-basic fixture
  on a host without `cargo` on PATH and observed the exact expected
  envelope (`state=engine-missing`, `evidence=["Cargo.toml"]`,
  `errors[0].code=engine-engine-missing`, install-hint URL
  `https://rustup.rs`, shell exit code 4).
- **Running-cargo paths NOT Manual-Test E2E verified** — the Manual
  Test host did not have the Rust toolchain installed (`rustc`,
  `cargo`, `cargo-nextest`, `cargo-llvm-cov` all absent), so the two
  `tests/integration/run/test_cargo_*.py` cases skipped cleanly via
  their `shutil.which(...)` guards.

The five unverified branches:

1. Basic `cargo nextest run` envelope — libtest-json parsing,
   node_id `::` convention, `engine_name == "cargo-test"`
   propagation, summary counts.
2. Coverage path with `cargo-llvm-cov` — LCOV artifact registration,
   build-failure-detector carve-out for coverage mode.
3. Readiness paths beyond `engine-missing` — the three
   `engine-misconfigured` flavors (no nextest, broken cargo version,
   missing Cargo.toml on a Rust-looking workspace).
4. `nextest_version` payload-stash surface in the persisted Run
   Record envelope (the convention question raised by the Run team in
   handoff §Open items #1).
5. Various combinations (coverage with intentionally failing tests,
   integration-test-binary distinction, etc.).

These five branches are exercised by the Run team's 16 unit-test
cases at the subprocess seam (with stubbed `run_subprocess`), but no
real `cargo nextest run` invocation against an actual Rust workspace
ran at the Manual Test layer.

## What this decision pins

### 1. v1 ships with unit + integration gate as the E2E signal for cargo

The 667-pass gate plus the cargo-specific 29 unit additions is
accepted as the v1 E2E signal for the running-cargo paths. cargo is
the **first adapter to ship without Manual Test E2E verification of
its native-engine execution path** — pytest, jest, and gotest were
all probed against running toolchains on their respective Manual Test
hosts.

This is a v1 exception, not a new norm. The default expectation
remains "Manual Test host has the native toolchain installed; the
integration tests run rather than skip".

### 2. Polyglot host parity is a forward commitment, not deferred backlog

**Ultimately every native engine MUST receive Manual Test E2E
verification at the same fidelity as Python pytest.** This is a
product-quality contract, not a nice-to-have. The pattern that
delivered pytest / jest / gotest at full E2E fidelity (Manual Test
host has the native toolchain installed; the relevant
`tests/integration/run/test_<engine>_*.py` cases run rather than
skip) MUST be extended to Rust, Java, and .NET before MVP release.

This commitment is recorded here as a permanent forward marker so
future PMs reviewing Phase 3/4/5 close-out know the cargo gap (and
the anticipated JUnit / dotnet gaps) is a **known liability with an
explicit closure plan, not a forgotten omission**.

### 3. Closure triggers (any one closes the cargo gap)

The cargo running-cargo branches' E2E gap closes when any of the
following first occurs:

- **(a) Release team adds a Rust cell to the CI matrix.**
  `decisions/2026-05-29-cargo-adapter-nextest-primary.md` §Affected
  already commits Release to this in their next CI workflow sweep.
  Once landed, the two `tests/integration/run/test_cargo_*.py` cases
  run rather than skip on CI, providing automated E2E coverage that
  effectively replaces the Manual Test gap.
- **(b) The Manual Test host gains the Rust toolchain.** Triggered
  by CEO installing `rustup` + `cargo install cargo-nextest --locked`
  + `cargo install cargo-llvm-cov` on the host that Manual Test runs
  against, then dispatching a follow-up Manual Test pass that
  exercises Steps 2-5 of the original verification doc verbatim.
  CEO indicated this path at a **short-future appropriate time** as
  the preferred trigger (option β as discussed at close).
- **(c) A "polyglot host parity" sweep cycle is dispatched.**
  Triggered when JUnit and/or dotnet adapters accumulate the same
  gap pattern; PM bundles cargo + Java + .NET (+ optionally Node
  re-validation) into one Manual Test sweep with the host explicitly
  equipped first. Option γ as discussed at close — kept available
  but not the preferred near-term path.

PM tracks (b) as an open polyglot-host backlog item, not as a queued
`tasks/` cycle. (b) and (c) are not exclusive — if (a) lands first
the gap is functionally closed regardless.

### 4. JUnit and dotnet anticipation

Phase 3 adapter backlog remains 4/6 (pytest + jest + go-test +
cargo-test landed; JUnit and dotnet pending Open Questions #4 + #5).
JUnit and dotnet will require the same host-toolchain pattern when
they land. This decision anticipates the same Manual Test E2E gap
for them unless trigger (b) or (c) has already fired by then. PM
documents the gap and trigger options up front in each new adapter
task brief.

## What this decision does NOT decide

- **Floor-version CI lane.** The `2026-05-25-supported-engine-matrix.md`
  "Mitigation slices" backlog item (defensive parsing audit +
  floor-version CI lane + engine-readiness probe enhancement) is
  about validating the *minimum* supported version of each engine.
  This decision is about cross-engine E2E parity at the *tested
  ceiling*. The two backlogs are independent.
- **What "MVP release" precisely requires** for polyglot host parity
  — whether all 6 engines must be Manual-Test E2E green before MVP,
  or whether automated CI-cell coverage suffices for a subset. This
  is a forward commitment; the specific gate is a future Release /
  PM call closer to MVP.
- **The `nextest_version` payload-stash convention question** raised
  in the Run team's handoff §Open items #1. That question is recorded
  in `2026-05-29-cargo-adapter-nextest-primary.md` §"What this does
  NOT decide" and resolves naturally when trigger (a) or (b) fires
  and a real Rust workspace exposes the surface.

## Affected teams / files

- **PM** — owns this commitment; reviews the cargo gap at every
  Phase 3 close-out checkpoint until one of the triggers fires;
  surfaces the same gap-disclosure pattern in JUnit / dotnet task
  briefs when they land.
- **Release team** — owns trigger (a). The Rust CI cell, when added,
  also serves as the cargo gap's automated closer. (Coordinate with
  the Java and .NET CI cells if those land first.)
- **Run team** — when writing JUnit / dotnet adapter briefs,
  includes the same polyglot-host gap disclosure pattern as this
  cargo cycle.
- **Manual Test team** — when host toolchains arrive (trigger b/c),
  picks up the cargo re-verification sweep covering Steps 2-5 of the
  2026-05-29 cargo verification doc.
- **`design/implementation-plan/foundations.md`** — the Native Engine
  principle and CI parity language are reinforced by this decision;
  no edit needed but should be linked when foundations is next
  revised.

## Effective date

2026-05-29.

## Supersedes

Nothing. First articulation of the polyglot host parity commitment.
The cargo-adapter-nextest-primary decision (2026-05-29) and the
supported-engine-matrix decision (2026-05-25) remain in force; this
decision adds the E2E parity contract on top of them.
