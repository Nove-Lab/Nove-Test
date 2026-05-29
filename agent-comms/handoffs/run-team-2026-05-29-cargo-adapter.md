---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-29
slug: cargo-adapter
related:
  - agent-comms/tasks/run-team-2026-05-29-cargo-adapter.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/history/2026-05-28-gotest-adapter-and-localization-phase4-entry.md
  - design/implementation-plan/engine-adapters.md
---

# Handoff: Phase 3 adapter backlog #2 — `cargo nextest` Native Engine adapter

## Worktree

- Path: `/home/yjshin/dev/aispace/novetest-cargo-adapter`
- Branch: `novetest-cargo-adapter`
- Base commit: `3094d1e` (one PM-comms commit ahead of the brief's quoted
  `f2243b8`; `3094d1e` only adds the task brief + Q3 decision to
  `agent-comms/`, so the src/test baseline is identical).
- Tip commit: (to be set on commit)

## Files written / modified

**Added (8 src/test + 11 fixtures):**

- `src/novetest/run/adapters/cargo_adapter.py` — `run_cargo` (~310 lines)
- `tests/unit/run/adapters/test_cargo_adapter.py` — 16 unit cases
- `tests/integration/run/test_cargo_basic.py` — 1 integration case (skips
  when `cargo` / `cargo-nextest` missing)
- `tests/integration/run/test_cargo_coverage.py` — 1 integration case
  (skips when `cargo` / `cargo-nextest` / `cargo-llvm-cov` missing)
- `tests/fixtures/projects/cargo-test-basic/` —
  `Cargo.toml`, `src/lib.rs`, `tests/integration_test.rs`, `README.md`,
  `.gitignore` (5 files)
- `tests/fixtures/projects/cargo-test-basic-coverage/` —
  `Cargo.toml`, `src/lib.rs`, `src/arithmetic.rs`, `src/classifier.rs`,
  `README.md`, `.gitignore` (6 files)

**Modified (8 files):**

- `src/novetest/run/engine_selector.py` — `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE`
  gains `"rust": "cargo-test"`; docstring updated to name cargo-test
  among shipping adapters and drop "rust" from the unimplemented list.
- `src/novetest/run/engine.py` — imports `run_cargo`; `_invoke_adapter`
  gains a fourth branch on `engine_name == "cargo-test"`.
- `src/novetest/run/readiness.py` — adds `_assess_cargo_readiness` (4
  states: missing, misconfigured-no-Cargo.toml, misconfigured-no-nextest,
  misconfigured-broken-cargo-version, ready); routes Rust candidates
  before the catch-all unimplemented branch; adds `_parse_cargo_version`.
- `src/novetest/run/normalizer.py` — dispatcher gains an
  `elif engine_name == "cargo-test"` branch; adds
  `_normalize_cargo_payload` + `_aggregate_cargo_status` +
  `_CARGO_EVENT_TO_OUTCOME` map.
- `tests/unit/run/conftest.py` — adds `cargo_test_basic_workspace` +
  `cargo_test_basic_coverage_workspace` fixtures.
- `tests/unit/run/test_normalizer.py` — extends with 7 Cargo cases
  (passing payload status + summary + node_id + duration_ms, failing
  payload + failure_reference, integration-test binary node_id, ignored
  → skipped, unknown terminal event → "unknown", returncode != 0 + no
  failures → "errored", missing events array → unparseable-output).
- `tests/unit/run/test_readiness.py` — extends with 4 Cargo cases
  (no-cargo, no-nextest, ready, failing-cargo-version).
- `tests/unit/run/test_engine_selector.py` — adds `Cargo.toml` →
  `NativeEngineContext("rust", "cargo-test")` case; updates the
  dotnet-still-unimplemented test docstring to drop "cargo-test".
- `tests/unit/run/test_engine.py` — adds `execute_with_engine_context(
  engine_name="cargo-test")` dispatch test with stubbed `run_cargo`.
- `design/implementation-plan/engine-adapters.md` §5 — narrowed per Q3
  decision (drops plain-text fallback, drops `.config/nextest.toml`
  writing, adds the "Required user-side tools" table with readiness-state
  mapping, documents LCOV-only coverage emission for v1).
- `WORKLOG.md` — new top entry for this cycle.

