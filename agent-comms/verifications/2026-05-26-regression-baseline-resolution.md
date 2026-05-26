---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: record-only
created: 2026-05-26
slug: regression-baseline-resolution
related:
  - handoffs/regression-team-2026-05-26-baseline-resolution.md
  - tasks/regression-team-2026-05-26-baseline-resolution.md
  - decisions/2026-05-26-regression-facts-json-layout.md
  - design/interace-contract/regression.md
---

# Verification record: Regression baseline-resolution & availability helpers

## Merged commit

`b32084d feat(regression): baseline resolution & availability helpers`

Source handoff:
[`handoffs/regression-team-2026-05-26-baseline-resolution.md`](../handoffs/regression-team-2026-05-26-baseline-resolution.md).

## Why this is a record doc (no Manual Test action requested)

The three new functions are **pure engine surface** in
`novetest.regression`:

```
novetest.regression.resolve_latest_baseline(store, target_expression)
    -> tuple[RunReference, RunReference] | RegressionUnavailable
novetest.regression.derive_latest_regression(store)
    -> RegressionFactSet | RegressionUnavailable
novetest.regression.check_regression_availability(store, run_reference)
    -> bool
```

I grepped `src/novetest/cli/` and `src/novetest/orchestration/` for any
of the three names and got **zero hits.** These helpers are not yet
wired into any CLI verb or orchestration workflow — the projection
onto envelopes (`novetest regression compare`, `novetest regression
latest`, `novetest compare` verb, `inspect` Regression section) is the
explicit scope of the **next** Orchestration CLI cycle.

Without a CLI surface there is no envelope for Manual Test to
copy-paste paths out of, and no command for them to exercise. The 17
new unit tests + 2 new integration tests in this slice cover the
contract end-to-end through the real Project Store seams (no Memory
mocks) — that is the verification surface this cycle.

The first real Manual Test verification request for these helpers
will arrive when the Orchestration team's CLI projection slice ships.

## Gate (post-merge, on `main` @ `b32084d`)

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit tests/integration` | **442 passed, 3 skipped** (was 423+3 on `0b55baf`; +19 new tests, all green; the 3 skips are the pre-existing Node-dependent jest integration tests, unrelated to this slice). |
| `uv run pytest -q tests/unit/regression tests/integration/regression` (slice-scope) | (handoff-claimed) **89 passed** (was 70 → +19). I did not re-run this targeted subset; the full-tree count delta of exactly +19 matches the handoff's claim verbatim. |
| `uv run mypy` | **clean** (57 source files, `--strict`; count unchanged — no new src files). |

All counts matched the handoff's claims exactly.

## Conflict resolution

None. Clean fast-forward from `0b55baf` (handoff's stated base) →
`b32084d`. No INDEX collision (the worktree's commit included a
1-line INDEX touch only; I re-ran `tools/regen_comms_index.py`
post-merge to pick up the new handoff entry deterministically — minor
delta from the worktree's regen as the file dates have advanced).

## Engine surface now complete

This slice closes out the `design/interace-contract/regression.md`
Internal interface table. All 7 rows are implemented; no further engine
surface is required for the upcoming CLI projection.

## Key behavior pins (worth carrying into the CLI cycle's verification)

These are NOT for Manual Test to probe this cycle — flagging them so
the next cycle's CLI slice gets a head-start on what to lock down
when envelope projection lands:

1. **`resolve_latest_baseline` tuple ordering.** Returns
   `(baseline=older, target=newer)` per decision §2. Tested in
   `test_baseline_resolution.py::test_resolve_three_runs_picks_two_latest`
   etc. — the contract-doc §C.4 ambiguity is closed.
2. **`<2 comparable runs` → `REASON_NO_COMPARABLE_BASELINE`.** The
   `RegressionUnavailable.detail` carries the `target_expression`
   string for single-run targets, and the literal string `"no-runs"`
   for the truly empty / all-tombstoned case. The distinction is
   load-bearing: `derive_latest_regression` PROPAGATES the
   `target_expression` detail when single-run resolves at the
   downstream call site rather than re-wrapping to `"no-runs"`. Pinned
   by `test_derive_latest_single_run_propagates_resolve_detail`.
3. **`derive_latest_regression` active-target anchor.** The "active
   target" is the latest **non-tombstoned** run's `target_expression`
   — NOT the literal latest. Without this filter, a tombstoned latest
   on a different target would block resolution against a perfectly
   comparable pair one rung down. Pinned by
   `test_derive_latest_skips_tombstoned_latest_and_uses_live_earlier_target`.
4. **`check_regression_availability` self-filter.** The input run is
   filtered out of its own candidate set by `run_id` regardless of
   tombstone state. Without this, a single live run on a target would
   falsely return `True` (it would see itself as a sibling). Pinned
   by `test_check_one_sibling`.
5. **`regression_facts.json` on-disk shape.** The integration test
   `test_baseline_resolution_e2e.py::test_derive_latest_writes_facts_at_pinned_path`
   asserts the file lands at
   `<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json`
   with `schema_version=1`, the 11-key `summary` block, and sorted
   `test_transitions` — verbatim from decision §4.

## Pytest baseline drift (informational, for PM)

The Regression team's task brief quoted a 415-test baseline from
`7e5b7a5`. The actual pre-slice baseline on `main` (`0b55baf`) was
**423+3** — 8 tests drifted in via the comms/verification commits
between `7e5b7a5` and `0b55baf`. The +19 delta from this slice lands
at 442+3 regardless. Not a blocker; PM may want to reference
`0b55baf` (or the current head after this merge) when phrasing the
next task brief's baseline.

## DoD bullets believed closed

**None.** Engine surface completion only. The remaining Phase 3 DoD
bullets (`novetest regression compare` / `novetest regression latest`
/ `novetest compare` verb / `inspect` Regression section wiring) all
close together when the upcoming Orchestration CLI cycle ships and
Manual Test fields the `regression_outcome` / `regression_delta`
envelope shapes — same ship→field-test→freeze cadence Coverage
followed (per decision §C.2).

## Next-cycle dependency map (for PM awareness)

- **Orchestration CLI cycle:** consumes the three new entry points to
  build `novetest regression compare` / `latest` / `compare` /
  `inspect` Regression section. PM freezes envelope shapes AFTER
  Manual Test fields them.
- **Localization Phase 4 activation:** will consume
  `derive_latest_regression` + `check_regression_availability` +
  `get_regression_facts` directly — no further engine surface needed.
