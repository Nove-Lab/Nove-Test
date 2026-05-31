---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-01
slug: localization-latest-aggregate-discovery
related:
  - agent-comms/handoffs/localization-team-2026-06-01-aggregate-fixture-redesign-and-defect3.md
  - agent-comms/verifications/2026-06-01-localization-aggregate-fixture-redesign-and-defect3.md
  - src/novetest/localization/retrieval.py
  - src/novetest/localization/derive.py
---

# Question: `localization latest` doesn't recognize aggregate-mode-eligible cargo runs (Defect 4)

> **⚠ Process correction (added 2026-06-01 post-filing)**: This question was
> filed by Main Branch as **overreach into Manual Test's exploratory
> territory**. Main Branch's charter limits "after merge" probing to
> envelope-path capture for verification doc scenarios; running
> `novetest localization latest` and investigating the resulting
> failure mode down to the source line is testing work, not merge
> verification. Per CEO directive 2026-06-01: the root-cause analysis +
> 5-line suggested fix below are retained for data value, but **Manual
> Test should independently verify Defect 4 reproduction via their own
> scenarios and add their perspective to `findings/`**. The verification
> doc's Scenario 1b prompts that independent check. PM should weight
> Manual Test's findings as the canonical signal; this question is
> supplementary context. Process correction logged so future cycles
> respect the Main Branch / Manual Test boundary.


## TL;DR

This cycle's Loc slice (`05f86bc`) made `sbfl_aggregate` mode work
end-to-end for cargo. `novetest localization <run_id>` returns a
correct ranked finding. But `novetest localization latest` returns
`kind: "unavailable"`, `reason: "run_not_analyzable"` for the same
cargo run.

Root cause: `src/novetest/localization/retrieval.py:99` hardcodes
`return coverage.mapping_granularity == "per-test"`. Cargo's
`"aggregate"` granularity is rejected; the resolver thinks no
analyzable run exists.

This is a **pre-existing bug that surfaced post-merge** of the
Localization team's parallel cycle. Not a regression caused by the
slice — the slice exposed it by making aggregate-mode finally work.

**Not blocking** this cycle's merge (gate green at 759+5; explicit
`<run_id>` works perfectly). Filing for follow-up.

## Empirical reproduction (on equipped host, post-merge `05f86bc`)

```
$ cd /tmp/lao-final  # cp from tests/fixtures/projects/localization-aggregate-only/
$ novetest init
$ novetest run --coverage  # → status: failed, has_coverage_facts: true, coverage_outcome.kind: fact-set
$ novetest localization 01KSZ9H5KAV0P74FTMD2ZSZ7AX  # explicit run_id
... kind: fact-set, mode: sbfl_aggregate, confidence: medium ...
... entries[0].rank: 1, file: 'src/arithmetic.rs', primary_line: 53 ...

$ novetest localization latest  # SAME store, SAME run
{
  "command": "localization.latest",
  "data": {
    "localization_outcome": {
      "detail": "no analyzable runs in store (1 candidates checked)",
      "kind": "unavailable",
      "reason": "run_not_analyzable",
      "run_reference": null
    }
  },
  ...
}

$ # AFTER the explicit <run_id> derive cached the findings:
$ novetest localization latest  # still
... reason: "run_not_analyzable" — not a caching issue, real gating
```

## Root cause

`src/novetest/localization/retrieval.py:63-99`:

```python
def check_localization_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Cheap precondition probe for Orchestration eligibility evaluation.

    Returns ``True`` iff ALL three preconditions for the per-test SBFL
    path are satisfied:

    1. ``retrieve_run_evidence`` succeeds AND the entry is not tombstoned.
    2. The Run Record has at least one failed test result.
    3. Coverage Facts exist for the run AND
       ``mapping_granularity == "per-test"``.
    ...
    """
    # ... preconditions 1-2 ...
    return coverage.mapping_granularity == "per-test"  # ← LINE 99
```

This function is called by `resolve_latest_analyzable_run`
(`derive.py:1043`) which walks `list_run_history` newest-first. For
each candidate run, the gate is `check_localization_availability` ==
`True`. If no candidate passes, the resolver returns
`LocalizationUnavailable(reason=REASON_RUN_NOT_ANALYZABLE)`.

The docstring even cites the per-test-only constraint explicitly:
"per-test coverage path".

## Why this wasn't caught by the team's tests

The team's integration tests cover:
- `test_aggregate_mode_e2e.py::test_aggregate_mode_ranks_buggy_file_top`
  — uses `derive_localization_findings(store, run_reference)`
  directly (the `<run_id>` path).