**Not touched (per charter forbids):** `src/novetest/models/`,
`src/novetest/coverage/`, `src/novetest/orchestration/`,
`src/novetest/cli/`, `agent-comms/decisions/**`,
`agent-comms/tasks/**`, `.github/workflows/`, `pyproject.toml`,
`design/implementation-plan/foundations.md`,
`design/implementation-plan/delivery-phasing.md`.

## Verification

### pytest

```
uv run pytest -q tests/unit tests/integration
→ 642 passed, 5 skipped in 15.15s
```

Baseline on this dev box at `3094d1e`: **613 passed + 3 skipped** (Go
1.18.1 is installed locally, so the two gotest integration tests run;
the 3 baseline skips are pre-existing Node-dependent jest integration
tests).

Delta: **+29 net new unit pass** + **+2 cargo integration skips** (no
Rust toolchain on this dev box) = **+31 collected**.

Per-file breakdown (verified via isolated run):

| File | New cases | Status |
|---|---|---|
| `tests/unit/run/adapters/test_cargo_adapter.py` | 16 | all pass |
| `tests/unit/run/test_normalizer.py` | 7 | all pass |
| `tests/unit/run/test_readiness.py` | 4 | all pass |
| `tests/unit/run/test_engine_selector.py` | 1 | passes |
| `tests/unit/run/test_engine.py` | 1 | passes |
| `tests/integration/run/test_cargo_basic.py` | 1 | skipped (no cargo) |
| `tests/integration/run/test_cargo_coverage.py` | 1 | skipped (no cargo) |
| **Total** | **31** | 29 pass + 2 skip |

The brief expected ~30 new tests; +31 lands within the target. The +1
above the brief's 30 is the extra integration-test-binary normalizer
case (`test_cargo_integration_test_node_id_distinguishes_binary`),
which I added to lock the `--`-substring convention with a unit test.

### mypy

```
uv run mypy
→ Success: no issues found in 70 source files
```

Source file count: **70** (+1 from the 69 baseline at `3094d1e`; the
new file is `src/novetest/run/adapters/cargo_adapter.py`). `--strict`
clean.

### Smoke / E2E

**No Rust toolchain on this dev box** (`cargo` / `rustc` / `rustup` /
`~/.cargo/bin` all absent), so the two new integration tests skip
cleanly via `shutil.which("cargo-nextest")` guards. End-to-end
adapter behavior was exercised via the 16 unit-test adapter cases with
stubbed `run_subprocess` covering:

- The execution-mode argv shape (`cargo nextest run
  --message-format=libtest-json --no-fail-fast --workspace`).
- The coverage-mode argv shape (`cargo llvm-cov nextest --lcov
  --output-path <...> --no-fail-fast --workspace
  --message-format=libtest-json`).
- The version probes (`cargo --version` + `cargo nextest --version`).
- Per-test failure log writing (the `::` → `__` filename safety pass).
- Build-failure detection (zero `started` events + non-zero exit).
- Coverage-mode build-failure-detector suppression (the
  `if not collect_coverage` carve-out — see Gotchas).
- LCOV-missing detection on coverage path.

## Worklog entry text (paste)

(See `WORKLOG.md` top entry — `## 2026-05-29 — phase3 / cargo-adapter`.
Pasting full text would duplicate ~150 lines of prose; refer to the
file directly.)

## DoD bullets believed closed

