---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-05-31
slug: fallback-modes
related:
  - design/implementation-plan/localization-strategy.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md
  - agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md
  - src/novetest/localization/derive.py
  - src/novetest/localization/sbfl/
---

# Task: Localization fallback modes — `sbfl_aggregate` + `failure_proximity`

## TL;DR

Replace the two `NotImplementedError`-style placeholder branches at
`src/novetest/localization/derive.py:167` (no coverage) and
`derive.py:179` (non-per-test coverage) with **actual mode
implementations** per `design/implementation-plan/localization-strategy.md`
§2. Closes **Phase 4 §4 DoD bullet #2** ("Mode field populated
correctly across all three fixtures").

After this slice, `novetest localization` works across **all 4
currently-supported languages** with tiered quality:
- `sbfl_per_test` (pytest only) — full accuracy, unchanged
- `sbfl_aggregate` (jest / go-test / cargo) — FLUCCS-style
  regression-aware where Regression Facts exist, failure-only Ochiai
  floor otherwise; `confidence: "medium"`
- `failure_proximity` (any engine with no coverage at all) — stack
  trace + Regression Facts intersection ranking; `confidence: "low"`

The algorithms are **peer-reviewed published techniques** (FLUCCS:
Sohn & Yoo, ISSTA 2017; failure proximity: standard IDE heuristic).
No novel research — pure implementation of an already-fully-specified
design.

## Why this slice exists (product framing)

Today: Localization gracefully degrades to `LocalizationUnavailable`
for every non-pytest run because the placeholder branches raise.
Result: 3 of 4 supported languages cannot use the `novetest
localization` verb at all.

After: 4 of 4 supported languages produce a ranked suspicion list
on every run; the AI consumer reads the `mode` + `confidence`
fields to gauge evidence strength. Localization stops being a
"pytest-only" feature and becomes a universal product surface.

This is the **single biggest user-visible Localization product
gain since the engine landed** (2026-05-28). Per the cycle's
load-bearing learnings, it also validates the canonical-normalization
architecture: the Localization engine consumes
`CoverageFactSet.mapping_granularity` discriminator + the canonical
`TestResult` / `RunRecord` shapes — no engine-specific dispatch on
`engine_name`.

## Background — what already exists (don't re-build)

### Design (fully specified in `localization-strategy.md` §2)

The 3-mode table + mode-selection pseudocode + algorithm
descriptions are pinned verbatim in §2 of the strategy doc. Read
it FIRST. Specifically:
- **Lines 79-123**: §2 mode table + mode-selection pseudocode +
  fallback hierarchy (regression-aware reweighting → failure-only
  Ochiai → coverage-weighted heuristic).
- **Lines 161-190**: §4 output fields (rank, tied_with, score_raw,
  score_normalized, formula, alternate_scores) — same shape as
  per-test mode produces.
- **Lines 192-225**: §5 empty-evidence behavior (when to return
  `LocalizationUnavailable` vs. degraded fallback).
- **Lines 226-265**: §6 the put-it-together example JSON envelope
  showing `mode: "sbfl_aggregate"`, `confidence: "medium"`, the
  output shape `failure_proximity` should also fit.

### Code skeleton (already in place)

- `src/novetest/localization/derive.py:167-188` — two
  `NotImplementedError`-style branches with descriptive
  `LocalizationUnavailable(detail="...not yet implemented (Phase 4
  follow-up)")` errors. These are the slots to fill.
- `src/novetest/localization/derive.py:299` — `_derive_per_test()`
  already populates `mode="sbfl_per_test"`. Add `_derive_aggregate()`
  and `_derive_failure_proximity()` paired helpers.
- `src/novetest/localization/sbfl/{ochiai,op2,dstar,tarantula}.py`
  — all 4 formulas already work on `spectra`. Reuse them
  verbatim for `sbfl_aggregate` mode (the spectra construction
  differs; the formulas are identical).