- `test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top`
  — same direct-derive pattern.
- `test_mode_selection_per_engine.py::test_mode_selection_routes_to_expected_mode`
  — three cases parameterized over fixtures, all using direct
  `derive_localization_findings`.

None exercise `derive_latest_localization` or the CLI's `latest` verb
against a non-per-test fixture. The team's test suite is correct for
the `<run_id>` path; the `latest` path's gating is orthogonal.

The CLI integration tests (`tests/integration/cli/test_localization_e2e.py`
from the prior CLI slice) use the `localization-branch` fixture
(pytest, per-test coverage), so `localization latest` works there.
No cargo fixture exercises `latest`.

## What "analyzable" should mean post-this-slice

Pre-this-slice, "analyzable" was correctly equivalent to "per-test
coverage" because `_derive_aggregate` and `_derive_failure_proximity`
were `LocalizationUnavailable`-returning placeholders. Now both
algorithms produce real findings. The gate should reflect that:

| Coverage state | Failed tests | Mode | Should `latest` consider analyzable? |
|---|---|---|---|
| `per-test` coverage | ≥1 | `sbfl_per_test` | YES (already True) |
| `aggregate` (cargo/jest/go) | ≥1 | `sbfl_aggregate` | YES (currently False — Defect 4) |
| `per-test-file` / `per-test-class` | ≥1 | `sbfl_aggregate` | YES (currently False) |
| No coverage at all | ≥1 | `failure_proximity` | YES (currently False — `coverage is CoverageUnavailable` returns False at line 98) |
| Any coverage state | 0 failed tests | n/a | NO (correctly False at line 94) |
| Tombstoned | * | n/a | NO (correctly False at line 90) |

So `check_localization_availability` is over-restrictive in TWO ways:
1. Rejects non-`per-test` granularities (Defect 4 proper).
2. Rejects runs with no coverage at all (would break
   failure_proximity discoverability — call it Defect 4b).

## Suggested fix

Replace `retrieval.py:97-99` (single-line change at the return):

```python
coverage = get_coverage_facts(store, entry.run_record.run_reference)
if isinstance(coverage, CoverageUnavailable):
    return False  # ← would break failure_proximity discoverability
return coverage.mapping_granularity == "per-test"  # ← rejects aggregate
```

with:

```python
# Mode dispatch in derive.py handles all coverage states:
#   per-test         → sbfl_per_test
#   aggregate / etc  → sbfl_aggregate  (Defect 3 fix made this work)
#   CoverageUnavailable → failure_proximity (always works given has-failed-tests)
# So at this layer, has-failed-tests + not-tombstoned are sufficient.
return True
```

Plus update the docstring lines 67-79 to reflect the broader
analyzability semantics, AND add an integration test that runs
`localization latest` against a cargo fixture (or a no-coverage
fixture for the failure_proximity case).

Risk analysis:
- A run with covered but no failed tests was already correctly
  rejected (`has_failed = ...; if not has_failed: return False`) —
  this isn't relaxed.
- A tombstoned run was already correctly rejected (`if
  entry.tombstoned_at is not None: return False`) — this isn't
  relaxed.
- No risk of false positives — every other state has a working
  derive path now.

The fix is ~5 lines including the docstring update.

## Why this is "Defect 4" and not "Defect 5/6"

Conventionally numbering this cycle's defect chain:
- Defect 1 (cargo-llvm-cov `--no-fail-fast`): Run team, fixed at `18fc224`.
- Defect 2 (fixture co-location): Loc team, fixed at `3ccfd72`.
- Defect 3 (parser catch-all + algorithm stdlib filter): Loc team,
  fixed at `05f86bc`.
- **Defect 4** (`latest` verb's aggregate/no-coverage discoverability):
  pre-existing, this question.

## Recommended path forward

1. **This cycle's merge stays** — gate is green at 759+5, the slice's
   intended scope (Defects 2 + 3) is fully closed, and the explicit
   `<run_id>` path works perfectly. Defect 4 is orthogonal.
2. **PM dispatches a Loc team fix-up slice** implementing the 5-line
   fix above + adding ≥1 integration test exercising `localization
   latest` for a non-per-test fixture (cargo aggregate or
   pytest-without-coverage).
3. **No CI matrix change needed** — Main Branch's gate would catch a
   regression of this if `localization latest` were ever wired into
   an integration test. The fix should include that wiring.

---

Filed by: novetest-main-branch-team
Date: 2026-06-01
