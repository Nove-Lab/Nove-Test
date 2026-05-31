---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-31
slug: cargo-lcov-dispatch
related:
  - agent-comms/tasks/coverage-team-2026-05-31-cargo-lcov-dispatch.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
worktree: /home/yjshin/dev/novetest-coverage-cargo-lcov-dispatch
branch: coverage-cargo-lcov-dispatch
base: main @ 4a39c92
---

# Handoff: Coverage engine — cargo LCOV dispatch

Slice closes the post-2026-05-31 carry-forward: cargo runs participate
in `coverage show` / `coverage diff` / `inspect` like the pytest / jest
/ go-test ecosystems. Output shape is identical — downstream consumers
need **zero changes**.

## Worktree

- Path: `/home/yjshin/dev/novetest-coverage-cargo-lcov-dispatch`
- Branch: `coverage-cargo-lcov-dispatch`
- Base: `main @ 4a39c92` (PM's task-dispatch commit, after the
  2026-05-31 cargo env-var hotfix `5a6f4fe`)

## Files

### New

- `src/novetest/coverage/lcov_parser.py` — `parse_lcov(...)`; LCOV →
  `CoverageFactSet`. ~360 lines including the long format-primer
  docstring.
- `tests/unit/coverage/test_lcov_parser.py` — 26 unit cases.
- `tests/integration/coverage/test_cargo_lcov_e2e.py` — 1 real-cargo
  E2E case (skips on Rust-less hosts).
- `agent-comms/handoffs/coverage-team-2026-05-31-cargo-lcov-dispatch.md`
  — this file.

### Edited

- `src/novetest/coverage/derive.py` — added early dispatch
  `if record.engine_name == "cargo-test": return _derive_cargo_lcov(...)`,
  the helper, and `COVERAGE_LCOV_ARTIFACT_KEY = "coverage_lcov"`.
- `src/novetest/coverage/availability.py` — `_COVERAGE_ARTIFACT_KEYS`
  tuple of two keys; the `native_payload_present` probe accepts either.
- `tests/unit/coverage/test_derive.py` — +4 cargo dispatch cases.
- `WORKLOG.md` — top-most entry under `## 2026-05-31 — phase3 /
  cargo-lcov-dispatch`.

### Untouched (per brief "out of scope")

- `pyproject.toml` (Run/Release territory)
- `.github/workflows/**` (separate companion Release task — see
  Open questions §1)
- `tests/integration/run/test_cargo_coverage.py` (adapter-level
  LCOV-emission test, different concern)
- `tests/fixtures/projects/cargo-test-basic-coverage/` (fixture
  reused verbatim)
- `src/novetest/run/**`, `src/novetest/models/**`,
  `src/novetest/memory/**` (other teams' territory; Memory's
  `has_coverage_facts` auto-flip works without any change because the
  flag probes `coverage_facts.json` file existence, not the artifact
  key)

## Pytest / mypy

- `uv run pytest -q tests/unit tests/integration` (on equipped host):
  **709 passed + 5 skipped in 28.47s**
  — baseline at `4a39c92` was **678 + 5** on equipped host → **+31 net
    = +31 new** (26 lcov_parser unit + 4 derive cargo + 1 cargo E2E,
    no regressions).
- `uv run mypy`: **clean, --strict, 71 source files** (70 baseline +
  1 new `lcov_parser.py`).
- Test breakdown:
  - `tests/unit/coverage/test_lcov_parser.py`: 26 cases (10 from brief
    §5 + 16 defensive — see Parser scope decisions below).
  - `tests/unit/coverage/test_derive.py`: +4 (1 happy-path dispatch,
    1 missing-`coverage_lcov`-key, 1 missing-LCOV-file, 1 malformed-LCOV).
  - `tests/integration/coverage/test_cargo_lcov_e2e.py`: 1 case;
    RUNS AND PASSES on equipped dev host. Skips cleanly on Rust-less
    runners (mirrors the existing
    `tests/integration/run/test_cargo_coverage.py:32-47` guard).

## DoD bullets believed closed

The task brief's DoD checklist (§DoD lines 332-356) — all believed
closed:

- [x] `src/novetest/coverage/lcov_parser.py` exists; `parse_lcov`
      converts LCOV file → `CoverageFactSet` with
      `mapping_granularity == "aggregate"`.
- [x] LCOV records handled: `SF`, `DA`, `LF`, `LH`, `end_of_record`,
      and `BRDA`/`BRF`/`BRH` when present. Ignored records (`TN`,
      `FN`, `FNDA`, `FNF`, `FNH`) pass through silently; unknown
      `KEY:value` records skipped silently for forward-compat.