- `src/novetest/localization/sbfl/spectra.py` — `Spectra` class /
  builder for per-test mode. For `sbfl_aggregate`, build the
  spectra differently (per §2 algorithm): failing-test-set as
  `e_f` column; passing component approximated from `aggregate
  hits − failing-test hits`.
- `LocalizationFinding` model already has `mode: str`,
  `confidence: str` (`"high" | "medium" | "low"`), `formula`,
  `entries`, etc. — NO model changes needed.

### Input data (already canonical for all 4 engines)

| Input | Source | Available for |
|---|---|---|
| `CoverageFactSet.mapping_granularity` | Coverage engine | per-test (pytest) / aggregate (cargo/go-test/jest) |
| `CoverageFactSet.files[*].executed_lines` / `missing_lines` | Coverage engine | All 4 engines (aggregate level) |
| `CoverageFactSet.files[*].line_contexts` (per-test) | Coverage engine | pytest only |
| `RunRecord.test_results[*].outcome` + `failure_reference` | Run engine | All 4 engines |
| `RegressionFactSet` (changed files) | Regression engine | All 4 engines (when baseline exists) |

Failure log files (pointed to by `TestResult.failure_reference`)
exist for all 4 engines — pytest writes pytest traceback; cargo
writes the `panicked at <file>:<line>:<col>` literal (verified
2026-05-31 sweep); jest writes jest's expected/actual; go writes
`go test -v` failure block. **These formats DIFFER per engine** —
the failure-proximity mode must accept this variability. See §
"Failure log parser" below.

## Scope (what this slice DOES)

### 1. Implement `sbfl_aggregate` mode

