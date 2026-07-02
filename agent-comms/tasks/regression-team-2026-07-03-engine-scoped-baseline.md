---
from: novetest-pm-team
to: novetest-regression-team
type: task
status: pending
created: 2026-07-03
slug: engine-scoped-baseline
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Task: Regression — engine-scoped baseline resolution (D5)

- **Owner**: novetest-regression-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` (D5)
- **Sequencing**: no dependencies — may start immediately, parallel with
  Memory and Run. Small slice.

## Goal

Baseline selection never pairs runs of different engines. Today
`compare_runs` hard-refuses cross-engine pairs
(`REASON_ENGINE_MISMATCH`, `src/novetest/regression/compare.py:178`) so no
corruption is possible — but `resolve_latest_baseline`
(`compare.py:600-633`) picks the two newest runs for a target *without*
engine filtering, so a mixed-engine series (legitimate under D3's transient
`--engine` override, e.g. a Rust+PyO3 root alternating cargo-test and
pytest) reports "unavailable" even when a comparable same-engine baseline
exists one step further back. Fix the selection; keep the guard.

## In scope

1. **`resolve_latest_baseline`**: target = newest non-tombstoned entry for
   the `target_expression` (unchanged); baseline = newest OLDER entry with
   the **same `engine_name` as the target**. No same-engine prior →
   `REASON_NO_COMPARABLE_BASELINE` (consider carrying the engine in
   `detail` for operator clarity). Update the docstring at
   `compare.py:617-621`, which currently documents the deliberate
   non-narrowing — that paragraph is superseded by D5.
2. **The two bypass sites**: `orchestration/workflows/inspect.py:186` and
   `orchestration/workflows/status.py:181` hand-pick `prior[0]` without
   going through `resolve_latest_baseline` — apply the same engine filter
   there, preferably by routing them through a shared engine-aware selector
   rather than replicating the filter. (These files are Orchestration
   territory; coordinate — PM pre-authorizes this cross-team edit as part
   of this slice since the change is the Regression engine's contract.
   Flag it prominently in the handoff so Main Branch orders merges
   accordingly.)
3. **`compare_runs` guard stays** as defense-in-depth. Do not remove or
   weaken it.
4. **Cross-run audit note (report, don't fix)**: verify whether any
   Coverage (`compare_coverage_facts` direct callers) or Localization
   (SBFL aggregate / failure-proximity run selection) path can pair
   cross-engine runs. If yes, file a question to PM — do NOT fix
   cross-engine issues in those engines yourself.

## Out of scope

Pin/store/CLI work, detection, walk-up, per-test-case reach-back baselines
(CEO-reviewed 2026-07-03: adjacent-state-per-series comparison is the
intended semantic; do not change it).

## Pinned file list

- **Edit**: `src/novetest/regression/compare.py`,
  `src/novetest/orchestration/workflows/inspect.py` (§2),
  `src/novetest/orchestration/workflows/status.py` (§2).
- **Tests**: `tests/unit/regression/` — mixed-engine series picks the
  same-engine baseline (not unavailable); pure series behavior unchanged
  (snapshot); single-run-of-that-engine → unavailable; inspect/status
  paths engine-filtered.

## Acceptance criteria

- Full suite green on the CI matrix; mypy clean.
- New test: series [pytest, cargo, pytest] — the newest pytest run
  resolves the older pytest run as baseline and produces facts.
- `WORKLOG.md` entry; handoff at
  `agent-comms/handoffs/regression-team-2026-07-03-engine-scoped-baseline.md`
  including the §4 audit result.

## Effort estimate (PM's read — challenge if you disagree)

~40 LOC production, ~120 LOC tests. Half cycle.