**None.** Per the task brief §"DoD bullets believed closed", no
`delivery-phasing.md` `- [ ]` bullets close from this slice alone —
Phase 3 line 150 ("all six landed by end of Phase 3") is a narrative
section header, not a checkbox. The Phase 3 adapter backlog moves **3/6
→ 4/6** (pytest + jest + go-test + cargo-test landed; junit + xunit
remain blocked on Open Questions #4 and #5).

## Phase progress

- **Phase 3 adapter backlog: 3/6 → 4/6** (pytest + jest + go-test +
  cargo-test landed; junit + xunit pending Open Questions #4 + #5).
- No `delivery-phasing.md` checkbox flips from this slice.

## Supported-engine-matrix proposal (for PM)

Per the Q3 decision §"What this implies for the supported-engine-matrix",
a new Rust row should be added to
`decisions/2026-05-25-supported-engine-matrix.md`. Proposed shape (PM
amends in the cycle-close bookkeeping commit):

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| `cargo` (Rust toolchain) | 1.74 | TBD (pending CI Rust cell) | matches edition 2021 + nextest 0.9.50 baseline; floor pinned by Q3 decision |
| `cargo-nextest` | 0.9.50 | TBD | floor pinned by `libtest-json --message-format` stability per Q3 decision §1 |
| `llvm-tools-preview` rustup component | — | — | required by `cargo-llvm-cov` for coverage; absence surfaces as `engine-misconfigured` via the LCOV-not-emitted check |

Tested ceiling is **UNVERIFIED on this dev box** — no Rust toolchain is
installed locally. The brief's "TBD" remains until Release adds a CI
Rust cell.

## Open items / surprises

1. **`nextest_version` lives in `payload`, not in `NativeEngineContext`.**
   The task brief said "Stash in `engine_context["nextest_version"]`",
   but `NativeEngineContext` is a frozen dataclass with only `ecosystem`
   / `engine_name` / `engine_version` slots — no extension hook. To stay
   model-clean (charter forbids `models/` changes in this slice), I
   stashed `nextest_version` in `NativeResult.payload["nextest_version"]`
   instead. Downstream consumers that need it must read from the payload.
   **PM action**: either codify this convention in a small decision (the
   adapter docstring documents it) OR amend `NativeEngineContext` with
   an optional `metadata: dict[str, str]` slot in a future `models/`
   slice for engine-specific version stashing.

2. **Coverage engine follow-on** — the Coverage engine needs an LCOV
   parser dispatched on `engine_name == "cargo-test"` to turn the
   registered `coverage_lcov` artifact into a `CoverageFactSet`. Until
   that lands, `novetest run --coverage` against a Cargo workspace
   produces a Run Record with `coverage_lcov` artifact but
   `has_coverage_facts` stays `False`. Natural next slice.

3. **Build-failure detector suppressed in coverage mode.** `cargo
   llvm-cov nextest` may consume stdout for its own internal
   bookkeeping in some versions, producing zero parseable libtest-json
   events even on successful runs. Triggering the detector
   unconditionally would produce false-positive `unparseable-output`
   errors on real test failures in coverage mode (the failing tests
   would surface as exit-nonzero + zero events). Mitigation:
   `if not collect_coverage and not saw_test_started and result.returncode != 0`.
   Real coverage failures are detected via `coverage_path.exists()`
   instead. **Manual Test should probe this**: a coverage run with
   intentionally failing tests (via the basic fixture's failing case)
   should still produce a Run Record with `status="failed"` rather than
   a typed adapter error — if it doesn't, the carve-out needs review.

4. **`--message-format=libtest-json` added to the COVERAGE path too**,
   departing from the brief's pseudo-argv that showed it only on the
   execution path. Reasoning: `cargo llvm-cov nextest` forwards nextest
   args, so requesting libtest-json preserves per-test result fidelity
   during coverage runs. If a user's cargo-llvm-cov version rejects
   this flag, the invocation would fail with a clear nextest error in
   stderr → typed `unparseable-output`. Without the flag, coverage mode
   loses ALL TestResult rows (the LCOV file would be the only output),
   which seems strictly worse. **Manual Test confirmation point**.

5. **CI matrix Rust cell** — current CI has no Rust cell. Release team
   adds a Rust cell when next touching CI workflows. Until then the two
   `tests/integration/run/test_cargo_*.py` cases skip cleanly on
   non-Rust runners (verified on this dev box).

6. **Integration test skip guard uses `shutil.which("cargo-nextest")`**,
   NOT `cargo nextest --version`. `cargo nextest` is a cargo subcommand
   exposed as `cargo-<name>` on PATH per cargo's subcommand convention,
   so `which` is correct and zero-cost. The unit tests at the readiness
   layer use the actual `cargo nextest --version` probe.

7. **Local Rust toolchain absent** — local smoke against a real cargo
   workspace was NOT performed. The 16 stubbed adapter unit tests cover
   the full subprocess seam, but Manual Test should exercise this on a
   real Rust + nextest box if available. Probe both the basic and
   coverage fixtures.

## Cycle queue (informational)

After Main Branch merges + Manual Test reports, PM's natural follow-ons:

1. **Supported-engine matrix amendment** — add the Rust row using the
   proposal above.
2. **Coverage engine LCOV parser slice** — dispatched on
   `engine_name == "cargo-test"`.
3. **`nextest_version` convention decision** — either codify
   payload-stash OR amend `NativeEngineContext`.
4. **(Eventually) CI Rust cell** — Release team.
