---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-01
slug: latest-aggregate-discovery-defect4
related:
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - src/novetest/localization/retrieval.py
  - src/novetest/localization/derive.py
---

# Task: `novetest localization latest` — discover aggregate-mode-eligible runs (Defect 4)

## TL;DR

`novetest localization latest` returns `kind: "unavailable"`,
`reason: "run_not_analyzable"` against cargo aggregate runs even
though `novetest localization <run_id>` on the same run produces a
correct ranked finding. Pre-existing bug **exposed** (not caused) by
the 2026-06-01 fallback-modes slice (`05f86bc`) — the `sbfl_aggregate`
mode now produces real findings, but the `latest` resolver still
gates on per-test coverage only.

**Surgical fix**: ~5 lines source change in `retrieval.py:97-99` +
~1 docstring update + 1 integration test exercising
`localization latest` against a non-per-test fixture.

Filed by Manual Test in their 2026-06-01 cycle close findings;
analyzed by Main Branch but flagged as Main Branch overreach (their
analysis is supplementary context — Manual Test's findings are the
canonical signal per `history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md`
§"Process correction").

## Why this slice exists (product framing)

`novetest localization latest` is a convenience verb that walks the
Run History newest-first and picks the latest "analyzable" run.
Currently the gate accepts ONLY per-test coverage. But this cycle's
slice just added two NEW modes (`sbfl_aggregate`,
`failure_proximity`) that work fine without per-test coverage.

Net effect today: **`localization latest` is broken for 3 of 4
supported languages** (cargo / go / jest produce aggregate coverage;
runs without `--coverage` produce no coverage). Only pytest with
`--coverage` works. The explicit `<run_id>` path works for all
modes; the `latest` discoverability path is the gap.

This is the **last open piece of Phase 4 §4 #2's user-facing
surface**. After this fix, all 4 supported languages have a
working `latest` flow.

## Empirical reproduction (verbatim from Manual Test 2026-06-01 findings)

```sh
. "$HOME/.cargo/env"
cd /tmp/lao-defect4   # cp from tests/fixtures/projects/localization-aggregate-only/
novetest init
novetest run --coverage   # → status: failed, has_coverage_facts: true

# Explicit <run_id> path — works correctly:
RUN_ID=$(... extract from run record ...)
novetest localization "$RUN_ID"
# → kind: "fact-set", mode: "sbfl_aggregate", entries[0].rank: 1
#   entries[0].code_location.file: "src/arithmetic.rs"

# latest verb on SAME store — broken:
novetest localization latest
# →
{
  "data": {
    "localization_outcome": {
      "kind": "unavailable",
      "reason": "run_not_analyzable",
      "detail": "no analyzable runs in store (1 candidates checked)",
      "run_reference": null
    }
  },
  "ok": true,
  "errors": []
}
```

Manual Test also confirmed (Bonus probe from their findings) the
same `run_not_analyzable` symptom recurs for the
`localization-no-coverage` fixture's `failure_proximity` mode — so
this is actually two related sub-issues, both flowing from the
same gate.

## Root cause analysis (verified against merged tip `05f86bc`)

**File**: `src/novetest/localization/retrieval.py:63-99`
(`check_localization_availability`).

**The over-restrictive gate** (last line of the function):

```python
def check_localization_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Cheap precondition probe for Orchestration eligibility evaluation.

    Returns ``True`` iff ALL three preconditions for the per-test SBFL
    path are satisfied:
    ...
    3. Coverage Facts exist for the run AND
       ``mapping_granularity == "per-test"``.
    """
    # ... preconditions 1-2 ...
    coverage = get_coverage_facts(store, entry.run_record.run_reference)
    if isinstance(coverage, CoverageUnavailable):
        return False  # ← would also break failure_proximity discoverability
    return coverage.mapping_granularity == "per-test"  # ← LINE 99
```

