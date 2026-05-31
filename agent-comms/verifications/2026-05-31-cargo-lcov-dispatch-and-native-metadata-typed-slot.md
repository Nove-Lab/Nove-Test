---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-31
slug: cargo-lcov-dispatch-and-native-metadata-typed-slot
related:
  - agent-comms/handoffs/coverage-team-2026-05-31-cargo-lcov-dispatch.md
  - agent-comms/handoffs/run-team-2026-05-31-native-result-metadata-typed-slot.md
  - agent-comms/tasks/coverage-team-2026-05-31-cargo-lcov-dispatch.md
  - agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
---

# Verification: parallel cycle — cargo Coverage LCOV dispatch + NativeResult typed metadata slot

## TL;DR

Two parallel slices landed together this cycle. Both probe the **same cargo
E2E surface**, so this verification doc covers both at once — Manual Test sets
up the cargo fixture once and exercises both surfaces from a single sweep.

- **Coverage slice** (`53f7920`): cargo runs now produce a canonical
  `CoverageFactSet` (via the new `lcov_parser.parse_lcov`). `coverage show`,
  `coverage diff`, and `inspect` now consume cargo runs like pytest/jest/go-test.
  `inspect.sub_reports.coverage` flips from `"unavailable"` to `"available"` for
  cargo runs.
- **Run slice** (`4cb5d48`): `NativeResult.metadata: dict[str, str]` is now a
  typed contract-layer slot. Normalizer overlays adapter metadata onto its
  own `native_exit_code` with a strict-raise guard for the reserved key.
  Cargo adapter migrates `payload["nextest_version"]` -> `metadata["nextest_version"]`.
  pytest / jest / gotest adapters intentionally don't populate `metadata` yet --
  none have a record-bound secondary-runner version analogous to nextest.

## Merged commits on main

| Commit | Subject |
|---|---|
| `53f7920` | feat(coverage): dispatch cargo-test LCOV through new parser |
| `4cb5d48` | refactor(run): add typed metadata slot on NativeResult; cargo migrated |

