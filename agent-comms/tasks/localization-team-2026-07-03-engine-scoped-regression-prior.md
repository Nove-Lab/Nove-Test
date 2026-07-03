---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-07-03
slug: engine-scoped-regression-prior
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
  - agent-comms/handoffs/regression-team-2026-07-03-engine-scoped-baseline.md
---

# Task: Localization — engine-scoped regression-prior lookup (D5, Finding B)

- **Owner**: novetest-localization-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` D5
- **Sequencing**: Wave 2, no dependencies — parallel with the Orchestration
  and Coverage slices. Small slice.

## Why

D5 audit Finding B: `try_get_latest_regression_facts`
(`src/novetest/localization/derive.py:670-729`) replicates the pre-D5
sibling-selection logic — `find_runs_for_target` + newest strictly-older
prior (`derive.py:701, 712-719`), **no engine filter** — then a cache-only
`get_regression_facts` read. No corruption is possible (a cross-engine
pair cache can never exist, because Regression's `compare_runs` never
writes one), but in a mixed-engine store the lookup asks for the WRONG
pair and misses the same-engine pair cache one step back. The FLUCCS
`changed_files` reweighting (aggregate: `derive.py:493-503`;
failure-proximity: `failure_proximity.py:328-341`) then silently degrades
to "no regression prior" exactly where the wave-1 Regression slice made
that prior derivable.

## In scope

1. Replace the local prior-selection in `try_get_latest_regression_facts`
   with Regression's shared engine-aware selector:
   `resolve_baseline_for_run(store, target_entry)`
   (`src/novetest/regression/compare.py:600`) — the same one-liner swap the
   wave-1 slice applied to `inspect.py` / `status.py`.
2. Test-seam migration per the pattern documented in the Regression
   handoff (`handoffs/regression-team-2026-07-03-engine-scoped-baseline.md`):
   stubs/monkeypatches on the removed `find_runs_for_target` path hard-fail
   — swap them to `resolve_baseline_for_run` in the same slice.
3. Confirm (and state in the handoff) that no other cross-run selection
   exists in Localization — the audit already established all three SBFL
   modes are otherwise strictly single-run (per-test `derive.py:229-239`;
   aggregate `derive.py:425,467`; failure-proximity
   `failure_proximity.py:291,300`).

## Out of scope

SBFL formulas and modes, Coverage/Orchestration findings (routed
separately), any change to `resolve_baseline_for_run` itself (Regression
territory — if its contract doesn't fit, file a question, don't fork it).

## Pinned file list

- **Edit**: `src/novetest/localization/derive.py`.
- **Tests**: `tests/unit/localization/` — mixed-engine store: the
  same-engine regression prior one step back IS found and FLUCCS
  reweighting activates; pure single-engine store behavior unchanged
  (snapshot); no-prior case unchanged.

## Acceptance criteria

- New test: series [pytest, cargo, pytest] with a regression-facts cache
  for the pytest pair — aggregate-mode localization applies the
  `changed_files` reweighting (pre-fix it degrades to no-prior).
- Full suite green on the CI matrix; mypy clean; `WORKLOG.md` entry;
  handoff at
  `agent-comms/handoffs/localization-team-2026-07-03-engine-scoped-regression-prior.md`.

## Effort estimate (PM's read — challenge if you disagree)

~15 LOC production, ~100 LOC tests. Half cycle.