This function is called by `resolve_latest_analyzable_run`
(somewhere around `derive.py:1043` based on Manual Test's grep) which
walks `list_run_history` newest-first. For each candidate, if the
gate returns `False`, skip; if no candidate passes, return
`LocalizationUnavailable(reason=REASON_RUN_NOT_ANALYZABLE)`.

**Why it was correct pre-2026-06-01**: `_derive_aggregate` and
`_derive_failure_proximity` were `LocalizationUnavailable`-returning
placeholders. Per-test coverage WAS the only real path; the gate
matched reality.

**Why it's wrong post-2026-06-01**: mode dispatch in `derive.py`
now handles ALL three cases (per-test / aggregate / no-coverage)
with real derive logic. The gate hasn't caught up.

## Scope (what this slice DOES)

### 1. Relax the gate in `retrieval.py`

Replace `retrieval.py:97-99` (single function-tail change):

**From**:
```python
coverage = get_coverage_facts(store, entry.run_record.run_reference)
if isinstance(coverage, CoverageUnavailable):
    return False  # ← rejects failure_proximity discoverability
return coverage.mapping_granularity == "per-test"  # ← rejects aggregate
```

**To**:
```python
# Mode dispatch in derive.py handles all coverage states:
#   per-test            → sbfl_per_test  (high confidence)
#   aggregate / etc     → sbfl_aggregate  (medium confidence)
#   CoverageUnavailable → failure_proximity  (low confidence)
# So at this layer, has-failed-tests + not-tombstoned are sufficient
# preconditions; coverage shape is the mode dispatcher's concern.
return True
```

The `coverage = get_coverage_facts(...)` lookup itself becomes
unused — if the implementing team prefers, remove the unused
lookup; if they prefer to keep the variable for log/debug purposes,
adding `del coverage` or just leaving it as a no-op is acceptable
(mypy strict will catch unused-variable if any).

### 2. Update the docstring

`retrieval.py:67-79` docstring currently enumerates the per-test
gate semantics. Update to reflect broader analyzability:

```python
"""Cheap precondition probe for Orchestration eligibility evaluation.

Returns ``True`` iff the run has SOMETHING the Localization engine
can analyze:
1. ``retrieve_run_evidence`` succeeds AND the entry is not tombstoned.
2. The Run Record has at least one failed test result.

Coverage shape is NOT gated here — `derive_localization_findings`
dispatches across all three modes (per-test / aggregate /
failure_proximity) based on `CoverageFactSet.mapping_granularity`
or its absence. Pre-2026-06-01 this function rejected non-per-test
coverage; per `history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md`
§"Defect 4" the gate was relaxed to match the new mode dispatch.
"""
```

(Exact docstring wording at implementer's discretion; the
load-bearing change is reflecting the post-relaxation semantics.)

### 3. Add integration test for the `latest` path on non-per-test fixtures

**Where**: extend
`tests/integration/localization/test_mode_selection_per_engine.py`
OR create a new module
`tests/integration/localization/test_latest_verb_non_per_test.py`.

The existing `test_mode_selection_per_engine.py` already covers
mode dispatch via direct `derive_localization_findings` calls.
This slice should add tests for the `derive_latest_localization` /
`localization latest` CLI verb against:

1. `localization-aggregate-only` fixture → assert `latest` returns
   `kind: "fact-set"`, `mode: "sbfl_aggregate"` (NOT
   `kind: "unavailable"`)
2. `localization-no-coverage` fixture → assert `latest` returns
   `kind: "fact-set"`, `mode: "failure_proximity"` (NOT
   `kind: "unavailable"`)
3. `localization-branch` (per-test) regression-pin → still
   `kind: "fact-set"`, `mode: "sbfl_per_test"` (unchanged)

Use the existing fixture infrastructure; skip-guard on
toolchain presence for the cargo fixture per existing pattern.

### 4. Update at most 1-2 unit tests if any explicitly assert the per-test gate

`grep -rn "check_localization_availability" tests/unit/`

If any unit test asserts the function returns `False` for an
aggregate-mode-coverage run, update the assertion to `True` (the
new contract). Likely scope: 0-2 tests.

## Out of scope (do NOT touch)

- **`_derive_aggregate`, `_derive_failure_proximity`, `_derive_per_test`**
  — all three already work correctly. The bug is purely in the gate.
- **Coverage / Run / Memory / Orchestration source territories** —
  Localization-only slice.
- **Envelope shape** — output envelope for the `latest` verb is
  the same as `<run_id>` verb; just `mode` will now reflect
  aggregate/failure_proximity for non-per-test runs.
- **Optional: removing the `get_coverage_facts` lookup at line 96**
  — if you keep the lookup as a no-op, fine. If you remove it,
  also fine. Implementer's call.
- **Phase 4 §4 #3 (perf NFR)** — separate slice, future.

## Pre-flight checks (before opening handoff)

1. **Full gate green** on equipped host:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline at this cycle's tip (`6aa26f6` after push): **759 + 5**
     on equipped host (676 + 7 on Rust-less).
   - Your tip = baseline + new integration tests. No regressions.
2. **mypy strict clean**: `uv run mypy` → no issues, 72 source
   files (unchanged).
3. **Empirical smoke**: reproduce the Defect 4 symptom pre-fix,
   then confirm post-fix:
   ```sh
   . "$HOME/.cargo/env"
   cp -r tests/fixtures/projects/localization-aggregate-only /tmp/lao-d4
   cd /tmp/lao-d4
   uv run --project /home/yjshin/dev/Nove-Test novetest init
   uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage
   uv run --project /home/yjshin/dev/Nove-Test novetest localization latest
   # Post-fix expected: kind: "fact-set", mode: "sbfl_aggregate",
   #                    entries[0].code_location.file: "src/arithmetic.rs"
   ```
   Pre-fix this would return `kind: "unavailable"`, `reason: "run_not_analyzable"`.

4. **failure_proximity discoverability smoke**:
   ```sh
   cp -r tests/fixtures/projects/localization-no-coverage /tmp/lnc-d4
   cd /tmp/lnc-d4
   uv run --project /home/yjshin/dev/Nove-Test novetest init
   uv run --project /home/yjshin/dev/Nove-Test novetest run     # no --coverage
   uv run --project /home/yjshin/dev/Nove-Test novetest localization latest
   # Post-fix expected: kind: "fact-set", mode: "failure_proximity",
   #                    entries[0].code_location.file ends with "statistics.py"
   ```

5. **Per-test regression-pin**: existing `localization-branch` flow
   still produces `mode: "sbfl_per_test"` via `localization latest`
   (unchanged behavior).

## DoD

- [ ] `retrieval.py:check_localization_availability` returns `True`
      for runs with failed tests regardless of coverage shape (the
      relaxed gate).
- [ ] Docstring updated to reflect the new semantics.
- [ ] 3 new integration tests (or 1 new + 2 parametrized) covering
      `latest` verb for all 3 mode-dispatch paths.
- [ ] Pre-flight smoke A (cargo aggregate) PASSES: `localization
      latest` returns `kind: "fact-set"`, `mode: "sbfl_aggregate"`.
- [ ] Pre-flight smoke B (no-coverage pytest) PASSES: `localization
      latest` returns `kind: "fact-set"`, `mode: "failure_proximity"`.
- [ ] Pre-flight smoke C (per-test pytest) regression-pin PASSES:
      `mode: "sbfl_per_test"` unchanged.
- [ ] Existing unit tests pass; mypy --strict clean; full suite
      green.

## Handoff format

`agent-comms/handoffs/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Pre-flight evidence A + B + C** — paste the verbatim
   `localization latest` envelopes for all 3 fixtures.
3. **`delivery-phasing.md` checkbox implications**: none directly
   (Phase 4 §4 #2 already ticked at the prior cycle close; this
   slice just closes a discoverability bug exposed by it). The
   slice marks the END of the Phase 4 §4 modes-related work
   (everything from the strategy doc §2 mode table now works
   end-to-end across all 3 modes AND both verbs).
4. **Open questions for PM** — any surprises during implementation.

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff.
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + new `agent-comms/` files + `INDEX.md`
   alongside source.

## Cross-references

- **History of the slice that exposed Defect 4**:
  `agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md`
  §"Defect 4 — orthogonal pre-existing bug, carry-forward".
- **Manual Test 2026-06-01 findings (where Defect 4 was canonically
  observed)**: deleted at the 2026-06-01 cycle close; reproduction
  inlined in this brief's §"Empirical reproduction".
- **Strategy doc** (the 3-mode table this slice's gate-relaxation
  reflects):
  `design/implementation-plan/localization-strategy.md` §2.
- **Envelope freeze v1** (no envelope changes in this slice):
  `agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md`.
