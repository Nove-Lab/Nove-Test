---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-29
slug: cargo-adapter
related:
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/history/2026-05-28-gotest-adapter-and-localization-phase4-entry.md
---

# Task: Phase 3 adapter backlog #2 — `cargo test` / `cargo-nextest` Native Engine adapter

This slice ships the **fourth native engine adapter** (after pytest,
jest, go-test). It is **dispatched in parallel** with the
Orchestration team's Localization CLI cycle — your owned files and
theirs do not intersect (`src/novetest/run/**` vs `src/novetest/cli/**`
+ `src/novetest/orchestration/**`).

The cycle mirrors the **go-test slice** (`adf7bac`, 2026-05-28) almost
line-for-line — read that diff before you start. Same pattern: detect
→ readiness → execution → coverage → normalization → fixtures. Cargo
is slightly more complex due to the dual-path consideration but the
structure is identical.

## Q3 resolution (read first)

The CEO answered Open Question #3 today: `cargo-nextest` is the
**only** execution path; no plain-text `cargo test` fallback, no
nightly `-Z unstable-options` JSON path. The decision that pins this is
`agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
— read it before starting. Notable narrowing from
`engine-adapters.md §5`: the §5 sketch implied a plain-text fallback;
the Q3 decision §3 **removes** that. Users without nextest get
`engine-misconfigured` with a clear install hint.

## Goal

Ship `src/novetest/run/adapters/cargo_adapter.py` and wire it through
`engine_selector.py` / `engine.py` / `readiness.py` / `normalizer.py`.
End-to-end goal: `novetest run` against a Cargo workspace produces a
Run Record with `engine_name="cargo-test"` and structured
`TestResult` rows, optionally with a coverage artifact registered.

## Pinned conventions (binding — do NOT diverge)

### Engine identity
- `engine_name = "cargo-test"` (NOT `"cargo"`, NOT `"nextest"`).
  Matches `_SUPPORTED_PAIRS` convention established by go-test
  (`"go-test"`) and the
  `decisions/2026-05-28-regression-outcome-envelope-shape.md`
  enum list (already lists `"cargo"` — see "Bookkeeping deviation"
  at the bottom of this brief).
- `ecosystem = "rust"`.
- `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE`: add `"rust": "cargo-test"`.

### Detection (`detect()`)
- Workspace marker: presence of `Cargo.toml` in the target's ancestor
  chain (walk up from target; stop at first match — same pattern as
  `pyproject.toml` discovery for pytest).
- A `Cargo.toml` with `[workspace]` table is a multi-crate workspace;
  treat the workspace root as the working directory for nextest.

### Readiness (`_assess_cargo_readiness`)
Three states (mirror the gotest pattern):

| Condition | State | install_hint |
|---|---|---|
| `cargo` not on PATH | `engine-missing` | `"install Rust toolchain from https://rustup.rs"` |
| `cargo` present but `cargo nextest --version` non-zero (nextest absent) | `engine-misconfigured` | `"install cargo-nextest: cargo install cargo-nextest --locked (or use cargo binstall)"` |
| `cargo nextest --version` zero, but `Cargo.toml` re-check fails | `engine-misconfigured` | `"workspace must contain a valid Cargo.toml"` |
| `cargo`, nextest, `Cargo.toml` all OK | `ready` | (none) |

**`cargo test` plain-text fallback is NOT a readiness path** —
nextest absence is `engine-misconfigured`, surfaced loudly per the Q3
decision §4. Users who want to run without nextest invoke
`cargo test` themselves; we do not silently degrade. This is a
deliberate UX call by the Q3 decision; do not soften it.

Version probes:
- `cargo --version` → extract `"1.74.0"` from
  `"cargo 1.74.0 (ecb9851af 2023-10-18)"`. Returns `None` silently on
  any failure. Stored as `engine_version`.
- `cargo nextest --version` → extract nextest version separately.
  Stash in `engine_context["nextest_version"]`.

### Execution argv

Do **not** auto-write `.config/nextest.toml` — our adapters never
modify the user's project (per the "we never modify the build file"
rule, applied across all six ecosystems). Use whatever profile the
user has configured (their CI profile if any), default otherwise.

Canonical argv:

```python
[
    "cargo", "nextest", "run",
    "--message-format=libtest-json",
    "--no-fail-fast",
    "--workspace",
    *([target_expression] if target_expression else []),
]
```

**Critical version pin**: `cargo nextest run --message-format=libtest-json`
is the **stable** JSON output path on nextest **0.9.50+** (released
2024). This is distinct from `cargo test --format=json -Z unstable-options`
(nightly Rust). Verify your dev box's `cargo nextest --version` is
>= 0.9.50; if older, document in the handoff and propose a floor.

**Fallback path (JUnit XML)**: if `libtest-json` is unavailable on the
user's nextest version, fall back to JUnit XML via `--profile=<auto>`
**only if you can do this WITHOUT mutating the user's
`.config/nextest.toml`**. This is harder than it sounds; the
engine-adapters.md §5 example writes a profile file. **My
recommendation: ship libtest-json ONLY in this slice; defer JUnit-XML
fallback to a follow-up if pre-0.9.50 nextest users surface.** Document
the floor in the handoff.

Coverage path (separate from execution):

```python
[
    "cargo", "llvm-cov", "nextest",
    "--lcov", "--output-path", str(coverage_lcov_path),
    "--no-fail-fast",
    "--workspace",
    *([target_expression] if target_expression else []),
]
```

`cargo-llvm-cov` REQUIRES the `llvm-tools-preview` rustup component.
Detect its absence as an additional `engine-misconfigured` state with
hint `"install llvm-tools-preview: rustup component add llvm-tools-preview"`.

Note: `cargo-llvm-cov` runs the tests itself (it wraps nextest); you
do NOT run nextest separately for coverage. The two paths are
mutually exclusive per invocation:
- `collect_coverage=False` → nextest only
- `collect_coverage=True` → `cargo-llvm-cov nextest` only

### Coverage artifact

- Artifact key: **`coverage_lcov`** (NEW key; distinct from go-test's
  `coverage_profile` and pytest/jest's `coverage_json`).
- Format: LCOV (universal Rust convention per `engine-adapters.md §5`).
- Path: `<artifact_dir>/native/coverage.lcov`.
- The Coverage-team follow-on slice (NOT this slice's work) parses
  `coverage_lcov` dispatched on `engine_name == "cargo-test"`.

Do NOT emit Cobertura or LLVM JSON in this slice — keep the artifact
surface small. Adding multi-format emission is a follow-up if Coverage
team needs it.

### Env vars (child subprocess)

```python
{
    "CARGO_TERM_COLOR": "never",
    "RUST_BACKTRACE": "1",
    "NO_COLOR": "1",
}
```

NO `CARGO_INCREMENTAL=0` — leave the user's incremental cache alone.
NO `RUSTFLAGS` override — would invalidate the cache.

### Node ID shape

libtest-json format emits per-test events with `name` and `binary`
fields. Construct `node_id` as:

```
<binary>::<name>
```

Where `<binary>` is the test binary path (relative to the workspace
root, e.g. `my_crate/tests/integration_test`) and `<name>` is the
test function path (e.g. `tests::test_add` for unit tests inside
the crate's `src/`).

Examples:
- Unit test in `src/lib.rs` → `<crate_name>::tests::test_add`
- Integration test in `tests/foo.rs` → `<crate_name>--foo::tests::test_x`
- Doctest → **OUT OF SCOPE** for this slice (cargo nextest doesn't run
  doctests; they require `cargo test --doc`).

If the libtest-json schema differs from this on your dev box, document
the actual shape in the handoff and follow what the engine emits
(defensive parsing — same posture as go-test for `Action: aborted`).

### Failure logs

Same pattern as go-test:
- Write per-test failure log to
  `<artifact_dir>/native/failures/<safe_node_id>.log`
- Safe filename: replace `/`, `::`, `:`, `\` with `_`.
- `failure_reference` in `TestResult` is the **relative path string**
  (e.g. `"native/failures/my_crate__tests__test_add.log"`).
- Content: combined `output` events for the failing test (libtest-json
  emits stdout/stderr as separate event streams; concatenate).

### Build failure detection

Cargo can fail to compile before any test runs. Detection:
- "Zero `start` events for tests AND non-zero exit code" → typed
  `unparseable-output` error with detail
  `"cargo build/test failed before any test ran (check stderr for compiler errors)"`.
- Capture full stderr in the artifact for diagnostics.

### Aggregate status rule

```python
if any TestResult.outcome == "failed": status = "failed"
elif returncode == 0:                  status = "passed"
else:                                  status = "errored"
```

Same rule as go-test. Skip events (`Action: skipped`) do NOT count as
failed.

### Defensive parsing

Per `decisions/2026-05-25-supported-engine-matrix.md` §2 — defensive
parsing posture:
- Malformed JSON lines → skip, do not abort.
- Unknown event types → skip silently (libtest-json may add new
  events).
- Unknown terminal outcomes → map to `outcome="unknown"` (visible, not
  silent) — same precedent as go-test's `_aggregate_gotest_status`.

## Files to touch (explicit allowlist)

**Add:**
- `src/novetest/run/adapters/cargo_adapter.py` (~250–300 lines;
  similar shape to `gotest_adapter.py`)
- `tests/unit/run/adapters/test_cargo_adapter.py`
- `tests/integration/run/test_cargo_basic.py`
- `tests/integration/run/test_cargo_coverage.py`
- `tests/fixtures/projects/cargo-test-basic/` (Cargo.toml + src/lib.rs +
  tests; 1 passing + 1 failing test minimum; see Fixtures below)
- `tests/fixtures/projects/cargo-test-basic-coverage/` (separate fixture
  with 1 covered + 1 deliberately uncovered branch)

**Edit:**
- `src/novetest/run/engine_selector.py` (add `"rust": "cargo-test"` to
  `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE`; update raise list in
  `_unimplemented_engine`)
- `src/novetest/run/engine.py` (import `run_cargo`; add fourth branch
  to `_invoke_adapter`)
- `src/novetest/run/readiness.py` (add `_assess_cargo_readiness`;
  route Cargo candidates)
- `src/novetest/run/normalizer.py` (add `_normalize_cargo_payload`;
  `_aggregate_cargo_status`)
- `tests/unit/run/conftest.py` (add `cargo_test_basic_workspace` and
  `cargo_test_basic_coverage_workspace` fixtures)
- `tests/unit/run/test_normalizer.py` (extend with Cargo cases)
- `tests/unit/run/test_readiness.py` (extend with Cargo cases)
- `tests/unit/run/test_engine_selector.py` (add Cargo workspace case)
- `tests/unit/run/test_engine.py` (extend dispatch test)

**Do NOT touch:**
- `src/novetest/cli/**`, `coverage/**`, `regression/**`,
  `localization/**`, `replay/**`, `orchestration/**`, `memory/**`
- `src/novetest/models/**` — file
  `agent-comms/questions/run-team-2026-05-29-<slug>.md` and stop if
  you find you need a model change.
- `agent-comms/decisions/**` — PM-only.
- `design/implementation-plan/engine-adapters.md` may be amended in
  this slice per the Q3 decision §"Affected files" — keep the edit
  narrow (the §5 nextest-vs-cargo-test posture section); PM reviews
  at cycle close.

## Fixtures

### `cargo-test-basic/` (5 files minimum)

```
Cargo.toml         # name = "cargo_test_basic", edition = "2021", rust-version = "1.74"
src/lib.rs         # mod tests { fn add() -> u32 ; fn test_add() }
                   # Add a deliberately failing test in a second mod (or in the same)
tests/integration_test.rs  # one integration test
README.md          # documents the intentional failure
.gitignore         # ignore target/
```

- Pin Rust edition `"2021"` (most widely supported).
- Pin `Cargo.toml` `rust-version = "1.74"` (matches `cargo-nextest` 0.9.50+
  stability baseline; verify on your dev box).
- 1 passing unit test + 1 failing unit test + 1 passing integration
  test minimum (total 3).
- Intentional failure for the failing test: deliberately wrong
  assertion (e.g. `assert_eq!(add(2, 2), 5)`); README pins the contract.

### `cargo-test-basic-coverage/` (similar, with one uncovered branch)

- Two source files in `src/` for cross-file LCOV block structure.
- One function with a clearly uncovered branch (e.g. `if x < 0 { return
  Err(...) }` where no test exercises the negative case).
- 4 passing tests minimum.
- README pins the intentional coverage gap as the fixture contract.

## Test expectations (~30 net new tests; mirror go-test slice)

### `tests/unit/run/adapters/test_cargo_adapter.py` (~16 cases)

1. Happy path: payload + artifact wiring.
2. Default workspace path (no target).
3. Target-expression pass-through.
4. Failing test writes failure log + content + safe filename.
5. Integration test in `tests/foo.rs` node_id includes binary path.
6. Build failure (compile error) stdout-empty + non-zero → typed `unparseable-output`.
7. Skip action + returncode 0 does NOT trigger build-failure detector.
8. Missing `cargo` raises `missing-binary` up-front.
9. `FileNotFoundError` from spawn → `missing-binary`.
10. Timeout maps to typed timeout error.
11. Malformed JSON line skipped defensively.
12. Coverage=False: no `cargo llvm-cov` invocation, no `coverage_lcov` artifact key.
13. Coverage=True: invokes `cargo llvm-cov nextest`, registers `coverage_lcov`.
14. Missing coverage.lcov when coverage requested → `unparseable-output`.
15. Version parsed from `cargo --version`.
16. Version `None` when probe fails.

### `tests/unit/run/test_normalizer.py` extended (~6 Cargo cases)

1. Passing-payload status + summary + node_id (lib unit test) + duration_ms.
2. Failing-payload + `failure_reference` relative-path string.
3. Integration test node_id includes binary name distinguisher.
4. Skip action maps to skipped + status passed (if returncode 0).
5. Unknown terminal action → outcome `"unknown"` per defensive parsing.
6. Returncode != 0 + no failures → `"errored"` (e.g. build script failure).

### `tests/unit/run/test_readiness.py` extended (~4 Cargo cases)

1. No `cargo` on PATH → `engine-missing` with rustup hint.
2. `cargo` present but no nextest → `engine-misconfigured` with install hint.
3. `cargo` + nextest present + `Cargo.toml` valid → `ready` + version populated.
4. `cargo --version` non-zero → `engine-misconfigured` with engine_context.

### `tests/unit/run/test_engine_selector.py` extended (1 case)

- `Cargo.toml` workspace → `NativeEngineContext("rust", "cargo-test")`.

### `tests/unit/run/test_engine.py` extended (1 case)

- `execute_with_engine_context(engine_name="cargo-test")` dispatches to `run_cargo`.

### `tests/integration/run/test_cargo_basic.py` (1 case)

- Real `cargo nextest run --message-format=libtest-json` against the
  failing fixture, asserts return code != 0, packages include the
  fixture crate, failure log written, engine_version starts with `"1."`,
  3 test results emitted (1 pass + 1 fail unit + 1 pass integration).

### `tests/integration/run/test_cargo_coverage.py` (1 case)

- Real `cargo llvm-cov nextest --lcov` against the coverage fixture,
  asserts LCOV header present, both source files represented, at
  least one branch with `count=0`.

## Worktree & branch

Branch: `novetest-cargo-adapter` (off `main` tip `f2243b8`).

## Verification gate

- `uv run pytest -q tests/unit tests/integration` — all green.
  Worktree baseline at `f2243b8`: **611 passed + 5 skipped**. Expected
  delta: **~+30 new tests**, all green.
  - Two new integration tests **skip cleanly** on a Cargo-less CI box
    (use `shutil.which("cargo")` + `pytest.skip(...)` pattern, mirror
    `test_gotest_basic.py` skip pattern).
- `uv run mypy` — clean, `--strict`, **+1 source file** (`cargo_adapter.py`).
  Source file count goes 69 → 70.
- Local smoke: run full `execute()` pipeline against the
  `cargo-test-basic` fixture. Confirm `status="failed"`,
  `summary={"passed": 2, "failed": 1, "skipped": 0, "total": 3}`,
  `engine_version` populated.

## DoD bullets believed closed

When you write your handoff, name these in the "DoD bullets believed
closed" list. PM verifies and ticks during cycle cleanup.

**No `delivery-phasing.md` `- [ ]` bullets close from this slice
alone.** Phase 3 line 150 ("all six landed by end of Phase 3") is a
narrative section header, not a checkbox. The Phase 3 adapter backlog
moves **3/6 → 4/6** (pytest + jest + go-test + cargo-test landed;
junit + dotnet remain blocked on Open Questions #4 and #5).

## Out of scope (do NOT do)

- Per-test coverage slow mode (`--per-test-coverage` slow path from
  `engine-adapters.md §5`). Rust's per-test attribution is
  prohibitively slow (N invocations); deferred to a post-MVP slice.
- Doctest execution (`cargo test --doc`). Separate path, separate
  parser, future slice.
- Race detector flag (`-Z sanitizer=thread` etc.).
- LCOV parser (Coverage team territory; this slice only registers
  the artifact).
- Cobertura emission.
- LLVM JSON emission.
- Plain-text `cargo test` fallback for non-nextest projects (Q3
  decision §3 explicitly narrows this slice to nextest-only).
- `models/` changes (none needed — `cargo-test` reuses the existing
  `TestResult` / `NativeResult` shape).
- `decisions/*.md` edits (PM-only).

## Bookkeeping deviations from prior briefs (informational)

1. **Q3 decision dependency** — this slice is conditional on
   `decisions/2026-05-29-cargo-adapter-nextest-primary.md` landing in
   `main` first. PM is writing it in the same dispatch; if you do not
   see it on your worktree base, file a question and stop.

2. **`supported-engine-matrix.md` rust row** — PM adds a `cargo`
   row in a bookkeeping commit. Propose your floor (recommend
   `cargo-nextest >= 0.9.50` AND `cargo >= 1.74`) and tested ceiling
   (whatever your dev box has) in the handoff; PM reconciles in a
   follow-up amendment.

3. **No CI Rust cell yet** — same situation as Go. The two integration
   tests skip cleanly on non-Rust CI runners. Release team adds a Rust
   cell when they next touch the CI matrix.

## Conventions reminders

- `--strict` mypy stays clean.
- `@dataclass(slots=True, frozen=True)` for any new internal types.
- `utils.asyncio_subprocess.run_subprocess` for all subprocess calls;
  do NOT call `subprocess.run` directly.
- `NativeResult.artifact_paths` values are absolute `Path` at the
  adapter layer; Memory rewrites to relative strings.
- No backwards-compat shims, no defensive programming layers beyond
  the defensive-parsing posture pinned above.
- The fixture must NOT import `novetest` (per Run team charter rule).