- [x] File path normalization absolute → project-relative (paths
      outside workspace_root preserved as absolute + warning emitted
      in `metadata["lcov_warnings"]` per brief §4).
- [x] `derive.py:113-127` dispatch extended for
      `engine_name == "cargo-test"` (implemented as an early-branch
      helper, see Parser scope decisions §2).
- [x] `availability.py:89` recognizes `coverage_lcov` artifact key
      alongside `coverage_json` (via `_COVERAGE_ARTIFACT_KEYS` tuple).
- [x] **26** unit tests for `parse_lcov` (brief asked for 10; the
      extras are defensive — see Parser scope decisions §4).
- [x] **4** dispatch tests added to `test_derive.py` (brief asked
      for 2; the extras pin missing-file and malformed-LCOV paths
      that are symmetric to the existing JSON-path tests).
- [x] 1 integration test in
      `tests/integration/coverage/test_cargo_lcov_e2e.py` covering
      `init → run --coverage → coverage show → inspect`.
- [x] Pre-flight smoke-test E2E green on the equipped dev host
      (evidence below).
- [x] `mypy --strict` clean.
- [x] Full pytest suite green (baseline + new, no regressions).
- [x] No `tests/integration/run/test_cargo_coverage.py` modification.

**`delivery-phasing.md` implications**: per task brief Handoff §4,
this slice closes a **CARRY-FORWARD**, NOT a numbered DoD bullet.
Phase 2's "Engine adapter coverage" mentions cargo as a Phase 3
implicit-extension rather than a tracked checkbox. The carry-forward
closes silently — cargo participates in `coverage show` / `coverage
diff` / `inspect` after this slice.

## Pre-flight smoke-test evidence

Per Pre-flight §5 (mandatory), executed end-to-end on the equipped
dev host with `cargo 1.96.0` + `cargo-nextest 0.9.137` +
`cargo-llvm-cov 0.8.7`.

### Step 1 — fixture copy + `novetest init`

```
cp -r tests/fixtures/projects/cargo-test-basic-coverage /tmp/cargo-cov-smoke
cd /tmp/cargo-cov-smoke
novetest init
→ {store_state: "ready", store_path: "/tmp/cargo-cov-smoke/.novetest"} exit 0
```

### Step 2 — `novetest run --coverage`

```
novetest run --coverage
→ run_id: 01KSYQMYGMHCC7JE3E3JE3G428
→ coverage_outcome: {kind: "fact-set", mapping_granularity: "aggregate"}
→ memory_entry.has_coverage_facts: true
→ 4 tests passed (test_add, test_subtract, test_classify_positive, test_classify_zero)
→ exit 0
```

(Pre-this-slice baseline behavior would have been `coverage_outcome:
{kind: "unavailable", reason: "missing-native-payload"}` because
`derive_coverage_facts` did not recognize `engine_name == "cargo-test"`.)

### Step 3 — `novetest coverage show` (the proof envelope)

```json
{
  "command": "coverage.show",
  "data": {
    "coverage_outcome": {
      "kind": "fact-set",
      "mapping_granularity": "aggregate",
      "run_reference": {
        "created_at": 1780221639188,
        "run_id": "01KSYQMYGMHCC7JE3E3JE3G428",
        "schema_version": 1
      },
      "summary": {
        "covered_branches": 0,
        "covered_statements": 24,
        "excluded_statements": 0,
        "missing_branches": 0,
        "missing_statements": 1,
        "num_branches": 0,
        "num_statements": 25,
        "percent_covered": 96.0
      }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

### Step 4 — `novetest inspect`

```
novetest inspect 01KSYQMYGMHCC7JE3E3JE3G428
→ sub_reports: {
    coverage: "available",      ← was "unavailable" pre-this-slice
    regression: "available",    ← incidental: single-run baseline
    localization: "unavailable",
    replay: "unavailable"
  }
→ ok: true, exit 0
```

### Step 5 — persisted `coverage_facts.json` inspection

```
engine_name: "cargo-test"
ecosystem: "rust"
mapping_granularity: "aggregate"
metadata: {coverage_format: "lcov", branch_arc_semantics: "lcov-line-index"}
files:
  src/arithmetic.rs  cov=6/6   missing_lines=[]
  src/classifier.rs  cov=6/7   missing_lines=[13]   ← intentionally-uncovered "negative" branch
  src/lib.rs         cov=12/12 missing_lines=[]