(Run team's original commit `a4d2e31` was rebased to `4cb5d48` to resolve a
WORKLOG.md text conflict -- both teams added new top-of-file entries at the
same insertion point. Resolution: Run entry above Coverage entry (Run lands
later in main's history), no source content changed during the rebase.)

## Main Branch gate evidence

- **Coverage merge -> gate** (`uv run pytest -q tests/unit tests/integration`):
  **709 passed + 5 skipped** (baseline 678+5 -> **+31** = 26 lcov_parser unit +
  4 derive cargo + 1 cargo E2E). mypy `--strict` clean, **71 source files**
  (70 baseline + 1 new `lcov_parser.py`).
- **Run merge -> gate** (same command): **712 passed + 5 skipped** (Coverage's
  709 -> +3 = 3 new metadata-overlay tests in `test_normalizer.py`). mypy
  `--strict` clean, **71 source files** (Run adds zero src files).
- **Cargo integration isolated re-run** on equipped host with `cargo 1.96.0` +
  `cargo-nextest 0.9.137` + `cargo-llvm-cov 0.8.7`:
  ```
  uv run pytest -q \
    tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py \
    tests/integration/coverage/test_cargo_lcov_e2e.py -v
  -> 3 passed in 1.23s
  ```
- **End-to-end smoke** (real `novetest init` + `novetest run --coverage`
  against `cargo-test-basic-coverage` fixture, both slices in tandem):
  ```
  ok:                              True
  has_coverage_facts:              True
  engine_name:                     cargo-test
  engine_version:                  1.96.0
  metadata:                        {'native_exit_code': 0, 'nextest_version': '0.9.137'}
  summary_counts:                  {'passed': 4, 'failed': 0, 'skipped': 0, 'total': 4}
  artifact_paths keys:             ['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']
  coverage_outcome.kind:           fact-set         <- was "unavailable" pre-Coverage-slice
  coverage_outcome.mapping_granularity: aggregate
  coverage_outcome.summary:        24/25 statements (96.0%)
  warnings:                        []
  errors:                          []
  inspect.sub_reports.coverage:    available        <- was "unavailable" pre-Coverage-slice
  ```
  (`metadata.nextest_version: '0.9.137'` is the **smoking-gun** that Run slice
  shipped -- pre-Run-slice the same path would have produced
  `metadata = {'native_exit_code': 0}` only; the secondary-runner version
  silently dropped at the normalizer seam.)

## Implementation pin-points (envelope/API path discipline)

These are the **observed** post-merge code paths Manual Test scenarios reference.
All grep-pinned against the merged tree, not the source handoff prose.

### Coverage slice

- `src/novetest/coverage/derive.py:54` -- `COVERAGE_LCOV_ARTIFACT_KEY = "coverage_lcov"`
- `src/novetest/coverage/derive.py:93` -- early dispatch:
  `if record.engine_name == "cargo-test": return _derive_cargo_lcov(store, record)`
- `src/novetest/coverage/derive.py:167` -- `_derive_cargo_lcov(store, record)`
  helper; reads `record.artifact_paths[COVERAGE_LCOV_ARTIFACT_KEY]`
- `src/novetest/coverage/lcov_parser.py` -- NEW module exposing
  `parse_lcov(lcov_path, *, run_reference, engine_name, ecosystem, workspace_root, derived_at=None) -> CoverageFactSet`
- `src/novetest/coverage/availability.py` -- `_COVERAGE_ARTIFACT_KEYS` tuple
  accepts both `coverage_json` and `coverage_lcov`

### Run slice

- `src/novetest/run/types.py:80` -- `NativeResult.metadata: dict[str, str] = field(default_factory=dict)`
- `src/novetest/run/normalizer.py:22` -- `_RESERVED_METADATA_KEYS: frozenset[str] = frozenset({"native_exit_code"})`
- `src/novetest/run/normalizer.py:79` -- reserved-key guard:
  `reserved_collisions = _RESERVED_METADATA_KEYS & native_result.metadata.keys()`
- `src/novetest/run/normalizer.py:90` -- overlay: `metadata.update(native_result.metadata)`
- `src/novetest/run/adapters/cargo_adapter.py` -- `payload["nextest_version"]`
  stash deleted; `metadata={"nextest_version": <version>}` kwarg on
  `NativeResult(...)` (conditional on probe success)

### Envelope paths Manual Test will read

| What | JSON path |
|---|---|
| Top-level OK flag | `ok` (bool) |
| Exit envelope warnings | `warnings` (list of `{code, message, details}`) |
| Run command's MemoryEntry | `data.memory_entry` |
| Run record | `data.memory_entry.run_record` |
| Run record metadata (typed slot, persisted) | `data.memory_entry.run_record.metadata` |
| Run record artifact paths | `data.memory_entry.run_record.artifact_paths` |
| Coverage outcome (run with `--coverage`) | `data.coverage_outcome` |
| Coverage outcome kind | `data.coverage_outcome.kind` (`"fact-set"` \| `"unavailable"`) |
| Coverage outcome run reference | `data.coverage_outcome.run_reference.run_id` |
| Coverage outcome mapping granularity | `data.coverage_outcome.mapping_granularity` |
| Coverage outcome summary | `data.coverage_outcome.summary` |
| Inspect sub-reports | `data.sub_reports` (`{coverage, regression, localization, replay}`) |
| Persisted run record | `.novetest/memory/runs/YYYY/MM/DD/run_<id>/record.json` |
| Persisted coverage facts | `.novetest/memory/runs/YYYY/MM/DD/run_<id>/coverage_facts.json` |

## Setup

Both slices probe the same cargo fixture. ONE setup serves both.

```bash
# Equipped host: cargo + cargo-nextest 0.9.50+ + cargo-llvm-cov
cargo --version           # -> cargo 1.96.0 (or compatible)
cargo nextest --version   # -> cargo-nextest 0.9.50+ (libtest-JSON gate)
cargo llvm-cov --version  # -> cargo-llvm-cov 0.8.0+

# Materialize a fresh workspace from the coverage fixture
SMOKE_DIR=$(mktemp -d /tmp/novetest-merge-verify-XXXX)
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic-coverage/* "$SMOKE_DIR/"
cd "$SMOKE_DIR"

# Use the system novetest from the merged tree
NOVETEST="PATH=$HOME/.cargo/bin:\$PATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest"

# Initialize store
eval "$NOVETEST init"   # -> ok=True, exit 0
```

Cleanup at end: `rm -rf $SMOKE_DIR`.

If `jq` is unavailable on the host, use `python3 -c "import json; ..."` for
JSON parsing -- every command below has a python3 alternative.

## Scenarios

### Scenario 1 -- `novetest run --coverage` proves BOTH slices in tandem

**Goal**: One command emits the Coverage slice's `fact-set` outcome AND the Run
slice's typed `metadata.nextest_version`.

```bash
cd "$SMOKE_DIR"
eval "$NOVETEST run --coverage" > run.json 2>run.stderr
echo "exit code: $?"

python3 <<'PY'
import json
d = json.load(open("run.json"))
print("ok:", d["ok"])
print("command:", d["command"])
me = d["data"]["memory_entry"]
print("has_coverage_facts:", me["has_coverage_facts"])
rr = me["run_record"]
print("engine_name:", rr["engine_name"])
print("engine_version:", rr["engine_version"])
print("metadata:", rr["metadata"])
print("artifact_paths keys:", sorted(rr["artifact_paths"].keys()))
co = d["data"]["coverage_outcome"]
print("coverage_outcome.kind:", co["kind"])
print("coverage_outcome.mapping_granularity:", co["mapping_granularity"])
print("coverage_outcome.summary:", co["summary"])
print("warnings:", d["warnings"])
print("errors:", d["errors"])
print("RUN_ID:", co["run_reference"]["run_id"])
PY
```

**Expected** (load-bearing assertions):

- exit code: `0`
- `ok: True`
- `engine_name: cargo-test`
- `engine_version: 1.96.0` (host-dependent string)
- `metadata: {'native_exit_code': 0, 'nextest_version': '0.9.137'}` <- **Run slice proof**
  - `native_exit_code` always present (normalizer-owned)
  - `nextest_version` present when version probe succeeded
  - Pre-Run-slice: `metadata = {'native_exit_code': 0}` only (the secondary-runner
    version was lost at the normalizer seam)
- `artifact_paths` includes both `coverage_lcov` (new artifact key, Coverage slice
  consumes it) and `cargo_events_jsonl` (existing)
- `coverage_outcome.kind: "fact-set"` <- **Coverage slice proof**
  - Pre-Coverage-slice: `coverage_outcome.kind: "unavailable"` with
    `reason: "missing-native-payload"` (the JSON-only `derive_coverage_facts`
    didn't recognize `engine_name == "cargo-test"`)
- `coverage_outcome.mapping_granularity: "aggregate"` (cargo-llvm-cov merges
  across all tests; per-test attribution is post-MVP)
- `coverage_outcome.summary.percent_covered: 96.0` (24/25 statements; the 1
  missing statement is the fixture's intentionally-uncovered `"negative"`
  branch at `src/classifier.rs:13`)
- `warnings: []`
- `errors: []`

Save `$RUN_ID` from the output -- used by subsequent scenarios.

### Scenario 2 -- `novetest coverage show <run_id>` proves Coverage envelope projection

```bash
RUN_ID="<paste from Scenario 1>"
eval "$NOVETEST coverage show $RUN_ID" > cov.json
echo "exit code: $?"

python3 <<PY
import json
d = json.load(open("cov.json"))
co = d["data"]["coverage_outcome"]
print("kind:", co["kind"])
print("mapping_granularity:", co["mapping_granularity"])
print("summary:", json.dumps(co["summary"], indent=2, sort_keys=True))
print("run_reference.run_id matches:", co["run_reference"]["run_id"] == "$RUN_ID")
PY
```

**Expected**:

- exit code: `0`
- `kind: "fact-set"`
- `mapping_granularity: "aggregate"`
- `summary.percent_covered: 96.0`
- `run_reference.run_id` matches the run ID

### Scenario 3 -- `novetest inspect <run_id>` proves `sub_reports.coverage: "available"`

```bash
eval "$NOVETEST inspect $RUN_ID" > inspect.json
python3 <<'PY'
import json
d = json.load(open("inspect.json"))
print("sub_reports:", json.dumps(d["data"]["sub_reports"], indent=2, sort_keys=True))
PY
```

**Expected**:

```json
{
  "coverage": "available",
  "localization": "unavailable",
  "regression": "unavailable",
  "replay": "unavailable"
}
```

`coverage: "available"` is the **load-bearing assertion** -- was `"unavailable"`
for all cargo runs pre-Coverage-slice.

### Scenario 4 -- Persisted record.json proves Run typed-slot survives serialization

```bash
python3 <<'PY'
import glob, json
rec = sorted(glob.glob(".novetest/memory/runs/**/record.json", recursive=True))[-1]
d = json.load(open(rec))
print("path:", rec)
print("engine_name:", d["engine_name"])
print("engine_version:", d["engine_version"])
print("metadata:", json.dumps(d["metadata"], sort_keys=True))
print("artifact_paths keys:", sorted(d["artifact_paths"].keys()))
PY
```

**Expected**:

- `engine_name: "cargo-test"`
- `engine_version: "1.96.0"`
- `metadata: {"native_exit_code": 0, "nextest_version": "0.9.137"}`
- `artifact_paths` includes `coverage_lcov`

### Scenario 5 -- Persisted coverage_facts.json proves LCOV parser landed

```bash
python3 <<'PY'
import glob, json
cf = sorted(glob.glob(".novetest/memory/runs/**/coverage_facts.json", recursive=True))[-1]
d = json.load(open(cf))
print("path:", cf)
print("engine_name:", d["engine_name"])
print("ecosystem:", d["ecosystem"])
print("mapping_granularity:", d["mapping_granularity"])
print("metadata:", json.dumps(d["metadata"], sort_keys=True))
print()
print("files:")
for f in d["files"]:
    cov = len(f["executed_lines"])
    tot = cov + len(f["missing_lines"])
    print(f"  {f['path']:30s}  cov={cov}/{tot}  missing_lines={f['missing_lines']}")
PY
```

**Expected**:

- `engine_name: "cargo-test"`
- `ecosystem: "rust"`
- `mapping_granularity: "aggregate"`
- `metadata: {"branch_arc_semantics": "lcov-line-index", "coverage_format": "lcov"}`
  - `coverage_format: "lcov"` is the producer identifier (mirrors istanbul's
    `coverage_format: "istanbul"`)
  - `branch_arc_semantics: "lcov-line-index"` pins the BRDA-semantic deviation
    (LCOV's branch tuples are `(line, branch_index)` not `(from_line, to_line)`)
- `files`: 3 entries, all workspace-relative POSIX:
  - `src/arithmetic.rs` 6/6 missing_lines=`[]`
  - `src/classifier.rs` 6/7 missing_lines=`[13]` <- the intentionally-uncovered `"negative"` branch
  - `src/lib.rs` 12/12 missing_lines=`[]`
- No `lcov_warnings` key in metadata (all paths inside workspace root --
  the key is conditional, absent when no warnings fired)

### Scenario 6 -- `novetest coverage diff` against two cargo runs

Coverage handoff Open Q4 flagged this as not exercised in its own E2E. Manual
Test can probe end-to-end here.

```bash
# First run already captured (Scenario 1). Run again to get a second cargo run.
eval "$NOVETEST run --coverage" > run2.json
RUN_ID_2=$(python3 -c "import json; print(json.load(open('run2.json'))['data']['coverage_outcome']['run_reference']['run_id'])")
echo "RUN_ID_2=$RUN_ID_2"

eval "$NOVETEST coverage diff $RUN_ID $RUN_ID_2" > diff.json
echo "exit code: $?"

python3 <<PY
import json
d = json.load(open("diff.json"))
print("ok:", d["ok"])
print("command:", d["command"])
print("data keys:", sorted(d["data"].keys()))
PY
```

**Expected**:

- exit code: `0`
- `ok: True`
- `command: "coverage.diff"` (or similar -- pin exact key from observed output)
- The two runs produce identical coverage (same fixture, same tests, same
  source), so the diff should report no per-file deltas; structure is the
  load-bearing assertion, not the content.

If the diff fails or the envelope shape is unexpected, that's a real finding --
Coverage's `compare_coverage_facts` is engine-agnostic in implementation but
this is the first time it consumes two cargo `CoverageFactSet`s end-to-end.

### Scenario 7 -- `novetest run` WITHOUT `--coverage` (typed-slot regression check)

Proves the Run slice's typed-slot landed on the **no-coverage** path too.

```bash
SMOKE_DIR_2=$(mktemp -d /tmp/novetest-merge-verify-no-cov-XXXX)
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic/* "$SMOKE_DIR_2/"
cd "$SMOKE_DIR_2"
eval "$NOVETEST init"
eval "$NOVETEST run" > run.json 2>run.stderr
echo "exit code: $?"

python3 <<'PY'
import json
d = json.load(open("run.json"))
rr = d["data"]["memory_entry"]["run_record"]
print("status:", rr["status"])
print("summary_counts:", rr["summary_counts"])
print("metadata:", rr["metadata"])
print("artifact_paths keys:", sorted(rr["artifact_paths"].keys()))
print("coverage_outcome:", d["data"].get("coverage_outcome", "not in envelope"))
PY

cd /tmp && rm -rf "$SMOKE_DIR_2"
```

**Expected**:

- exit code: `3` (`cargo-test-basic` has 1 by-design failing test; exit 3 is
  the correct envelope code for "test failures detected")
- `status: "failed"`
- `summary_counts: {'failed': 1, 'passed': 2, 'skipped': 0, 'total': 3}`
- `metadata: {'native_exit_code': 100, 'nextest_version': '0.9.137'}`
  - `native_exit_code: 100` = libtest's "1+ tests failed"
  - `nextest_version` typed-slot persists on non-coverage path too
- `artifact_paths` has `cargo_events_jsonl`, `stderr`, `stdout` (NO `coverage_lcov`
  -- not requested)
- `coverage_outcome` is absent from the envelope (or present but `unavailable`
  with `reason: missing-native-payload` -- verify which)

### Scenario 8 -- Non-cargo engine regression check (pytest, jest, go-test)

Both slices' code paths short-circuit for non-cargo engines. Verify that pytest
/ jest / go-test runs are unaffected.

Use any pre-existing fixture under `tests/fixtures/projects/` that isn't a
cargo fixture (e.g. `pytest-discoverable`, `jest-basic`, `gotest-basic`).

```bash
SMOKE_PY=$(mktemp -d /tmp/novetest-merge-verify-pytest-XXXX)
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-discoverable/* "$SMOKE_PY/"
cd "$SMOKE_PY"
eval "$NOVETEST init"
eval "$NOVETEST run --coverage" > run.json
python3 <<'PY'
import json
d = json.load(open("run.json"))
rr = d["data"]["memory_entry"]["run_record"]
print("engine_name:", rr["engine_name"])
print("metadata:", rr["metadata"])
co = d["data"].get("coverage_outcome", {})
print("coverage_outcome.kind:", co.get("kind"))
PY
cd /tmp && rm -rf "$SMOKE_PY"
```

**Expected**:

- `engine_name: "pytest"` (or jest / go-test, depending on fixture)
- `metadata: {"native_exit_code": <int>}` -- ONLY `native_exit_code`. The
  pytest / jest / gotest adapters do not populate `metadata` (no record-bound
  secondary-runner version to stash). This is the regression-pinning shape
  for the 3 non-cargo adapters.
- `coverage_outcome.kind: "fact-set"` (existing JSON-path flow unchanged)

## Critical edge cases worth probing

### Edge case 1 -- `metadata.native_exit_code` reserved-key guard

The Run slice's normalizer raises `ValueError` if any adapter tries to pre-populate
`metadata["native_exit_code"]` (the normalizer owns that key). Unit-tested at
`tests/unit/run/test_normalizer.py` (`test_metadata_overlay_rejects_reserved_native_exit_code_key`).
Manual Test is unlikely to trigger this without contriving an adapter -- covered
by unit tests; out of scope for E2E probing.

### Edge case 2 -- Coverage availability probe accepts both artifact keys

The Coverage slice's `_COVERAGE_ARTIFACT_KEYS` tuple accepts EITHER `coverage_json`
(pytest/jest/gotest) OR `coverage_lcov` (cargo). `check_coverage_availability` returns
`native_payload_present=True` for both. Manual Test does not need to probe this
directly -- Scenarios 1/3 cover the cargo case end-to-end, Scenario 8 covers
the non-cargo case.

### Edge case 3 -- LCOV path-outside-workspace handling

The LCOV parser preserves absolute paths AND surfaces
`metadata["lcov_warnings"]` when a path is outside `workspace_root` (e.g.
cargo build-script generated code under `target/...`). The `cargo-test-basic-coverage`
fixture's three files are all under `src/`, so `lcov_warnings` is absent
(Scenario 5's expected). If Manual Test wants to probe the warning path, a
contrived fixture would be needed -- out of scope; unit-tested in
`tests/unit/coverage/test_lcov_parser.py`.

### Edge case 4 -- BRDA-branch handling (LCOV-line-index semantic)

cargo-llvm-cov's default output OMITS BRDA records. The fixture exercises the
BRDA-ABSENT path (Scenario 5's `summary.num_branches: 0`). The BRDA-PRESENT
path is future-proofing for a hypothetical cargo-llvm-cov upgrade that starts
emitting BRDA; unit-tested in isolation in `test_lcov_parser.py`. If Manual
Test sees `num_branches > 0` on the smoke fixture, cargo-llvm-cov upgraded its
default -- that's a real finding worth flagging.

### Edge case 5 -- Cache round-trip on second `coverage show`

`get_coverage_facts` reads the persisted `coverage_facts.json` on cache hit
(no re-derivation). After Scenario 2, a second `novetest coverage show
$RUN_ID` should produce the IDENTICAL envelope (same `summary`, same file
list, same `metadata`). Optional sanity check:

```bash
eval "$NOVETEST coverage show $RUN_ID" > cov2.json
diff <(python3 -c "import json,sys; print(json.dumps(json.load(open('cov.json')), sort_keys=True, indent=2))") \
     <(python3 -c "import json,sys; print(json.dumps(json.load(open('cov2.json')), sort_keys=True, indent=2))")
# -> empty diff (envelope identical)
```

### Edge case 6 -- `metadata` empty `dict` not the same as missing key

Run slice persisted `record.json.metadata` is ALWAYS at least
`{"native_exit_code": <int>}` (the normalizer-owned key). No `record.json`
should have `metadata: {}` or absent -- the normalizer always writes at least
the exit code. If you see `metadata: {}` or no `metadata` field, that's a
real finding.

## Trigger-(b) closure context

The cargo adapter slate from the 2026-05-30 sweep is now **fully resolved**:

- **Issue 1** (env-var hotfix) -- closed by `1e736cc` in the previous cycle.
  Trigger-(b) of `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  §3 closed by `5a6f4fe`.
- **Issue 2** (`nextest_version` payload-stash) -- closed by this cycle's
  Run slice (`4cb5d48`).
- **Cargo-Coverage carry-forward** (post-2026-05-31 `inspect.sub_reports.coverage`
  flip) -- closed by this cycle's Coverage slice (`53f7920`).

After Manual Test confirms Scenarios 1-8 + Edge cases 1-6 are green, the
cargo-adapter slate is **closed**. The natural next step for PM after Manual
Test findings is to dispatch the post-MVP backlog (Phase 4 SBFL aggregate
mode, JUnit/dotnet adapters per Q4/Q5).

## Notes from the merge for Manual Test

1. **WORKLOG.md conflict resolved by Main Branch surgically.** Both teams added
   top-of-file entries at the same insertion point. Resolution: Run entry above
   Coverage entry (Run lands later in main's history -> most-recent-on-top
   convention). Both source-code commits were FF-merged; the WORKLOG entries
   are byte-for-byte preserved from each team's worktree (the only change was
   the section ORDER). No source code was edited during conflict resolution.
2. **Run team's commit hash changed during rebase**: `a4d2e31` -> `4cb5d48`.
   This is the rebase resolving the WORKLOG.md text conflict -- the source-file
   diff is identical between the two commit hashes. Refer to `4cb5d48` going
   forward; `a4d2e31` no longer exists on main.
3. **Both slices were dispatched as a parallel cycle** by PM (same date, same
   base `4a39c92`, sibling cross-references in both handoffs noting "zero
   file overlap"). The handoffs predicted no merge conflict -- that prediction
   held for the SOURCE files (zero overlap in `src/` and `tests/`). The
   WORKLOG.md conflict was the only conflict, and the entries were complementary.
4. **Equipped host required**: All cargo scenarios skip cleanly on Rust-less
   hosts but are no-op there. The merged tip's full gate was validated on a
   Rust-equipped host (cargo 1.96.0 + cargo-nextest 0.9.137 + cargo-llvm-cov
   0.8.7) so 712+5 reflects the cargo integration tests RUNNING, not skipping.
