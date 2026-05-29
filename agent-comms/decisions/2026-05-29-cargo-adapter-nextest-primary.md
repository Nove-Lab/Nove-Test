---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-29
slug: cargo-adapter-nextest-primary
related:
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/tasks/run-team-2026-05-29-cargo-adapter.md
---

# Decision: cargo adapter ships nextest-primary, no nightly path, no plain-text fallback in v1

CEO-approved on 2026-05-29. Closes **Open Question #3**
(`delivery-phasing.md` table) — "`cargo nextest libtest-json`
graduation off nightly".

## Context

Three structurally different paths exist to get structured test output
from a Rust workspace:

| Path | Stability | Format |
|---|---|---|
| `cargo test --format=json -Z unstable-options` | **nightly Rust only** (`-Z` gate) | JSON stream |
| `cargo nextest run --message-format=libtest-json` | **stable nextest 0.9.50+** on stable Rust | JSON stream |
| `cargo test` (plain text) | stable, universal | lossy human-readable |

`engine-adapters.md §5` initially sketched a hybrid posture: nextest
as primary, plain-text `cargo test` as a lossy fallback for users
without nextest installed. Open Question #3 asked whether to
**re-evaluate** when the `cargo test --format=json` nightly path
graduates to stable — that would let the fallback be structured
instead of lossy.

## Decision

The cargo adapter ships with **`cargo-nextest` as the only execution
path**. Specifically:

1. **`cargo-nextest >= 0.9.50` is the floor**, surfaced as
   `engine-misconfigured` when absent. The install hint is
   `"install cargo-nextest: cargo install cargo-nextest --locked (or
   use cargo binstall)"`.
2. **No plain-text `cargo test` fallback.** Users without nextest
   cannot run via `novetest`; they get a clear, actionable error.
3. **No nightly `cargo test --format=json` path.** The `-Z
   unstable-options` flag is rejected by stable Rust; building
   against it would either lock the adapter to nightly toolchains
   (regressing Rust support to "nightly required") or require
   runtime version branching that doubles parser code. Neither is
   warranted at v1.
4. **`libtest-json` graduation watch.** When `cargo test
   --format=json` graduates to stable Rust (date TBD by upstream), the
   adapter MAY add a plain-`cargo test` execution path as a
   non-breaking extension. Until then, the watch is informational —
   PM tracks the Rust release notes, no scheduled slice.

## Rationale

### Why nextest-only is not a hardship

`cargo-nextest` is the de facto modern Rust test runner — adopted by
the majority of mature Rust projects and integrated into the standard
Rust CI tooling. Asking users to `cargo install cargo-nextest --locked`
once is a small ask compared to the lossy alternative.

### Why plain-text fallback is structurally wrong

Plain-text `cargo test` output is:
- Locale-dependent (`Ok` vs `passed` text varies by Rust version).
- Format-unstable across minor Rust versions.
- Lacks per-test duration, captured output, and structured failure
  detail.

A parser for it would be a permanent maintenance burden, would silently
degrade `TestResult` fidelity (`failure_reference: null`, `duration_ms:
null` for most results), and would obscure the `engine-misconfigured`
signal that nextest's absence should produce.

### Why nightly is out

Nove Test's contract per `foundations.md §1` is **stable Python +
stable toolchains end-to-end**. Adding nightly Rust as a build path
for cargo adapter parity inverts this. The graduation watch covers the
upside if/when upstream removes the `-Z` gate.

### What this implies for the supported-engine-matrix

A new `cargo` row will be added to
`decisions/2026-05-25-supported-engine-matrix.md` when the Run-team
slice closes. Indicative shape (Run team proposes the exact numbers in
their handoff):

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| `cargo` (Rust toolchain) | 1.74 | TBD (Run-team handoff proposes; Release adds CI cell) | matches edition 2021 + nextest 0.9.50 baseline |
| `cargo-nextest` | 0.9.50 | TBD | floor pinned by `libtest-json --message-format` stability |
| `llvm-tools-preview` rustup component | — | — | required by `cargo-llvm-cov` for coverage; absence surfaces as `engine-misconfigured` |

PM amends the matrix in the cycle-close commit.

## What this decision does NOT decide

- **Per-test coverage attribution for Rust.** The
  `--per-test-coverage` slow-mode path
  (`engine-adapters.md §5`) is unaffected by this decision and remains
  deferred to a post-MVP slice. The Q3 closure does not gate that.
- **Doctest execution (`cargo test --doc`).** Separate path, separate
  parser, future slice. Not in scope.
- **Race detector / thread sanitizer modes.** Separate flags, separate
  Run modes, future work.
- **JUnit-XML fallback for pre-0.9.50 nextest.** If a user's nextest
  version predates 0.9.50, the adapter surfaces `engine-misconfigured`.
  A JUnit-XML fallback parser could be added later WITHOUT auto-writing
  `.config/nextest.toml` (which our adapters never do), but that work
  is not scheduled at v1.
- **The `nextest_version` payload-stash convention** (raised in the
  Run team's handoff §Open items #1). The Run team stashed
  `nextest_version` in `NativeResult.payload["nextest_version"]`
  rather than `NativeEngineContext` (which is a frozen dataclass
  with no extension hook), keeping `models/` untouched. The eventual
  call — codify payload-stash as the engine-version-stash convention,
  OR amend `NativeEngineContext` with an optional
  `metadata: dict[str, str]` slot in a future `models/` slice — is
  deferred until a polyglot-host pass actually inspects where
  `nextest_version` surfaces in a persisted Run Record. Added
  2026-05-29 at the cycle-close — see
  `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §"What
  this does NOT decide" for the trigger conditions.

## Affected files / teams

- **Run team** — implements the adapter under the constraints above
  (per task brief
  `agent-comms/tasks/run-team-2026-05-29-cargo-adapter.md`).
- **PM** — amends `supported-engine-matrix.md` with the cargo row at
  cycle close; tracks `cargo test --format=json` graduation in the
  matrix's "imminent watch" section.
- **Release team** — adds a Rust cell to the CI matrix when next
  touching CI workflows. Until then, the two `tests/integration/run/
  test_cargo_*.py` cases skip cleanly on Cargo-less runners.
- **`engine-adapters.md §5`** — should be amended to reflect this
  narrowed posture (text currently sketches the plain-text fallback;
  this decision binds the adapter to nextest-only). Run team is
  permitted to edit `engine-adapters.md §5` as part of this slice;
  PM reviews the diff at cycle close.

## Forward-compatible extension rules

- Adding a `cargo test --format=json` execution path (after upstream
  stabilization) is **additive** and does not require a v2 of this
  decision — it adds a fallback, does not remove nextest-primary.
- Adding plain-text `cargo test` fallback REQUIRES v2 — reverses the
  v1 decision.
- Adding a JUnit-XML alternative fallback for pre-0.9.50 nextest
  users is **additive** (extends the supported nextest floor downward)
  and does not require v2 unless it changes the nextest-primary
  semantics.

## Effective date

2026-05-29.

## Supersedes

None. First decision on the cargo adapter's execution-path posture.
The `engine-adapters.md §5` sketch was a working draft that this
decision now narrows.