```

The missing line 13 in `classifier.rs` is exactly the
`"negative"` literal — see
`tests/fixtures/projects/cargo-test-basic-coverage/src/classifier.rs:13`
and the fixture's README pin. No `lcov_warnings` key (all paths
under workspace root).

Smoke directory cleaned up afterward (`rm -rf /tmp/cargo-cov-smoke`).

## Parser scope decisions

### 1. BRDA parsing IS implemented (future-proofing)

Manual Test's 2026-05-31 sweep observed cargo-llvm-cov emitting only
`SF`/`DA`/`LF`/`LH` (no `BRDA`) by default. The parser nevertheless
implements BRDA → `executed_branches` / `missing_branches`
end-to-end because (a) the brief §1 explicitly requested it ("if
BRDA records appear in the test LCOV, parse them"), (b) it's
cheap once the SF-block walker is in place, and (c) it future-proofs
against a cargo-llvm-cov upgrade that starts emitting BRDA by default.

**SEMANTIC DEVIATION**: the model's `FileCoverage.executed_branches`
is documented as `(from_line, to_line)` per coverage.py. LCOV's
`BRDA:<line>,<block>,<branch>,<hits>` has no destination line — the
parser emits `(line, branch_index)` pairs. The deviation is pinned
in `metadata["branch_arc_semantics"] = "lcov-line-index"` for
downstream debuggers. `compare_coverage_facts` does set-equality
on branch tuples so the mixed semantic does not break deltas; any
future tool that PARSES the second integer as a line number for a
cargo run would silently misinterpret. PM should consider whether
this warrants either (a) a model-level discriminator field on
`FileCoverage` or (b) a normalization pass in `compare`.

The smoke fixture exercises the BRDA-ABSENT path (cargo-llvm-cov's
default); BRDA-PRESENT is unit-tested with inline LCOV.

### 2. `LcovParseError` REUSES `CoverageJsonParseError`

The brief left this to discretion ("team's call on whether to add
`LcovParseError` or reuse the existing parse-error type"). Chose
**reuse**:

- Keeps `derive.py`'s engine dispatch uniform: one `try` /
  `except CoverageJsonParseError` block per branch maps cleanly to
  `CoverageUnavailable(REASON_NATIVE_PAYLOAD_CORRUPT)`.
- Avoids a new exception class for what is fundamentally the same
  semantic ("the native payload doesn't match its documented shape").
- The exception name is slightly inaccurate ("Json" for an LCOV
  file) — acceptable tradeoff. A rename to
  `NativePayloadParseError` would be a separate cosmetic slice
  affecting `parser.py` / `istanbul_parser.py` / `lcov_parser.py`
  together; out of scope for this slice.

### 3. Dispatch implemented as EARLY BRANCH, not 3-way `if/elif/else`

The brief sketched a 3-branch dispatch in `derive.py:113-127`
(`if jest / elif cargo-test / else`), but that would require the
artifact-key lookup at `derive.py:67` (`COVERAGE_JSON_ARTIFACT_KEY`)
to also become engine-aware. Cleaner refactor: hoist the cargo
case ABOVE the JSON-only logic — `_derive_cargo_lcov(store, record)`
helper returns early, the existing JSON path keeps its single
artifact-key assumption intact. Net: 1 new helper + 1 new constant
in `derive.py`; the existing JSON-path tests pass unchanged.

If a 3rd non-JSON ecosystem lands (Java JaCoCo XML? .NET cobertura?),
the pattern repeats — another `_derive_*` early-branch helper.
Generalizing to a table-driven dispatch would be more code than the
two-line-per-engine pattern saves.

### 4. 26 unit tests (brief asked for 10)

The brief's 10 required cases (§5) are all present and named
self-evidently. The +16 defensive cases cover:

- Whitespace-only file rejection (analog to empty-file rejection)
- 3 dangling-block error variants (`end_of_record` alone, nested
  `SF:`, trailing unclosed block)
- LF / LH / BRF / BRH cross-check disagreement quartet
- BRDA duplicate-triple aggregation (covers cargo-llvm-cov's
  observed per-instantiation duplicate behavior for generics)
- BRDA wrong-field-count + non-integer-field rejection
- DA non-integer line rejection
- Unknown `KEY:value` record forward-compat (skip silently)
- Blank-line + `#`-comment tolerance
- Ignored-records (`TN`, `FN`, `FNDA`, `FNF`, `FNH`) leave no
  trace in `to_dict()` output
