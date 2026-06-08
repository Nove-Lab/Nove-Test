---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-08
slug: fixed-tests-spec
related:
  - agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md
  - agent-comms/handoffs/regression-team-2026-06-08-fixed-tests-spec.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
---

# Verification — Regression `fixed_tests` spec (intent verdict + contract strengthening)

## Verdict (carried from handoff)

**INTENT** — not a bug. Zero source changes. The D6 Scenario F+ observation
(`summary.regressed == 0 AND summary.fixed == 0` despite one run failing and
another passing) is the **correct behavior under disjoint `node_id` test
sets**: per-test signal lives in `summary.added` + `summary.removed`, not in
`summary.regressed` / `summary.fixed`. The team's slice strengthens the
contract doc + pins integration tests around the existing behavior.

## Merged commit

- **Tip**: `55fd693 comms: handoff for regression fixed-tests-spec slice (intent verdict)`
- **Functional commit**: `94c1c7a docs(regression): pin transition-detection set semantics + D6 F+ tests (intent verdict)`
- **Base (before rebase)**: `4184cd1`
- **Base (after rebase onto current main)**: `1325307 comms: verification (defect7 failure_proximity warning-loop)`
- **Merge type**: FF-merge after rebase. `WORKLOG.md` conflict resolved
  (both 2026-06-08 entries preserved; regression entry on top as the
  newer-in-main-history commit, separated by `---`).
- **Files**: 5 changed, +609 / −0

## Source handoff consumed

- `agent-comms/handoffs/regression-team-2026-06-08-fixed-tests-spec.md`

## What landed

A **docs + tests** slice. Zero `src/` changes — the existing
`compare.py::_build_transitions` already implements the intended union-walk
semantics; the gap was that the contract did not document the rule, so
operators encountering the disjoint-set case had no reference for
interpretation.

1. **`design/interace-contract/regression.md`** (+29 lines, new section
   "Transition Detection Semantics"):
   - Pins the union-walk rule + reachability matrix (both / target-only /
     baseline-only `node_id` → which of the 9 categories are reachable).
   - States two binding consequences explicitly:
     a. `fixed` / `regressed` require same `node_id` on both sides.
     b. Disjoint test sets are still a valid comparison; both counts MAY
        be zero. Consumers MUST NOT read `summary.regressed == 0 AND
        summary.fixed == 0` as "nothing changed" without also checking
        `summary.added` and `summary.removed`.
   - Cross-references decision `2026-05-26-regression-facts-json-layout.md`
     §C.7 for the "newly-introduced failures" consumer filter.

2. **`tests/unit/regression/test_compare.py`** (+52 lines, 1 new test
   `test_disjoint_test_sets_yield_zero_regressed_and_zero_fixed`):
   - Placed adjacent to the 9 existing `test_category_*` cases so the
     canonical grep target for transition semantics carries the D6
     resolution.

3. **`tests/integration/regression/test_transition_set_semantics.py`** (NEW,
   276 lines, 4 integration tests at the Memory + Persistence + Engine seam):
   a. `test_same_node_id_fail_to_pass_populates_fixed` — symmetric positive
      control.
   b. `test_same_node_id_pass_to_fail_populates_regressed` — the symmetric
      regressed counterpart.
   c. `test_disjoint_test_sets_yield_empty_fixed_and_regressed` — the **D6
      Scenario F+ reproducer** at full E2E depth.
   d. `test_mixed_sets_classify_each_node_id_independently` — shared
      transition + target-only fail + baseline-only pass; proves each
      `node_id` is classified independently per the union walk.

## Pre-merge test gate (on merged main = `55fd693`)

The full gate was re-run after WORKLOG.md conflict resolution (charter mandate):

| Check | Result |
| --- | --- |
| `uv run mypy --strict src/novetest` | **Success: no issues found in 92 source files** |
| `uv run pytest -q tests/unit tests/integration --deselect tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` | **1191 passed, 23 skipped, 1 deselected in 32.66s** |

