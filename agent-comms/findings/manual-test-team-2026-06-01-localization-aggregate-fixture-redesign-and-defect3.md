---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-06-01
slug: localization-aggregate-fixture-redesign-and-defect3
verdict: passed
related:
  - agent-comms/verifications/2026-06-01-localization-aggregate-fixture-redesign-and-defect3.md
  - agent-comms/handoffs/localization-team-2026-06-01-aggregate-fixture-redesign-and-defect3.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
  - agent-comms/questions/main-branch-team-2026-06-01-localization-latest-aggregate-discovery.md
---

# Manual Test findings — Localization fallback-modes + fixture redesign + Defect 3 fix

**Verdict**: **passed**.

After **four attempts** across two cycles, the Localization team's
Phase 4 §4 #2 slice finally lands cleanly on `main`. The merged tip
`05f86bc` bundles three commits closing three defects:

1. **`804690b` (feat)** — `sbfl_aggregate` + `failure_proximity`
   modes added (the original Phase 4 §4 #2 feature)
2. **`3ccfd72` (Defect 2 / CEO Option A)** — the failing `test_divide`
   relocated from `lib.rs::tests` into `arithmetic.rs`'s own
   `#[cfg(test)] mod tests` block, so the cargo panic trace's first
   line points at the bug file (`src/arithmetic.rs:53:9`) rather than
   the assertion-host file (`src/lib.rs:35:9`).
3. **`05f86bc` (Defect 3 / CEO Option D)** — two complementary
   tightenings in `src/novetest/localization/`:
   - `failure_proximity.py` — dropped the third "defensive catch-all"
     regex `\b<file>.rs:N:M` from `_CARGO_REGEXES`. Only the two
     anchored patterns (`panicked at`, `failed at`) remain. The
     catch-all was slurping `/rustc/<hash>/library/core/src/...`
     stdlib paths from cargo's default stack backtrace.
   - `derive.py:438` — `_derive_aggregate`'s candidate set
     restricted to `covered_files` (no union with failing-trace
     files). Stdlib paths aren't instrumented, so they're never in
     `coverage.files` — defense in depth against any future parser
     regression.

The third commit's two changes work in concert: the parser change
removes the noise at the source; the algorithm filter is the safety
net. Both are CEO's Option D (recommended in Main Branch's question
doc).

**ALL 8 verification scenarios + 5 edge probes verified. No source
regressions. Defect 4 (separate, pre-existing) confirmed in the
field — not blocking, has a recommended fix path.**

## What was tested

A CEO-readable narrative:

1. **The cycle's load-bearing assertion empirically passes**:
   `novetest localization <run_id>` against the redesigned cargo
   fixture now ranks `src/arithmetic.rs` at **rank 1** with `kind:
   "fact-set"`, `mode: "sbfl_aggregate"`, `confidence: "medium"`,
   `formula: "ochiai"`, `score_raw: 0.5`. The `entries` list has
   length **1** — only `arithmetic.rs` survives the algorithm-level
   coverage-files filter. Pre-fix (third attempt), the top-1 was
   `/rustc/<hash>/library/core/src/ops/function.rs` with arithmetic.rs
   buried at rank #4. Post-fix, stdlib paths are completely absent
   from the result.

2. **The Ochiai score arithmetic matches the verification doc's
   prediction byte-for-byte**: `score_raw = 1/√((e_f + n_p)·(e_f + e_p))
   = 1/√((1+0)·(1+3)) = 0.5`. The alternate scores match too
   (dstar2 = 1/3, op2 = 0.25, tarantula = 0.5). `score_normalized: 0.0`
   is correct because min-max normalization over a single entry yields
   0 by construction.

3. **The fixture redesign (Option A) is structurally sound**:
   `arithmetic.rs` carries BOTH the bug (`pub fn divide(a, b) { a + b }`
   — intentional, comment-flagged) AND the `#[cfg(test)] mod tests`
   block containing `test_divide`. `lib.rs::tests` contains only the
   3 passing tests (`test_add`, `test_subtract`,
   `test_classify_positive`) — no `test_divide`. So the cargo panic
   trace's `assert_eq!` site IS the bug site.

