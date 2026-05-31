---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-05-31
slug: cargo-lcov-dispatch
related:
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - design/implementation-plan/engine-adapters.md
  - src/novetest/coverage/derive.py
  - src/novetest/coverage/availability.py
  - src/novetest/run/adapters/cargo_adapter.py
---

# Task: Coverage engine — cargo LCOV dispatch (`engine_name == "cargo-test"`)

## TL;DR

The cargo adapter (post-2026-05-31 hotfix) emits a well-formed
`coverage.lcov` artifact when invoked with `--coverage`, but the
Coverage engine does not yet know how to parse LCOV. Result today:
cargo run records have the raw LCOV file but `has_coverage_facts:
false` — so `coverage show`, `coverage diff`, and `inspect`'s
Coverage section all surface `unavailable` for cargo runs, while
they work for pytest / jest.

Add an LCOV parser module + extend the Coverage dispatch so that
`engine_name == "cargo-test"` runs produce a canonical
`CoverageFactSet` just like the other ecosystems. Output shape is
identical to pytest / jest / go-test — downstream consumers
(`coverage show`, `coverage diff`, `inspect`, future Localization
aggregate-mode) need **zero changes**. After this slice, cargo
becomes a first-class Coverage citizen.

Mapping granularity is **`"aggregate"`** for cargo v1 — per-test
attribution requires `cargo-llvm-cov --per-test-coverage` slow
mode which is post-MVP per `design/implementation-plan/engine-adapters.md`
§5 (line 363: "Per-test mode = per-test invocations, opt-in slow
mode — out-of-scope for v1 (deferred to a post-MVP slice)").

## Why this slice exists (product framing)

Nove Test claims 4-language polyglot support (Python / JS-TS / Go /
Rust). Until today the cargo adapter was "merged but broken"; that
was closed by the 2026-05-31 hotfix (trigger-(b) closure). But
Coverage is one of the 3 product pillars (Run / Coverage /
Regression), and cargo currently delivers only the first.

This slice closes the gap so cargo runs participate in:
- `novetest coverage show <run_id>` — show Coverage Facts table
- `novetest coverage diff <run_a> <run_b>` — cross-run coverage delta
- `novetest inspect <run_id>` — Coverage section populated, NOT
  "unavailable"
- Future Phase 4 §4 #2 `sbfl_aggregate` mode — needs aggregate
  coverage as input; without this slice the aggregate mode would
  not work for Rust users when it lands

Pair-slice context: parallel with
`tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`
(Issue 2 typed-slot). Zero file overlap; both teams work
independently. Both slices together complete cargo's first-class
status.

## Scope (what this slice DOES)

### 1. New LCOV parser module

**Create**: `src/novetest/coverage/lcov_parser.py`

Mirrors the existing `istanbul_parser.py` precedent (specialized
module per format). Public entry:

```python
def parse_lcov(
    lcov_path: Path,
    *,
    run_reference: RunReference,
    engine_name: str,   # "cargo-test"
    ecosystem: str,     # "rust"
    workspace_root: Path,  # for file-path normalization
) -> CoverageFactSet:
    ...
```

(Exact signature at team's discretion — match the existing
`parse_istanbul_json` / `parse_coverage_json` ergonomics. Look at
how they're called from `derive.py:113-127` and mirror.)

LCOV records the parser MUST handle:
- **`SF:<absolute_path>`** — start of source file record. Normalize
  to project-relative via `workspace_root` (see §3 below).
- **`DA:<line>,<hit_count>`** — line execution counter. `hit_count
  > 0` → executed; `hit_count == 0` → missing.
- **`LF:<total_lines>`** / **`LH:<lines_hit>`** — file-level
  summary (cross-check against per-DA counts; raise on mismatch
  for safety).
- **`end_of_record`** — close current SF block.

LCOV records the parser MAY handle (if present in
cargo-llvm-cov output):
- **`BRDA:<line>,<block>,<branch>,<hit>`** — branch coverage.
  Manual Test's 2026-05-31 sweep observed `SF: 3; DA: 25;
  end_of_record: 3` (no BRDA mentioned), so cargo-llvm-cov likely
  doesn't emit branch records by default. **Implementation
  guidance**: if BRDA records appear in the test LCOV, parse them
  into `FileCoverage.executed_branches` / `missing_branches`. If
  they don't appear, skip — set those fields to empty tuples. Do
  not fail if BRDA is absent.

LCOV records the parser SHOULD ignore (cargo-llvm-cov-specific):
- `TN:<test_name>` (test name, always blank from cargo-llvm-cov in
  aggregate mode)
- `FN:<line>,<function>` (function definition)
- `FNDA:<hit>,<function>` (function execution count)
- `FNF:<total>` / `FNH:<hit>` (function summary)
- `BRF:<total>` / `BRH:<hit>` (branch summary)

These are valid LCOV but Nove Test's `FileCoverage` model doesn't
have per-function fields. Skip them silently (do not raise).

Errors (raise `CoverageJsonParseError` or analogous —
team's call on whether to add `LcovParseError` or reuse the
existing parse-error type):
- File not found
- Empty file
- Malformed records (e.g., `DA:` without preceding `SF:`)
- LF/LH mismatch with DA counts (safety guard)

### 2. Dispatch extension

**Edit**: `src/novetest/coverage/derive.py:113-127`

Current dispatch (verbatim):
```python
if record.engine_name == "jest":
    fact_set = parse_istanbul_json(...)
else:
    fact_set = parse_coverage_json(...)
```

Extend to a 3-branch dispatch:
```python
if record.engine_name == "jest":
    fact_set = parse_istanbul_json(...)
elif record.engine_name == "cargo-test":
    fact_set = parse_lcov(
        lcov_path,                  # from artifact_paths["coverage_lcov"]
        run_reference=...,
        engine_name="cargo-test",
        ecosystem="rust",
        workspace_root=...,
    )
else:
    fact_set = parse_coverage_json(...)
```

The artifact key for cargo is `"coverage_lcov"` (NOT the existing
`COVERAGE_JSON_ARTIFACT_KEY = "coverage_json"`). Resolve via
`record.artifact_paths.get("coverage_lcov")`.

`workspace_root` source: the Run Record's workspace root. If the
RunRecord doesn't have a direct field, derive from
`record.artifact_paths` parent traversal OR from
`ProjectStore.path.parent` (the `.novetest/` directory's parent
IS the workspace root). Pick the cleanest path; document the
choice in the parser's docstring.

### 3. Availability check extension

**Edit**: `src/novetest/coverage/availability.py:89` (the line that
currently only checks for `"coverage_json"` artifact key)

Extend to recognize BOTH artifact keys — `"coverage_json"` (pytest,
jest, go-test) OR `"coverage_lcov"` (cargo-test). The
`native_payload_present` flag flips `true` if EITHER key has a
present artifact path. Without this fix, `check_coverage_availability`
will keep returning `available=False` for cargo runs even after
Facts are derived.

Cross-check: `src/novetest/memory/store.py:_availability_flags` at
lines 315-329. The `has_coverage_facts` flag is set by probing the
persisted `coverage_facts.json` file existence (engine-agnostic),
NOT by checking the artifact key — so once `derive_coverage_facts`
runs successfully for cargo and `write_coverage_facts` persists,
the flag flips automatically. No `store.py` change needed.

### 4. File-path normalization

LCOV from cargo-llvm-cov uses ABSOLUTE paths:
```
SF:/home/yjshin/dev/Nove-Test/tests/manual-test-workspace/cargo-test-basic-coverage/src/arithmetic.rs
```

`CoverageFactSet.files[*].file_path` is `str` but downstream
consumers (`coverage diff`, `inspect`) need PROJECT-RELATIVE paths
for stable cross-run identity (the same fixture in different tmp
workspace dirs MUST produce comparable file_paths).

Normalization rule (pin in parser's docstring):
- `relpath = absolute_path.relative_to(workspace_root)` → store
  `str(relpath)`.
- If `absolute_path` is NOT under `workspace_root` (rare —
  generated code from cargo build script, etc.), keep the
  absolute path AND emit a warning via the existing parser
  warnings channel (mirror `parse_istanbul_json` precedent if it
  has one; else add to `metadata["lcov_warnings"]`).

### 5. Tests

**New unit test file**: `tests/unit/coverage/test_lcov_parser.py`

Mirror the structure of `tests/unit/coverage/test_istanbul_parser.py`
(your existing precedent). Required cases:

1. Happy path: parse a 3-file LCOV with mix of executed + missing
   lines; assert `CoverageFactSet` shape, file count, line counts.
2. `LF`/`LH` summary cross-check matches DA count totals.
3. Empty file → `CoverageJsonParseError` (or `LcovParseError`).
4. `DA:` without preceding `SF:` → parse error.
5. Absolute path normalization to workspace-relative.
6. Path NOT under workspace root → preserved + warning emitted.
7. `BRDA:` records present → parsed into branch fields.
8. `BRDA:` records absent → branch fields empty tuples (no error).
9. Ignored records (`TN:`, `FN:`, `FNDA:`, `FNF:`, `FNH:`, `BRF:`,
   `BRH:`) → parsed cleanly, do not appear in output.
10. Deterministic file ordering (sorted by `file_path`).

Use a small inline LCOV string fixture per test for clarity; do
NOT use the cargo `coverage.lcov` from
`tests/fixtures/projects/cargo-test-basic-coverage/.novetest/...`
in unit tests (those are workspace-state, may not exist on a
fresh checkout, would create fragile coupling).

**Update existing test file**: `tests/unit/coverage/test_derive.py`

Add 2 cases pinning the new dispatch:
1. `engine_name == "cargo-test"` runs route through `parse_lcov`,
   not `parse_coverage_json`. (Use mock to assert which parser
   was called.)
2. `engine_name == "cargo-test"` with missing `coverage_lcov`
   artifact path → returns `CoverageUnavailable` with appropriate
   reason (cargo equivalent of jest's "no coverage artifact"
   case).

**New integration test**: `tests/integration/coverage/test_cargo_lcov_e2e.py`

Real subprocess test using the existing
`tests/fixtures/projects/cargo-test-basic-coverage/` fixture (do
NOT modify the fixture). Skip guard via
`shutil.which("cargo") is None or shutil.which("cargo-nextest") is
None or shutil.which("cargo-llvm-cov") is None` (mirror the
existing `tests/integration/run/test_cargo_coverage.py:32-47`
guard pattern).

Test flow:
1. `cp -r` fixture to `tmp_path`.
2. `novetest init` against the tmp copy.
3. `novetest run --coverage` against the tmp copy.
4. `novetest coverage show <run_id> --output json` — assert:
   - `ok: true`, exit 0
   - `data.coverage_facts.engine_name == "cargo-test"`
   - `data.coverage_facts.ecosystem == "rust"`
   - `data.coverage_facts.mapping_granularity == "aggregate"`
   - `data.coverage_facts.files` has >= 2 entries (the fixture's
     `arithmetic.rs` + `classifier.rs`)
   - At least one file has `missing_lines` non-empty (the
     intentionally-uncovered classifier negative branch)
5. `novetest inspect <run_id> --output json` — assert
   `sub_reports.coverage == "available"` (was "unavailable"
   pre-slice).

DO NOT modify `tests/integration/run/test_cargo_coverage.py`. That
test currently verifies adapter-level LCOV emission; this slice's
integration test verifies Coverage engine derivation downstream.
Different concerns, separate files.

## Out of scope (do NOT touch)

- **Per-test coverage attribution for cargo**. Documented post-MVP
  slow-mode path (`engine-adapters.md` §5 line 363). When that
  slice lands, it'll add a new `mapping_granularity` flow; this
  slice pins `"aggregate"` only.
- **Branch coverage emission from cargo-llvm-cov**. If BRDA
  records aren't in the test LCOV, do nothing. Don't add a
  `cargo-llvm-cov --branch` flag (out of scope; separate
  discussion at MVP-time about branch-coverage feature parity).
- **Modifying the existing `tests/integration/run/test_cargo_coverage.py`**.
  That test owns the adapter-level LCOV emission verification.
  Add a NEW integration test for the Coverage engine flow.
- **`src/novetest/run/**`** — Run team's territory; the cargo
  adapter at `cargo_adapter.py:311` already registers
  `artifact_paths["coverage_lcov"]` (verified by Manual Test
  2026-05-31). No Run-side changes needed.
- **`src/novetest/models/**`** — `CoverageFactSet` / `FileCoverage`
  / `CoverageSummary` shapes are unchanged. Use them as-is.
- **Issue 2 typed-slot work** (running in parallel via Run team's
  slice). This Coverage slice does NOT read or write
  `NativeResult.metadata` — Coverage works against `RunRecord`
  which has its own `metadata` field already.

## Pre-flight checks (before opening handoff)

1. **Equipped host**: same Pre-flight host check as the previous
   cargo hotfix slice — `cargo`, `cargo-nextest`, and
   `cargo-llvm-cov` all on PATH.
2. **Hotfix tip equality**: your worktree base SHOULD be at or
   after `5a6f4fe` (current main tip after the 2026-05-31 cycle
   close). The cargo adapter at this tip emits well-formed LCOV
   (verified by Manual Test); building this slice on an earlier
   tip would risk inheriting the pre-hotfix exit-4 cargo behavior.
3. **Full gate green on equipped host**:
   `uv run pytest -q tests/unit tests/integration -v`
   - Baseline at `5a6f4fe`: **678 passed + 5 skipped** on equipped
     host (676 + 7 on Rust-less hosts).
   - Your tip should be baseline + new test cases, no regressions.
4. **mypy strict clean**: `uv run mypy` → no issues.
5. **Smoke-test the new flow end-to-end before opening handoff**:
   - `cp -r tests/fixtures/projects/cargo-test-basic-coverage /tmp/cargo-cov-smoke`
   - `cd /tmp/cargo-cov-smoke && uv run --project /home/yjshin/dev/Nove-Test novetest init`
   - `uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage`
   - `uv run --project /home/yjshin/dev/Nove-Test novetest coverage show <run_id>`
     — should NOT return "unavailable"; should return real
     Coverage Facts.
   - `uv run --project /home/yjshin/dev/Nove-Test novetest inspect <run_id>` — confirm
     `sub_reports.coverage == "available"`.
   - `rm -rf /tmp/cargo-cov-smoke` after.

## DoD

- [ ] `src/novetest/coverage/lcov_parser.py` exists; `parse_lcov`
      converts LCOV file → `CoverageFactSet` with
      `mapping_granularity == "aggregate"`.
- [ ] LCOV records handled: `SF`, `DA`, `LF`, `LH`,
      `end_of_record`. Optionally `BRDA` if cargo-llvm-cov emits
      it. Ignored records pass through silently.
- [ ] File path normalization absolute → project-relative.
- [ ] `derive.py:113-127` dispatch extended for
      `engine_name == "cargo-test"`.
- [ ] `availability.py:89` recognizes `coverage_lcov` artifact
      key alongside `coverage_json`.
- [ ] 10 unit tests for `parse_lcov` (per §5).
- [ ] 2 dispatch tests added to `test_derive.py`.
- [ ] 1 integration test in
      `tests/integration/coverage/test_cargo_lcov_e2e.py` covering
      the end-to-end flow (init → run --coverage → coverage show →
      inspect).
- [ ] Pre-flight smoke-test E2E green on the equipped dev host
      (see Pre-flight §5).
- [ ] `mypy --strict` clean.
- [ ] Full pytest suite green (baseline + new tests, no
      regressions).
- [ ] No `tests/integration/run/test_cargo_coverage.py`
      modification.

## Handoff format

Standard handoff per team charter at
`agent-comms/handoffs/coverage-team-2026-05-31-cargo-lcov-dispatch.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Pre-flight smoke-test evidence** — paste the exact `coverage
   show` envelope from the smoke test (it's the proof that
   cargo Coverage works end-to-end).
3. **Parser scope decisions** — did you implement BRDA parsing?
   What happened with `LcovParseError` vs `CoverageJsonParseError`?
   Any LCOV records you ignored that PM should know about?
4. **DoD implications**: this slice does NOT close any
   `delivery-phasing.md` checkbox directly (Phase 2 §"Engine
   adapter coverage" mentions cargo as Phase 3 implicit-extension,
   not a numbered DoD bullet). The cargo Coverage gap was a
   carry-forward, not a DoD checkbox. After this slice, the
   carry-forward closes.
5. **Open questions for PM** — anything the brief did not
   anticipate (especially: any cargo-llvm-cov output quirks you
   discovered; any FileCoverage field that doesn't map cleanly
   from LCOV; any decisions about workspace_root resolution).

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md`, the new `agent-comms/` files, and
   `INDEX.md` alongside source. PreToolUse hook blocks the commit
   if `src/` or `tests/` are staged but `WORKLOG.md` is not.

## Cross-references

- **Cargo adapter (registers `coverage_lcov` artifact)**:
  `src/novetest/run/adapters/cargo_adapter.py:311`. Read-only
  context — do not modify.
- **Existing parsers (precedents to mirror)**:
  - `src/novetest/coverage/parser.py` (pytest coverage.py JSON)
  - `src/novetest/coverage/istanbul_parser.py` (jest istanbul)
- **CoverageFactSet model** (the canonical output shape):
  `src/novetest/models/coverage_fact_set.py:172-197`.
- **Per-test vs aggregate decision pin**:
  `design/implementation-plan/engine-adapters.md:361-363` —
  "Per-test mode = per-test invocations, opt-in slow mode —
  out-of-scope for v1 (deferred to a post-MVP slice)."
- **Cargo adapter execution-path constraints** (still in force —
  this slice does NOT alter them):
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`.
- **Trigger-(b) closure context** (proves cargo adapter is
  reliable enough to build on):
  `agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`.
- **Parallel-cycle sibling slice** (Run typed-slot — no file
  overlap, independent dispatch):
  `agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`.