Delta vs the post-localization gate (1186 passed): **+5 new tests** (1 unit +
4 integration in the regression scope). All other tests unchanged.

§2.5 equip-and-exercise gate does NOT fire for this slice (task brief
§"§2.5"). The single deselected test is the same `.NET SDK 8.0+`-bound
xUnit-v3 deferral test that fails identically on the unmodified base
`4184cd1` — environmental, not a regression (handoff Verification §"Full
unit + integration sweep" confirms).

## Wire-level envelope shape (verbatim, pinned from merged source)

The regression compare envelope shape is unchanged by this slice (zero src
edits). Source-pinned at `src/novetest/cli/app.py:630` and
`src/novetest/models/regression_fact_set.py:132-153`. Schema documented in
the new contract section at `design/interace-contract/regression.md:43-68`.

For `novetest regression compare <baseline_run_id> <target_run_id>`:

```json
{
  "command": "regression",
  "ok": true,
  "data": {
    "regression_outcome": {
      "kind": "fact-set",
      "summary": {
        "regressed": <int>,
        "fixed": <int>,
        "still_failing": <int>,
        "still_passing": <int>,
        "still_skipped": <int>,
        "newly_skipped": <int>,
        "newly_active": <int>,
        "added": <int>,
        "removed": <int>,
        "total_baseline_tests": <int>,
        "total_target_tests": <int>
      },
      "test_transitions": [
        {
          "category": "<one of: regressed | fixed | still_failing | still_passing | still_skipped | newly_skipped | newly_active | added | removed>",
          "node_id": "<string>",
          "baseline_outcome": "<string | null>",
          "target_outcome": "<string | null>",
          "...": "..."
        }
      ],
      "...": "..."
    }
  }
}
```

When `node_id` is target-only, `baseline_outcome` is `null` (model invariant
`baseline_outcome is None iff category == "added"`, pinned at
`regression_fact_set.py:69` docstring). Symmetrically `target_outcome` is
`null` when `category == "removed"`.

## Verification steps — for Manual Test

The handoff §"Manual Test recommendations" lists three suggested scenarios;
they're reproduced here with concrete commands + expected envelope paths.

### Scenario A — Contract readability check (doc-only, no CLI)

Read `design/interace-contract/regression.md` §"Transition Detection
Semantics" (lines 43–68) from the perspective of an operator who saw the D6
Scenario F+ surprise.

**Probe questions:**
- Does it answer "why are `summary.regressed` and `summary.fixed` both zero
  when one run failed and the other passed?" without requiring the reader
  to open `decisions/2026-05-26-regression-facts-json-layout.md`?
- Are the two binding consequences (a) and (b) discoverable in a single
  scroll?
- Does the §"Consumer guidance for newly-introduced failures" subsection
  make the Localization-side filter obvious?

**Pass criterion:** an operator who saw D6 F+ can reach "the disjoint-set
case is intentional; check `summary.added` + `summary.removed` for the
per-test signal" in under 60 seconds of reading.

### Scenario B — End-to-end disjoint-set reproducer via CLI (D6 F+ in production)

Pin the documented behavior at the CLI subprocess boundary against a fresh
project store.

```bash
cd $(mktemp -d -t novetest-reg-verify-XXXXXX)
# Stage two intentionally-disjoint test files
cat > test_foo.py <<'PY'
def test_foo_one(): assert True
def test_foo_two(): assert True
PY
cat > test_bar.py <<'PY'
def test_bar_one(): assert True
def test_bar_two(): assert True
PY
python -m venv .venv && . .venv/bin/activate && pip install pytest >/dev/null

novetest init
RUN1=$(novetest run test_foo.py -o json | jq -r '.data.run_record.run_reference.run_id')
RUN2=$(novetest run test_bar.py -o json | jq -r '.data.run_record.run_reference.run_id')

novetest regression compare "$RUN1" "$RUN2" -o json > /tmp/reg-disjoint.json
```

**Expected envelope** (`jq` selectors against `/tmp/reg-disjoint.json`):

| `jq` selector | Expected value |
| --- | --- |
| `.command` | `"regression"` |
| `.ok` | `true` |
| `.data.regression_outcome.kind` | `"fact-set"` |
| `.data.regression_outcome.summary.regressed` | `0` |
| `.data.regression_outcome.summary.fixed` | `0` |
| `.data.regression_outcome.summary.added` | `>= 2` (the 2 bar tests) |
| `.data.regression_outcome.summary.removed` | `>= 2` (the 2 foo tests) |
| `.data.regression_outcome.test_transitions \| length` | `>= 4` |
| `.data.regression_outcome.test_transitions[] \| .category` (set) | `["added", "removed"]` only — NO `regressed`, NO `fixed` |

**Headline assertion** (what the new contract section pins):
```bash
jq '.data.regression_outcome.summary | {regressed, fixed, added, removed}' /tmp/reg-disjoint.json
# Expected: {regressed: 0, fixed: 0, added: 2, removed: 2}
```

This is the CLI-level translation of integration test
`test_disjoint_test_sets_yield_empty_fixed_and_regressed`.

### Scenario C — Same-set sanity check (the populated case)

Confirm the contract pin does NOT accidentally suppress the populated
`fixed` / `regressed` cases.

```bash
cd $(mktemp -d -t novetest-reg-samesetXXX)
cat > test_xyz.py <<'PY'
def test_flippable(): assert True
def test_stable(): assert True
PY
python -m venv .venv && . .venv/bin/activate && pip install pytest >/dev/null

novetest init
RUN_PASS=$(novetest run test_xyz.py -o json | jq -r '.data.run_record.run_reference.run_id')

# Flip the first test to fail
cat > test_xyz.py <<'PY'
def test_flippable(): assert False
def test_stable(): assert True
PY
RUN_FAIL=$(novetest run test_xyz.py -o json | jq -r '.data.run_record.run_reference.run_id')

# pass→fail comparison (PASS as baseline, FAIL as target)
novetest regression compare "$RUN_PASS" "$RUN_FAIL" -o json > /tmp/reg-regressed.json
# fail→pass comparison (FAIL as baseline, PASS as target)
novetest regression compare "$RUN_FAIL" "$RUN_PASS" -o json > /tmp/reg-fixed.json
```

**Expected on `/tmp/reg-regressed.json`** (pass→fail):
- `.data.regression_outcome.summary.regressed >= 1` (the flippable test)
- `.data.regression_outcome.summary.fixed == 0`
- `.data.regression_outcome.summary.added == 0`
- `.data.regression_outcome.summary.removed == 0`
- Exactly one `.test_transitions[] | select(.category == "regressed")` with
  `node_id` ending in `test_flippable`

**Expected on `/tmp/reg-fixed.json`** (fail→pass):
- `.data.regression_outcome.summary.fixed >= 1`
- `.data.regression_outcome.summary.regressed == 0`
- `.data.regression_outcome.summary.added == 0`
- `.data.regression_outcome.summary.removed == 0`
- Exactly one `.test_transitions[] | select(.category == "fixed")` with
  `node_id` ending in `test_flippable`

### Scenario D — Mixed-set independence (recommended bonus)

Combine the two patterns: one shared test that flips + one target-only test
+ one baseline-only test. Confirms each `node_id` is classified
independently per the union walk.

```bash
cd $(mktemp -d -t novetest-reg-mixedXXX)
# Run 1: baseline. shared_test passes, baseline_only_test passes
cat > test_set.py <<'PY'
def test_shared(): assert True
def test_baseline_only(): assert True
PY
python -m venv .venv && . .venv/bin/activate && pip install pytest >/dev/null
novetest init
RUN_BASE=$(novetest run test_set.py -o json | jq -r '.data.run_record.run_reference.run_id')

# Run 2: target. shared_test FAILS, baseline_only gone, target_only_test FAILS
cat > test_set.py <<'PY'
def test_shared(): assert False
def test_target_only(): assert False
PY
RUN_TGT=$(novetest run test_set.py -o json | jq -r '.data.run_record.run_reference.run_id')

novetest regression compare "$RUN_BASE" "$RUN_TGT" -o json > /tmp/reg-mixed.json
```

**Expected on `/tmp/reg-mixed.json`**:
- `.data.regression_outcome.summary.regressed >= 1` (test_shared pass→fail)
- `.data.regression_outcome.summary.added >= 1` (test_target_only)
- `.data.regression_outcome.summary.removed >= 1` (test_baseline_only)
- `.data.regression_outcome.summary.fixed == 0`

Three distinct categories all populated in one envelope. Confirms the union
walk's per-`node_id` independence.

## Critical edge cases worth probing

1. **Same-set, target_only outcome IS fail-like**: the contract treats the
   "test newly appeared AND fails" case as `category="added"`, NOT
   `category="regressed"`. Localization callers wanting newly-introduced
   failures must use the consumer filter from `design/interace-contract/
   regression.md:63-66`:
   ```
   category in {"regressed", "still_failing"}
     OR (category == "added" AND target_outcome in fail-like)
   ```
   If Manual Test discovers an existing Localization or downstream consumer
   that filters ONLY on `category == "regressed"` and silently misses the
   "added + fail-like" case, surface as a follow-up finding (not a blocker
   for this slice — the contract makes the rule discoverable).

2. **Summary `total_baseline_tests` / `total_target_tests` invariants**: the
   regression handoff doesn't probe these but the model docstring at
   `regression_fact_set.py:135-141` pins them as `in_both + removed` and
   `in_both + added` respectively. A quick `jq` check on the disjoint-set
   envelope (Scenario B) confirms:
   ```
   summary.total_baseline_tests == 0 + removed == removed
   summary.total_target_tests == 0 + added == added
   ```
   These should sanity-check on Scenarios B/C/D.

3. **`regression latest` envelope vs `regression compare`**: `regression
   latest` resolves the pair from store, but the resulting envelope wraps
   the same `RegressionFactSet` (same `regression_outcome` payload shape).
   Manual Test should exercise `latest` once on a store with at least 2
   runs to confirm the shape parity:
   ```bash
   novetest regression latest -o json | jq '.data.regression_outcome | keys'
   ```
   Same top-level keys as the `compare` envelope.

4. **Unavailable case** (no comparable baseline): if Manual Test runs
   `regression latest` against a fresh store with only ONE run, the envelope
   carries `.data.regression_outcome.kind == "unavailable"` with
   `reason == "no-comparable-baseline"` (pinned at
   `cli/app.py:617-654`). This is unchanged by the slice but worth a
   negative-control pin.

## Anything not obvious during merge

- **WORKLOG.md conflict resolution**: regression entry placed ABOVE
  localization entry, separated by a `---` divider, because regression
  commits land later in main history (charter convention: newest commit on
  top). Both entries preserved verbatim — no content lost.
- **Rebase, not merge commit**: regression branch was rebased onto current
  main (`1325307`) BEFORE FF-merge, per charter "Default: rebase clean
  linear history." Two regression commits (`94c1c7a`, `55fd693`) replayed
  cleanly; only WORKLOG.md required hand-resolution.
- **Source-file count unchanged**: 92 mypy source files before and after
  this slice (no new `src/` files; docs + tests only). Cross-check: the
  localization slice also kept 92 (it modified existing `cli/app.py`).
- **Zero src changes is the headline**: this is the cleanest possible
  "intent verdict" delivery. The handoff §"Evidence supporting INTENT"
  enumerates 4 source-of-truth surfaces that all agree on the union-walk
  semantics; the slice adds a 5th (the new contract section) to close the
  documentation gap.

## Reference

- Task: `agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md`
- Handoff: `agent-comms/handoffs/regression-team-2026-06-08-fixed-tests-spec.md`
- Original D6 F+ observation:
  `agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`
  §"Regression engine subtle question (carry-forward to Regression team)"
- 9-category taxonomy decision:
  `agent-comms/decisions/2026-05-26-regression-facts-json-layout.md` §3,
  §C.7
- New contract section: `design/interace-contract/regression.md` §43-68