4. **The Defect 3 fix surfaces in source as expected**:
   - `failure_proximity.py:115-153` — `_CARGO_REGEXES` is a 2-tuple
     of `panicked at` + `failed at` anchored patterns. A multi-line
     comment block (lines 120-127) preserves the design rationale
     and points at the question doc for empirical evidence.
   - `derive.py:438` — `all_files = sorted(covered_files)`. The
     prior shape `sorted(covered_files | set(file_to_failed_tests.keys()))`
     is gone. Adjacent comments cross-reference the question doc.

5. **The other new mode (`failure_proximity`) works end-to-end on
   the no-coverage pytest fixture**: `kind: "fact-set"`, `mode:
   "failure_proximity"`, `confidence: "low"`,
   `alternate_scores_available: []` (documented deviation —
   failure_proximity is not SBFL), `entries[0].alternate_scores: {}`
   (same deviation), and `entries[0].code_location.file` ends with
   `statistics.py` (the bug site in the fixture).

6. **The existing per-test (pytest) mode is unaffected** — Scenario 5
   confirms `localization-branch` still produces `mode: "sbfl_per_test"`,
   `confidence: "high"`, `formula: "ochiai"`, `entries[0]` ranks
   `divide` at top-1 with Ochiai `score_raw: 1.0` and
   `kind: "symbol"` granularity (function-level — different from
   aggregate mode's file-level granularity).

7. **The cargo coverage path (Defect 1's `--ignore-run-fail` from
   last cycle) is wired correctly for the failing-test path**:
   Scenario 1's Step 1 envelope has `has_coverage_facts: true`,
   `coverage_outcome.kind: "fact-set"`, `mapping_granularity:
   "aggregate"`, 85.71% covered. Pre-Defect-1, this would have
   been `kind: "unavailable"`.

8. **Defect 4 confirmed in the field**: `novetest localization
   latest` on the aggregate cargo run returns
   `kind: "unavailable"`, `reason: "run_not_analyzable"`,
   `detail: "no analyzable runs in store (1 candidates checked)"`.
   Root cause exactly matches Main Branch's question doc:
   `src/novetest/localization/retrieval.py:99` hardcodes
   `return coverage.mapping_granularity == "per-test"`. Cargo runs
   carry `mapping_granularity: "aggregate"` → the gate returns
   `False` → `resolve_latest_analyzable_run` reports no candidate.

   **Not blocking this cycle's merge.** The explicit `<run_id>`
   path works (Scenario 1 proves), and the slice's intended scope
   (Defects 2 + 3) is complete with gate green. Defect 4 is
   orthogonal — recommend PM dispatch a separate fix.

9. **mypy strict gate is clean at 72 source files** (+1 from
   baseline 71 = `failure_proximity.py`, the new module from
   `804690b`).

10. **The full pytest gate is green at 759 + 5 skipped in 31.42s**
    (baseline 715 + 5 → +44 net, matches Main Branch claim
    line-for-line).

## Commands run (verbatim) + observed output

### Pre-flight — full gate + mypy + Loc integration trio

```
$ uv run pytest -q tests/unit tests/integration
... 759 passed, 5 skipped in 31.42s

$ uv run mypy
Success: no issues found in 72 source files

$ uv run pytest -v \
    tests/integration/localization/test_aggregate_mode_e2e.py \
    tests/integration/localization/test_failure_proximity_e2e.py \
    tests/integration/localization/test_mode_selection_per_engine.py
collected 5 items
tests/integration/localization/test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top                  PASSED
tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top            PASSED
tests/integration/localization/test_mode_selection_per_engine.py::test_mode_selection_routes_to_expected_mode[localization-branch]       PASSED
tests/integration/localization/test_mode_selection_per_engine.py::test_mode_selection_routes_to_expected_mode[localization-no-coverage]  PASSED
tests/integration/localization/test_mode_selection_per_engine.py::test_per_test_path_does_not_cross_talk_to_aggregate                     PASSED
5 passed in 2.30s
```

Result: ✅ **759 + 5**, **72 src**, **Loc trio 5/5 in 2.30s**.

### Scenario 1 — Aggregate mode E2E (THE SMOKING GUN)

```
$ cd tests/manual-test-workspace/loc-fallback-modes/localization-aggregate-only
$ novetest init        # ok: true, store_state: ready
$ novetest run --coverage > /tmp/sc1_run.json
$ echo $?
3
$ RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/sc1_run.json'))['data']['memory_entry']['run_record']['run_reference']['run_id'])")
$ echo $RUN_ID
01KSZAA2MD5TS716J04D7BX77E
$ novetest localization $RUN_ID > /tmp/sc1_loc.json
$ echo $?
0
```

**Step 1 (run --coverage)** envelope projection:
| Path | Observed | Expected |
|---|---|---|
| Shell exit | `3` (test-failures-detected) | `3` ✓ |
| `ok` | `true` | `true` ✓ |
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` | — ✓ |
| `data.memory_entry.run_record.status` | `"failed"` | `"failed"` ✓ |
| `data.memory_entry.run_record.summary_counts` | `{passed: 3, failed: 1, skipped: 0, total: 4}` | same ✓ |
| `data.memory_entry.has_coverage_facts` | `true` | `true` ✓ |
| `data.coverage_outcome.kind` | `"fact-set"` | `"fact-set"` ✓ |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` | `"aggregate"` ✓ |
| `data.coverage_outcome.summary.percent_covered` | `85.71` | `85.71` ✓ |

**Step 2 (localization <run_id>)** envelope projection:
| Path | Observed | Expected |
|---|---|---|
| `ok` / `errors` | `true` / `[]` | — ✓ |
| `data.localization_outcome.kind` | `"fact-set"` | `"fact-set"` ✓ |
| `data.localization_outcome.mode` | `"sbfl_aggregate"` | `"sbfl_aggregate"` ✓ |
| `data.localization_outcome.confidence` | `"medium"` | `"medium"` ✓ |
| `data.localization_outcome.formula` | `"ochiai"` | `"ochiai"` ✓ |
| `data.localization_outcome.alternate_scores_available` | `["dstar2", "op2", "tarantula"]` | same ✓ |
| `data.localization_outcome.top_n` | `10` | `10` ✓ |
| **`data.localization_outcome.entries` length** | **`1`** | **`1`** ✓ (stdlib paths filtered) |
| **`entries[0].rank`** | **`1`** 🎯 | **`1`** 🎯 |
| **`entries[0].code_location.file`** | **`"src/arithmetic.rs"`** 🎯 | **same** 🎯 |
| `entries[0].code_location.primary_line` | `53` | `53` ✓ (assert_eq! line) |
| `entries[0].code_location.evidence_lines` | `[53]` | — ✓ |
| `entries[0].code_location.kind` | `"file"` | `"file"` ✓ (v1 granularity per strategy doc §3) |
| `entries[0].code_location.symbol` | `null` | — ✓ (aggregate doesn't carry symbol info) |
| `entries[0].score_raw` | `0.5` | `0.5` ✓ (Ochiai = 1/√((1+0)·(1+3)) = 0.5) |
| `entries[0].score_normalized` | `0.0` | `0.0` ✓ (single entry → min-max yields 0) |
| `entries[0].alternate_scores` | `{dstar2: 0.333..., op2: 0.25, tarantula: 0.5}` | same ✓ |
| `data.localization_outcome.metadata` | `{regression_reweighted: false, changed_files_count: 0}` | same ✓ |

Result: 🎯 ✅ **THE SMOKING-GUN PROOF.** `src/arithmetic.rs` ranks
top-1 as the original e2e test asserted. Pre-fix (third attempt),
the top-1 was `/rustc/<hash>/library/core/src/ops/function.rs`,
with arithmetic.rs buried at rank #4. Post-fix, stdlib paths are
absent from the result entirely (entries length = 1, not 4+).
Defect 3's two-layer fix (parser + algorithm) is empirically proven.

### Scenario 2 — Redesigned fixture inspection

`arithmetic.rs` (excerpts):
```rust
pub fn divide(a: i32, b: i32) -> i32 {
    // Deliberate bug — should be `a / b`. The `tests::test_divide` case
    // below fails because of this line.
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;
    // ...
    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2), 5);
    }
}
```

`lib.rs::tests` (excerpt):
```rust
#[cfg(test)]
mod tests {
    use super::arithmetic::{add, subtract};
    use super::classifier::classify;

    #[test] fn test_add() { assert_eq!(add(2, 3), 5); }
    #[test] fn test_subtract() { assert_eq!(subtract(10, 4), 6); }
    #[test] fn test_classify_positive() { assert_eq!(classify(7), "positive"); }
}
```

Result: ✅ **Option A executed correctly.** `arithmetic.rs` carries
both the bug AND the failing test in the same file; `lib.rs::tests`
has the 3 passing tests only. Module-level doc comments explain the
co-location rationale ("Why the test lives here, not in
`lib.rs::tests`") — accessible to AI consumers reading the fixture.

### Scenario 3 — Defect 3 fixes verified in source

**3a. `failure_proximity.py`** (`grep "panicked at\|failed at\|catch-all" ...`):
```
115:_CARGO_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
116:    # Standard libtest panic: ``thread '...' panicked at <path>:<line>:<col>``.
117:    re.compile(rf"panicked at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
118:    # ``assertion `...` failed at <path>:<line>:<col>`` — newer rustc forms.
119:    re.compile(rf"failed at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
120:    # NOTE: a third "defensive catch-all" regex (`\b(...)\.rs:(\d+):\d+`)
125:    # ``/rustc/<hash>/library/core/src/panicking.rs:N:M``. The catch-all
```

Tuple has EXACTLY 2 anchored patterns; the catch-all is gone, replaced
by an explanatory NOTE block (lines 120-127).

**3b. `derive.py:438`** (`grep "all_files = sorted"`):
```python
covered_files = {f.file_path for f in coverage.files}
all_files = sorted(covered_files)
```

The previous `sorted(covered_files | set(file_to_failed_tests.keys()))`
shape is GONE. Adjacent docstring lines 430-437 explain why.

Result: ✅ **Both Defect 3 fix layers correctly land in source.**

### Scenario 4 — Failure proximity mode E2E

```
$ cd tests/manual-test-workspace/loc-fallback-modes/localization-no-coverage
$ novetest init
$ novetest run > /tmp/sc4_run.json   # exit 3, no --coverage
$ RUN_ID=...
$ novetest localization $RUN_ID
```

| Path | Observed | Expected |
|---|---|---|
| engine_name | `"pytest"` | — |
| status | `"failed"` | — |
| summary_counts | `{collected: 3, failed: 1, passed: 2, total: 3}` | — |
| has_coverage_facts | `false` | — ✓ (no `--coverage` flag) |
| `data.localization_outcome.kind` | `"fact-set"` | `"fact-set"` ✓ |
| `data.localization_outcome.mode` | `"failure_proximity"` | `"failure_proximity"` ✓ |
| `data.localization_outcome.confidence` | `"low"` | `"low"` ✓ |
| **`data.localization_outcome.alternate_scores_available`** | **`[]`** | **`[]`** ✓ (documented deviation — failure_proximity is not SBFL) |
| `entries[0].rank` | `1` | — ✓ |
| **`entries[0].code_location.file`** | ends with **`statistics.py`** | ends with `statistics.py` ✓ (bug site) |
| **`entries[0].alternate_scores`** | **`{}`** | **`{}`** ✓ (same deviation) |

Result: ✅ **Failure proximity mode end-to-end correct.** The
no-coverage path's documented deviations (empty
`alternate_scores_available` + empty per-entry `alternate_scores`)
both surface correctly in the envelope.

### Scenario 5 — Per-test mode regression check (existing pytest path)

```
$ cd tests/manual-test-workspace/loc-fallback-modes/localization-branch
$ novetest init
$ novetest run --coverage     # pytest, per-test coverage
$ novetest localization latest
```

| Path | Observed | Expected |
|---|---|---|
| engine_name | `"pytest"` | — |
| `coverage_outcome.mapping_granularity` | `"per-test"` | `"per-test"` ✓ |
| `localization_outcome.kind` | `"fact-set"` | `"fact-set"` ✓ |
| `localization_outcome.mode` | `"sbfl_per_test"` | `"sbfl_per_test"` ✓ |
| `localization_outcome.confidence` | `"high"` | `"high"` ✓ |
| `localization_outcome.formula` | `"ochiai"` | `"ochiai"` ✓ |
| **`entries[0].rank`** | **`1`** | — ✓ |
| **`entries[0].code_location.symbol`** | **`"divide"`** 🎯 | **`"divide"`** ✓ |
| `entries[0].code_location.kind` | `"symbol"` | — ✓ (function-level — note the contrast with aggregate's file-level) |
| **`entries[0].score_raw`** | **`1.0`** | **`1.0`** ✓ (Ochiai pure top score) |
| `entries` length | `10` | — ✓ (top_n=10 in per-test mode) |

Result: ✅ **Per-test mode behavior unchanged.** The Defect 3 fix
(aggregate-mode-specific) does NOT regress per-test mode. Function-level
granularity (`kind: "symbol"`) and top-N ranking both intact.

Note: `localization latest` WORKS here because per-test runs ARE
selected by `retrieval.py:99`'s `mapping_granularity == "per-test"`
gate. Cargo aggregate runs are not (see Defect 4 below).

### Scenario 6 — Cargo coverage path for failing runs

Same envelope as Scenario 1 Step 1 — `has_coverage_facts: true`,
`coverage_outcome.kind: "fact-set"` on a `status: "failed"` cargo
run. Proves Defect 1's `--ignore-run-fail` swap (commit `18fc224`
from last cycle) is wired correctly. Without it, this entire slice
would be moot.

Result: ✅ **Coverage path for failing cargo runs unblocked.**

### Scenario 7 — Loc integration trio in isolation

Already run in Pre-flight. **5 passed in 2.30s**.

### Scenario 8 — Full gate one last time

Already run in Pre-flight. **759 + 5 skipped, mypy clean 72 src files**.

## Edge case probes

### Edge 1 — Stdlib path filter at algorithm layer (defense in depth)

```
$ grep -n "all_files = sorted" src/novetest/localization/derive.py
438:    all_files = sorted(covered_files)
```

The expression is `sorted(covered_files)` — no union with
`file_to_failed_tests.keys()`. Even if a future parser regex change
ever leaks a stdlib path past the parser, the algorithm filter would
catch it (stdlib paths aren't instrumented, so they're never in
`coverage.files`).

Result: ✅ **Defense in depth confirmed.**

### Edge 2 — Catch-all regex absent

```
$ grep -c "\b.*\.rs" src/novetest/localization/failure_proximity.py
```

Only the two anchored patterns remain (`panicked at ... .rs:N:M`,
`failed at ... .rs:N:M`). No bare `\b<file>.rs:N:M` catch-all.
Re-adding it would re-introduce Defect 3.

Result: ✅ **Catch-all gone, anchored patterns preserved.**

### Edge 3 — Tie-break behavior is moot after the filter

Pre-fix third attempt: 4-way tie at `e_f = 1` between
`arithmetic.rs`, `panicking.rs`, `function.rs`, plus one more
stdlib path. Lexicographic sort lifted stdlib paths to ranks 1-3
and pushed arithmetic.rs to rank 4. Post-fix: `entries` length = 1
(verified in Scenario 1) — only `arithmetic.rs` survives the filter
because every other covered file has `e_f = 0` and is dropped by
the score-zero gate at `_derive_aggregate` Step 5.

Result: ✅ **Tie-break is no longer load-bearing — the filter
prevents ties from forming.**

### Edge 4 — Per-test (pytest) path unaffected

Scenario 5 confirms the existing per-test path continues working
identically (same mode, same confidence, same formula, same top-1
result). The Defect 3 fix touched `_derive_aggregate` (Path B) and
the cargo parser only — Path A (`_derive_per_test`) and Path C
(`_derive_failure_proximity`) are unchanged.

Result: ✅ **Per-test mode unaffected.**

### Edge 5 — Failure proximity (no-coverage) unaffected

Scenario 4 confirms the failure_proximity path still works against
the no-coverage pytest fixture. The Defect 3 fix touched the cargo
parser regexes and `_derive_aggregate`'s candidate set, but NOT the
failure_proximity dispatch logic.

Result: ✅ **Failure proximity mode unaffected.**

## Defect 4 — confirmed in the field (not blocking)

### Probe

```
$ cd tests/manual-test-workspace/loc-fallback-modes/localization-aggregate-only
$ novetest localization latest
```

Result envelope:
```
ok: True
errors: []
data.localization_outcome.kind: "unavailable"
data.localization_outcome.reason: "run_not_analyzable"
data.localization_outcome.detail: "no analyzable runs in store (1 candidates checked)"
```

### Root cause verified

```
$ sed -n '95,99p' src/novetest/localization/retrieval.py
    coverage = get_coverage_facts(store, entry.run_record.run_reference)
    if isinstance(coverage, CoverageUnavailable):
        return False
    return coverage.mapping_granularity == "per-test"
```

Line 99 hardcodes `mapping_granularity == "per-test"`. Cargo runs
carry `mapping_granularity: "aggregate"` → this check returns False
→ `resolve_latest_analyzable_run` skips the candidate → final result
reports no analyzable run.

### Severity assessment

- **Severity**: medium (user-facing — the `latest` convenience verb
  doesn't work for the new cargo aggregate path).
- **Workaround**: pass `<run_id>` explicitly (Scenario 1 proves it
  works perfectly).
- **Pre-existing**: yes. Pre-slice, the aggregate code path was a
  placeholder, so even an explicit `<run_id>` would have failed.
  The slice's fix EXPOSES this bug; it didn't cause it.
- **Blocking?**: NO. The slice's intended scope (Defects 2 + 3) is
  complete and the gate is green at 759 + 5. Defect 4 is orthogonal
  scope.

### Recommended fix (matches Main Branch's question doc)

Two options:
- **Option A (narrow)**: change line 99 to
  `return coverage.mapping_granularity in {"per-test", "aggregate"}`.
- **Option B (broader, the better one)**: remove the granularity
  check entirely. The mode dispatch in `_derive_*` already handles
  both granularities AND the no-coverage case
  (failure_proximity), so the `retrieval.py` gate's granularity
  filter is now obsolete coupling. Simplification + capability gain
  in one change. Recommend Option B for minimum surface area.

## Issues found

**No source-level issues in this slice.** Defect 4 is a separate
pre-existing bug (the slice exposes it; not blocking this cycle).

No doc-level observations on the verification request — Main Branch's
predictions were all correct this cycle (the recurring doc-nit
pattern from the prior three cycles did NOT recur). Particularly
noting the Scenario 1 byte-for-byte match on the Ochiai score
arithmetic, all 4 alternate scores' fractions, and the entry
metadata. This is the cleanest verification doc of the cycle.

## Recommendations for PM

1. **Close the 2026-06-01 Loc fallback-modes + fixture redesign +
   Defect 3 slice as `passed`.** All 3 commits are correct; all
   8 scenarios + 5 edges verified; Defect 4 documented and not
   blocking. Phase 4 §4 #2 (sbfl_aggregate + failure_proximity
   modes) is now ✅ complete and end-to-end-verified.

2. **File Defect 4 follow-up task.** Suggested specification:
   - Title: "Loc retrieval — `resolve_latest_analyzable_run` rejects
     aggregate-mode runs"
   - Owner: localization-team
   - Acceptance: `novetest localization latest` produces a non-trivial
     fact-set against a fresh cargo aggregate run (the Scenario 1
     fixture).
   - Recommended approach: Option B above (remove the granularity
     check from `retrieval.py`).
   - Estimated size: < 30 lines (one method + a regression test).

3. **Close the four pending task slots** (per Main Branch's
   "Next Steps §2"):
   - `localization-team-2026-05-31-fallback-modes` (now landed)
   - `localization-team-2026-05-31-aggregate-fixture-redesign`
     (now landed)
   - The proactive Defect 3 fix that wasn't filed as a task (CEO's
     "확인하고 업무 진행" was the routing signal — retroactive
     bookkeeping if PM wants the audit trail)
   - `run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail` (landed
     last cycle, findings already passed; this slot may already be
     closed but worth double-checking)

4. **Update `delivery-phasing.md` Phase 4 checkboxes.**
   - §4 #2 (aggregate + failure_proximity modes) → complete ✅
   - Other Phase 4 items still pending — check the doc for status.

5. **Cycle history entry.** Notable points to capture:
   - 4-attempt cycle journey (Run-team Defect 1 → Loc fixture
     redesign → Defect 3 surfaced post-merge → CEO Option D fix).
   - Three sequential CEO option-pick decisions worked smoothly
     (Option A for fixture redesign; Option D for parser+algorithm).
   - Recurring verification-doc nit pattern (3 prior cycles) did
     NOT recur this cycle — verification doc was byte-accurate.
   - Defect 4 surfaced as orthogonal follow-up (not caused by this
     slice, but exposed by it).

6. **No `delivery-phasing.md` checkbox movement specific to this
   slice** beyond §4 #2 closure — the Defect 3 fix is a tightening,
   not a phase-gated feature.

## Confirmation matrix

| Scenario / Edge | Subject | Verdict |
|---|---|---|
| Pre-flight | Full gate (759 + 5) + mypy (72 src) + Loc trio (5/5) | ✅ |
| 1  | **Aggregate mode E2E (THE SMOKING GUN — arithmetic.rs top-1)** | ✅ |
| 2  | Redesigned fixture (Option A) — arithmetic.rs co-locates bug+test | ✅ |
| 3  | Defect 3 source fixes (parser + algorithm) | ✅ |
| 4  | Failure proximity mode E2E (pytest no-coverage) | ✅ |
| 5  | Per-test mode regression check (pytest with coverage) | ✅ |
| 6  | Cargo coverage path for failing runs | ✅ |
| 7  | Loc integration trio | ✅ |
| 8  | Full gate confirmation | ✅ |
| E1 | Stdlib filter at algorithm layer (defense in depth) | ✅ |
| E2 | Catch-all regex absent | ✅ |
| E3 | Tie-break is moot after filter | ✅ |
| E4 | Per-test path unaffected | ✅ |
| E5 | Failure proximity path unaffected | ✅ |
| Defect 4 | `localization latest` rejects aggregate runs | ⚠️ confirmed in field — separate slice |

**Final verdict: passed.** Phase 4 §4 #2 lands successfully after
four attempts. `src/arithmetic.rs` ranks top-1 in the cargo aggregate
e2e. Two complementary defenses (parser + algorithm) eliminate
stdlib pollution from rankings. Failure proximity mode added as the
no-coverage fallback. Per-test mode unchanged. Defect 4 documented
as orthogonal follow-up. Cycle journey records four attempts but
final result is clean.

---

Filed by: novetest-manual-test-team
Date: 2026-06-01
Cycle: 2026-06-01 single-slice (Loc fallback-modes + fixture
       redesign + Defect 3 fix) — all three commits passed.
       Defect 4 surfaced as orthogonal follow-up.