**Where**: replace `derive.py:179` placeholder; add helper
`_derive_aggregate()` (mirror `_derive_per_test()`'s shape).

**Algorithm** (per `localization-strategy.md` §2 + §"Most defensible
fallback hierarchy"):

```
Given:
  - CoverageFactSet with mapping_granularity in {"aggregate",
    "per-test-file", "per-test-class"}  (NOT "per-test")
  - failed_test_ids (non-empty by precondition — §5)
  - Optional: RegressionFactSet (passed in if present)

Step 1: Build aggregate spectra.
  For each covered line/symbol in CoverageFactSet.files:
    e_f = |{failing tests whose failure_reference indicates this line/file}|
          (best-effort — use failing-tests-union-of-covered-files heuristic
           since per-test mapping is unavailable; spec: pin file-level for v1)
    n_f = total_failing_tests - e_f
    e_p = max(0, aggregate_line_hits - e_f)  ← key approximation per §2
    n_p = total_passing_tests - e_p

Step 2: Compute formulas using existing sbfl/{ochiai,op2,dstar,
        tarantula}.py functions — NO new formula code.

Step 3: If RegressionFactSet provided AND non-empty, apply FLUCCS
        reweighting (Sohn & Yoo ISSTA 2017):
          adjusted_score = base_score * (1 + α * regression_signal)
        where regression_signal = 1.0 if file is in
        RegressionFactSet.changed_files, else 0.0.
        α = 0.5 as v1 default (cite the paper's tuned value).

Step 4: Rank, persist, return LocalizationFinding with:
        mode = "sbfl_aggregate"
        confidence = "medium" if step 3 applied, else "medium" still
                     (per §2 table — both sub-variants are "medium" tier)
        formula, entries, alternate_scores_available — same shape
        as per-test mode.
```

**File-level granularity is acceptable for v1**: `sbfl_aggregate`
ranks at the file level (not line/symbol). The strategy doc §3
allows file-level fallback for ecosystems where the symbol
resolver is not ready (currently: all non-Python). Pin file-level
for this v1 slice; line/symbol upgrade is post-MVP.

### 2. Implement `failure_proximity` mode

**Where**: replace `derive.py:167` placeholder; add helper
`_derive_failure_proximity()`.

**Algorithm** (per `localization-strategy.md` §2):

```
Given:
  - failed_test_ids (non-empty)
  - Each failing test has TestResult.failure_reference → log file path
  - Optional: RegressionFactSet

Step 1: Parse failure logs to extract (file, line) references.
        See § "Failure log parser" below for per-engine format
        handling.

Step 2: Aggregate references across all failing test failure logs.
        For each file referenced, count occurrences.

Step 3: If RegressionFactSet exists, intersect with changed files
        — boost score for files appearing in both. (FLUCCS-style
        prior, same α = 0.5 as sbfl_aggregate.)

Step 4: Rank files by aggregated score (occurrences + regression
        boost). Return LocalizationFinding with:
        mode = "failure_proximity"
        confidence = "low"
        entries[*].code_location.kind = "file"  (no symbol; failure
                                                  trace lines are
                                                  file/line tuples)
        entries[*].score_raw = aggregated count + boost
        entries[*].score_normalized = min-max normalize in [0,1]
        alternate_scores_available = []  (no SBFL formulas computed;
                                          this mode is not SBFL —
                                          §"Failure-proximity is a
                                          distinct algorithm" below)
```

**`failure_proximity` is NOT an SBFL mode** (despite the engine
package being named `sbfl/`). It's a separate ranking technique.
Implementation lives in a new file
`src/novetest/localization/failure_proximity.py` (sibling of
`sbfl/`, not under it). The output uses the SAME
`LocalizationFinding` shape so downstream consumers don't branch
on mode, but the internal computation is independent.

### 3. Failure log parser (sub-module of failure_proximity)

**Where**: new helper
`src/novetest/localization/failure_proximity.py:parse_failure_log()`
(or `failure_log_parser.py` — implementer's call).

**Engine-specific format handling**:

| Engine | Format example | Parser strategy |
|---|---|---|
| pytest | `tests/test_x.py:5: AssertionError\n  assert 2 == 3` | Regex: `^([\w/\-\.]+\.py):(\d+):` |
| cargo (libtest panic) | `thread 'tests::test_div' panicked at src/lib.rs:32:9` | Regex: `panicked at ([\w/\-\.]+):(\d+):(\d+)` |
| jest | `at Object.<anonymous> (/path/to/src/calc.test.ts:42:21)` | Regex: `\(([\w/\-\.]+):(\d+):(\d+)\)` |
| go test | `--- FAIL: TestAdd (0.00s)\n    add_test.go:14: expected 5, got 6` | Regex: `^\s*([\w/\-\.]+\.go):(\d+):` |

Implementation guidance:
- Use `engine_name` from the `RunRecord` to pick the right regex
  set. Yes, this DOES branch on `engine_name` — but it's the
  inner-most parsing layer where format variance is inherent. The
  output (file, line) tuples are canonical.
- Best-effort parser: if regex matches, use the result. If no
  match, skip that log file (don't crash) — log a warning via
  `LocalizationFinding.metadata["parse_warnings"]`.
- Test each engine's parser with at least one realistic failure
  log fixture per engine (use real cargo `panicked at src/lib.rs:N:M`
  from the 2026-05-31 verified output; pytest from existing
  `localization-branch` fixture; jest/go from minimal hand-crafted
  inputs).

### 4. Update mode-selection routing in `derive.py`

**Where**: replace the placeholder branches at lines 167-188.

**New flow** (per §2 pseudocode):

```python
def derive_localization_findings(store, run_id, *, formula, top_n):
    # ... existing prelude (run lookup, failed_test_ids, etc.) ...

    if not failed_test_ids:
        return LocalizationUnavailable(reason=REASON_NO_FAILED_TESTS, ...)

    coverage = get_coverage_facts(store, record.run_reference)
    regression = try_get_latest_regression_facts(store, record)  # best-effort,
                                                                   # None if no
                                                                   # baseline

    if isinstance(coverage, CoverageUnavailable):
        # Path C: failure_proximity
        return _derive_failure_proximity(store, record, failed_test_ids,
                                          regression, top_n)

    if coverage.mapping_granularity == "per-test":
        # Path A: existing sbfl_per_test (unchanged)
        return _derive_per_test(store, record, coverage, failed_test_ids,
                                 top_n, formula)

    # mapping_granularity in {"aggregate", "per-test-file",
    #                         "per-test-class"}
    # Path B: sbfl_aggregate (regression-aware if regression available)
    return _derive_aggregate(store, record, coverage, failed_test_ids,
                              regression, top_n, formula)
```

`try_get_latest_regression_facts()` is a new best-effort helper:
look up the latest Regression Facts for this run's Test Target;
return None if absent (no baseline yet). NO error path — absence
is normal.

### 5. New fixtures

**`tests/fixtures/projects/localization-aggregate-only/`**

Mirror `localization-branch/` shape but use a language without
per-test coverage. Recommended: **cargo** (since the cargo
adapter is freshly E2E-verified and produces canonical aggregate
LCOV per the 2026-05-31 cycle). 3-4 source files, 1 intentional
bug, ~5 tests with 1 failing.

Alternative: go-test or jest — both work. Pick whichever has the
lightest fixture infrastructure. Cargo is recommended because the
verification path is freshest.

**`tests/fixtures/projects/localization-no-coverage/`**

Run without `--coverage`. Same engine (or pytest — pytest
without `--cov` has no coverage facts). Same fixture project
structure with an intentional bug + failing test. The failing
test's failure log MUST reference the buggy file:line so
`failure_proximity` can rank correctly.

Fixture authoring guidelines (carry-forward from the 2026-05-29
gotcha about `cd`-ing into temp dirs — see
`history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md`
load-bearing learning #5): fixture itself stays under
`tests/fixtures/projects/`; integration tests use `tmp_path` +
`cp -r` to copy, never operate on the source fixture directly.

### 6. Tests

**Unit** (under `tests/unit/localization/`):
- `test_derive_aggregate.py`: 5+ cases — happy path, no regression
  facts, with regression facts (FLUCCS reweighting), small-N
  (1 failing 1 passing) edge case, granularity = `"per-test-file"`
  path
- `test_derive_failure_proximity.py`: 5+ cases — happy path,
  per-engine parser (pytest / cargo / jest / go), no regression
  facts, empty failure log (no parseable references) → warning +
  empty findings
- `test_failure_log_parser.py`: per-engine parser unit tests with
  hand-crafted inputs covering format edge cases (no match,
  partial match, multi-line trace, ANSI escape codes if any)
- `test_derive_modes_dispatch.py`: assert the routing in `derive.py`
  picks the right mode given each (coverage, regression) input
  combination (3 paths × 2 regression states = 6 cases minimum)

**Integration** (`tests/integration/localization/`):
- `test_aggregate_mode_e2e.py`: real `novetest run` against
  `localization-aggregate-only` fixture → `novetest localization
  latest` → assert `mode == "sbfl_aggregate"`, `confidence ==
  "medium"`, top-ranked file is the buggy one
- `test_failure_proximity_e2e.py`: real `novetest run` (no
  `--coverage`) against `localization-no-coverage` fixture →
  `novetest localization latest` → assert `mode ==
  "failure_proximity"`, `confidence == "low"`, top-ranked file
  is the buggy one
- `test_mode_selection_per_engine.py`: parametrized over engines
  with available fixtures — confirm mode-selection picks the
  expected mode for each (granularity, regression-facts) state

### 7. Envelope verification

The `localization_outcome` envelope was frozen 2026-05-30 at
`decisions/2026-05-30-localization-outcome-envelope-shape.md`.
That decision PINNED the 12/9/6/3-key shape for `kind: "fact-set"`
including the `mode` and `confidence` fields. Your slice MUST:
- Honor the freeze byte-for-byte for `sbfl_per_test` mode (no
  regression — existing tests catch this).
- Apply the SAME 12/9/6/3-key shape to `sbfl_aggregate` mode
  output. `alternate_scores_available` is still 3 sorted strings.
  `entries[*].alternate_scores` is still a 3-entry dict.
- Apply the same shape to `failure_proximity` mode WITH ONE
  EXPLICIT DEVIATION: `alternate_scores_available` is `[]` (empty
  list) and `entries[*].alternate_scores` is `{}` (empty dict),
  because failure_proximity is not SBFL and doesn't compute
  per-formula scores. **This deviation is the only acceptable
  envelope change** — document it in the slice's WORKLOG entry
  and reference for PM's follow-up freeze amendment if needed.

## Out of scope (do NOT touch)

- **Per-test coverage attribution for non-pytest engines** —
  post-MVP slow-mode slice per `engine-adapters.md` §5. Don't
  try to enable per-test mode for cargo / jest / go in this
  slice.
- **Symbol resolver upgrades** for non-Python ecosystems — file-
  level is the v1 fallback per strategy doc §3. Don't write JS/Go/Rust
  AST parsers in this slice.
- **`branch_arc_semantics` discriminator handling** — per CEO
  2026-05-31 decision D=a (keep as metadata key; sbfl_aggregate
  uses line info only, ignores branch tuples). If your
  implementation finds branch info would meaningfully help
  sbfl_aggregate accuracy, flag in handoff Open Q's but do NOT
  implement.
- **Performance NFR-LOC-002 perf slice** — separate slice (1B
  candidate). Don't tune for the 500-failed × 50k-loc benchmark
  in this slice. Correctness first; perf later.
- **`engine-adapters.md` §5** edits — that doc references the
  per-engine per-test attribution status, which doesn't change
  in this slice.
- **`models/`** — no model-shape changes. `LocalizationFinding`
  already has `mode` + `confidence` + `metadata` fields.

## Concrete file map

| File | Action |
|---|---|
| `src/novetest/localization/derive.py` | Replace placeholders at lines 167 + 179; add `_derive_aggregate()`, `_derive_failure_proximity()`, `try_get_latest_regression_facts()` helpers |
| `src/novetest/localization/failure_proximity.py` | NEW — failure log parser + proximity ranker |
| `src/novetest/localization/sbfl/spectra.py` | Extend `Spectra` builder to construct aggregate spectra (or add `build_aggregate_spectra()` helper if cleaner) |
| `src/novetest/localization/sbfl/{ochiai,op2,dstar,tarantula}.py` | NO CHANGES — formulas are mode-agnostic |
| `tests/fixtures/projects/localization-aggregate-only/` | NEW fixture |
| `tests/fixtures/projects/localization-no-coverage/` | NEW fixture |
| `tests/unit/localization/test_derive_aggregate.py` | NEW |
| `tests/unit/localization/test_derive_failure_proximity.py` | NEW |
| `tests/unit/localization/test_failure_log_parser.py` | NEW |
| `tests/unit/localization/test_derive_modes_dispatch.py` | NEW |
| `tests/integration/localization/test_aggregate_mode_e2e.py` | NEW |
| `tests/integration/localization/test_failure_proximity_e2e.py` | NEW |
| `tests/integration/localization/test_mode_selection_per_engine.py` | NEW |

## Pre-flight checks (before opening handoff)

1. **Read `localization-strategy.md` §2-§6 fully** — design is the
   spec; this brief is the dispatch. Strategy doc owns the
   algorithmic ground truth.
2. **Full gate green** on equipped host:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline at this cycle's tip (`ad31b2f`): **712 + 5** on
     equipped host, **676 + 7** on Rust-less.
   - Your tip = baseline + new tests. No regressions.
3. **mypy strict clean**: `uv run mypy` → no issues, ≤72 source
   files (70 baseline + 1 new `failure_proximity.py` + possibly 1
   new `aggregate.py` if you split out).
4. **`sbfl_per_test` regression check**: existing
   `localization-branch` fixture still produces `mode ==
   "sbfl_per_test"`, top-ranked function = `divide`, Ochiai score
   = 1.0 (the 2026-05-29 baseline). The per-test path is
   structurally untouched; this is regression-pinning.
5. **End-to-end smoke per mode** on equipped host:
   - Mode A (existing): `localization-branch` → `mode: "sbfl_per_test"`,
     `confidence: "high"`.
   - Mode B (new): `localization-aggregate-only` → `mode:
     "sbfl_aggregate"`, `confidence: "medium"`, buggy file
     ranked #1.
   - Mode C (new): `localization-no-coverage` → `mode:
     "failure_proximity"`, `confidence: "low"`, buggy file
     ranked #1.
6. **Mode-selection no-cross-talk**: confirm Mode A run doesn't
   accidentally hit Mode B path (pytest `localization-branch` =
   per-test coverage → must stay Mode A).

## DoD

- [ ] `_derive_aggregate()` implemented per §"Scope §1"; replaces
      `derive.py:179` placeholder.
- [ ] `_derive_failure_proximity()` implemented per §"Scope §2";
      replaces `derive.py:167` placeholder.
- [ ] `failure_proximity.py` module created with per-engine log
      parser.
- [ ] `try_get_latest_regression_facts()` helper added; absence is
      non-error.
- [ ] Mode-selection routing in `derive.py` matches strategy doc
      §2 pseudocode exactly.
- [ ] `localization-aggregate-only/` fixture authored.
- [ ] `localization-no-coverage/` fixture authored.
- [ ] All unit tests in §"Scope §6" added; full suite green.
- [ ] All 3 integration tests added; pass on equipped host.
- [ ] `sbfl_per_test` regression: existing `test_localization_e2e.py`
      tests still pass byte-for-byte.
- [ ] Envelope conformance: `mode` field carries one of `{"sbfl_per_test",
      "sbfl_aggregate", "failure_proximity"}`; `confidence` carries
      one of `{"high", "medium", "low"}`; 12/9/6/3-key shape held
      with the documented `alternate_scores_available: []`
      deviation for `failure_proximity` only.
- [ ] mypy --strict clean.
- [ ] Pre-flight smoke per mode green on equipped host.
- [ ] `delivery-phasing.md` Phase 4 §4 DoD bullet #2 **believed
      closed** (PM verifies + ticks at cycle close — your handoff
      lists this claim).

## Handoff format

Standard handoff at `agent-comms/handoffs/localization-team-2026-05-31-fallback-modes.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Pre-flight smoke evidence** — paste the 3 mode envelopes
   verbatim (one per mode) so PM can compare against expected
   shape.
3. **Phase 4 §4 #2 DoD claim** — explicit assertion that the
   delivery-phasing.md bullet "Mode field populated correctly
   across all three fixtures" is closed. PM verifies the 3
   fixtures' envelopes show the 3 distinct mode values.
4. **Envelope shape deviation for `failure_proximity`** — document
   verbatim what the empty-alternate-scores fields look like.
   PM decides at cycle close whether to amend the 2026-05-30
   freeze decision OR just narrate the deviation in history.
5. **Failure log parser per-engine status** — table of (engine →
   regex → tested?). PM will know which adapters need follow-up
   if any parser is incomplete.
6. **Open questions for PM** — anything you encountered that the
   brief did not anticipate.

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + new `agent-comms/` files + `INDEX.md`
   alongside source. PreToolUse hook blocks the commit if `src/`
   or `tests/` are staged without `WORKLOG.md`.

## Cross-references

- **Authoritative algorithm spec**:
  `design/implementation-plan/localization-strategy.md` §2-§6
  (full mode table, pseudocode, output shape, citations).
- **Envelope shape freeze** (must hold byte-for-byte for
  `sbfl_per_test`; documented deviation for `failure_proximity`):
  `agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md`.
- **Phase 4 §4 DoD bullet #2** (this slice closes it):
  `design/implementation-plan/delivery-phasing.md` Phase 4 §4
  line 187.
- **CEO 2026-05-31 decision D=a** (branch_arc_semantics stays
  metadata-key; this slice uses line info only):
  `agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md`
  §"Issues raised + PM queueing decisions" item 2.
- **Existing per-test mode reference**: `_derive_per_test()` in
  `derive.py` is your structural template for `_derive_aggregate()`
  and `_derive_failure_proximity()`.
- **Parallel-cycle sibling slice** (Run team — no file overlap):
  `agent-comms/tasks/run-team-2026-05-31-build-failure-heuristic-polish.md`.