- Inside-only paths OMIT the `lcov_warnings` metadata key (the
  warnings tracker is conditional — absent when nothing to warn)
- `metadata["coverage_format"] == "lcov"` marker assertion
- Frozen-schema round-trip (`to_dict` → `from_dict` is identity)

### 5. `metadata` adds 2 NEW keys not present in pytest/jest paths

- `coverage_format: "lcov"` — producer identifier (mirrors
  istanbul's `coverage_format: "istanbul"`).
- `branch_arc_semantics: "lcov-line-index"` — pins the BRDA
  semantic deviation (see §1 above).
- `lcov_warnings: [str, ...]` — only present when at least one
  warning fired (outside-workspace path); omitted otherwise.

The on-disk `coverage_facts.json` schema is unchanged
(`metadata: dict[str, Any]` is open-ended in the model).

## Open questions for PM

### 1. CI lane for `tests/integration/coverage/test_cargo_lcov_e2e.py`

The new E2E test follows the same skip-on-Rust-less-host pattern as
the existing `tests/integration/run/test_cargo_coverage.py`. On
current CI runners (no Rust cell yet) both tests skip cleanly. When
the Release team adds a Rust cell to the CI matrix (queued per
`decisions/2026-05-29-cargo-adapter-nextest-primary.md` §"What this
implies for the supported-engine-matrix"), the cargo Coverage E2E
becomes a real gate alongside the basic-cargo + cargo-coverage
adapter tests. **Out of scope for this slice** — separate Release task.

### 2. `branch_arc_semantics` discriminator placement

Currently a `metadata` key. Two alternative placements PM should
weigh at MVP-time:

- **Model-level discriminator**: add `branch_arc_semantics:
  Literal["coverage-py-from-to", "lcov-line-index", "istanbul-omitted"]`
  to `FileCoverage` or `CoverageFactSet`. Promotes the
  format-disambiguation key from "metadata convention" to "frozen
  schema field". Costs a `models/` migration.

- **Compare-pipeline normalization**: `compare_coverage_facts`
  could normalize branch tuples to a canonical shape before
  deltas. Costs a perf pass on the 50k-location NFR-COV-002 path.

Today's `metadata` approach is forward-compatible with both. PM
may want to decide before the post-MVP `sbfl_aggregate` slice
lands, since SBFL consumes branch sets too.

### 3. Outside-workspace path handling: deviation from istanbul

The brief mandated "keep the absolute path AND emit a warning" for
paths outside `workspace_root` (§4). This DEVIATES from istanbul's
established `../`-prefixed relpath precedent (decision 2026-05-15
#6 + `istanbul_parser._workspace_relative`). Implemented per brief;
documented in the parser docstring with rationale. If PM wants
the two paths harmonized (either way), that's a follow-up slice
touching both parsers + decision 2026-05-15 amendment.

### 4. `coverage diff` for two cargo runs

Not exercised in this slice's E2E (the brief's flow tests `coverage
show` + `inspect` only). `compare_coverage_facts` is engine-agnostic
in implementation — it operates on `CoverageFactSet.files` set
equality — so two cargo runs should diff correctly. Manual Test may
want to probe this end-to-end during their follow-up sweep. (The
existing pytest/jest `compare` unit tests in
`tests/unit/coverage/test_compare.py` cover the algorithm; a real
two-cargo-run diff would be a Manual Test artifact, not a unit test.)

### 5. Per-test cargo Coverage (post-MVP)

Documented post-MVP path per `engine-adapters.md §5:363`
("Per-test mode = per-test invocations, opt-in slow mode —
out-of-scope for v1, deferred to a post-MVP slice"). When that
slice lands, it'll add a new `mapping_granularity` flow to the
cargo branch — likely a new artifact key or a `metadata`
discriminator on the `coverage_lcov` artifact. This slice's
`_derive_cargo_lcov` would need a per-test sub-branch; the
existing `parse_lcov` would remain the aggregate-mode entry.

## Cross-references

- Task brief:
  `agent-comms/tasks/coverage-team-2026-05-31-cargo-lcov-dispatch.md`
- Cargo adapter (registers `coverage_lcov` artifact, untouched):
  `src/novetest/run/adapters/cargo_adapter.py:311`
- Coverage facts JSON layout decision:
  `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`
- Cargo adapter execution-path posture:
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
- Trigger-(b) closure context (proves cargo adapter is reliable):
  `agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`
- Parallel-cycle sibling slice (Run typed-slot, zero file overlap):
  `agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`
