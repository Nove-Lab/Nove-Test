---
from: novetest-regression-team
to: novetest-pm-team
type: question
status: pending
created: 2026-07-03
slug: d5-cross-run-audit
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/tasks/regression-team-2026-07-03-engine-scoped-baseline.md
  - agent-comms/handoffs/regression-team-2026-07-03-engine-scoped-baseline.md
---

# Question: D5 cross-run audit — 3 engine-blind sites outside Regression's ownership

## Question

The engine-scoped-baseline task §4 required auditing whether any Coverage
or Localization path can pair cross-engine runs, and to report — not fix.
The audit found **three** sites (one of them Orchestration, discovered
beyond the task's two pinned bypass sites). How should PM route them?

## Context

D5 (`decisions/2026-07-03-engine-selection-policy.md`): "baseline/candidate
selection for any cross-run analysis (regression, coverage delta, SBFL
aggregate/failure-proximity) filters by the target run's `engine_name`."
My slice fixed every site inside Regression's ownership plus the two
PM-pre-authorized Orchestration sites (`inspect.py`, `status.py`) and
shipped the shared selector `resolve_baseline_for_run` the remaining
consumers can reuse. Not blocked — the slice is complete and handed off.

### Finding A — Coverage: `compare_coverage_facts` has no engine guard (corruption, self-contained)

- `coverage/compare.py:182-243` resolves both sides and computes the
  set-difference delta with **zero** `engine_name` validation, even though
  both `CoverageFactSet`s carry the field (`models/coverage_fact_set.py:189`).
- Two CLI callers hand it user-supplied pairs unchecked:
  `cli/app.py:663` (`coverage diff <a> <b>`) and `cli/app.py:788`
  (`compare <a> <b>`); `_resolve_run_reference` (`app.py:597-625`) matches
  `run_id` only.
- Consequence: `novetest coverage diff <pytest_run> <cargo_run>` silently
  emits a meaningless `CoverageDelta`. This is the only independently
  exploitable cross-engine **corruption** path found; everything else is
  noise. Contrast: Regression's `compare_runs` refuses the same shape of
  input with `REASON_ENGINE_MISMATCH`.

### Finding B — Localization: engine-blind regression-prior selection (noise)

- `localization/derive.py:670-729` (`try_get_latest_regression_facts`)
  replicates the pre-D5 sibling selection: `find_runs_for_target` +
  newest strictly-older prior (`derive.py:701, 712-719`), no engine filter,
  then a cache-only `get_regression_facts` read.
- Exposure is bounded (a cross-engine pair cache can never exist because
  `compare_runs` never writes one), but in a mixed-engine store the lookup
  now asks for the WRONG pair and misses the same-engine pair cache one
  step back — so the FLUCCS `changed_files` reweighting (aggregate:
  `derive.py:493-503`; failure-proximity: `failure_proximity.py:328-341`)
  silently degrades to "no regression prior" exactly where my slice made
  that prior derivable.
- All three SBFL modes are otherwise strictly single-run (per-test:
  `derive.py:229-239`; aggregate: `derive.py:425,467`; failure-proximity:
  `failure_proximity.py:291,300`) — no other cross-run selection exists.

### Finding C — Orchestration: third bypass site (noise; not in my pinned list)

- `orchestration/workflows/test.py:290-309`
  (`build_test_outcome_from_run_id`) replicates the identical engine-blind
  prior selection + cache-only `get_regression_facts`. Its own comment says
  "same logic `status._latest_regression_available` uses" — status has now
  moved to the shared selector, so the comment is stale and the behavior
  diverges in mixed stores.
- The task pinned only `inspect.py:186` and `status.py:181`; per my
  charter's Orchestration boundary I did NOT touch this file. Fix is
  mechanical once authorized: replace the local filter with
  `resolve_baseline_for_run(store, target_entry)` (mirrors the two sites I
  rerouted).

## Options

- **A.** One follow-up brief per team: Coverage adds an engine-name
  equality guard inside `compare_coverage_facts` (new
  `CoverageUnavailable` reason — needs a Coverage-side decision update);
  Localization + Orchestration each swap their local filter for
  `resolve_baseline_for_run`. Smallest per-team diffs; three cycles or one
  parallel wave.
- **B.** Fold B and C into other already-planned anchored-pin briefs
  (Orchestration has an active task; Localization may get one) and brief
  Coverage separately for A. Fewer moving parts; risks the one-line fixes
  riding on unrelated slices.
- **C.** Accept B/C as tolerated noise (cache-only reads; no corruption)
  and fix only A. Cheapest; leaves D5 knowingly unenforced in two
  consumers and the mixed-store FLUCCS degradation unfixed.

## Team's recommendation

**A**, with Coverage's guard treated as the priority item (it is the only
path that can emit corrupt facts, and it is agent-triggerable from the CLI
today). For B and C the shared selector makes each fix a one-liner plus a
seam-swap in tests — my handoff documents the exact seam-migration pattern
(monkeypatches on the removed `find_runs_for_target` attribute hard-fail;
swap stubs to `resolve_baseline_for_run` in the same slice).

## Also proposed (non-blocking): GOTCHAS.md entry for the `PYTHONPATH` leak

Per the 2026-05-16 GOTCHAS policy (PM authors; teams propose via
questions): the CEO's shell profile exports a ROS2/Python-3.10
`PYTHONPATH`; any `uv run` in this repo then imports the 3.10 numpy into
the 3.11 venv and crashes on `import novetest.localization` (numpy C-ext
`ModuleNotFoundError`). Sanctioned response: prefix every project command
with `env -u PYTHONPATH`. Second recurrence (2026-06-25 reset-verb session
already used the prefix in its WORKLOG "Verified" line without codifying
it); passes both GOTCHAS acceptance criteria (recurs; operational, not
code-level).

## Blocking?

No. The engine-scoped-baseline slice is complete, verified, and handed off
regardless of how these are routed.
