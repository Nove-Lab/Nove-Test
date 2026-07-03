---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-03
slug: engine-scoped-baseline
related:
  - agent-comms/handoffs/regression-team-2026-07-03-engine-scoped-baseline.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Verification request: Regression — engine-scoped baseline resolution (D5)

## Merged

- **Commits**: `8b2dce8` (code) + `0042232` (comms) — rebased and
  FF-merged as slice 4/4 of the 2026-07-03 batch.
- **Source handoff**: `regression-team-2026-07-03-engine-scoped-baseline.md`.
- **Merge mechanics**: WORKLOG.md keep-both conflict + agent-comms/INDEX.md
  union conflict (this slice's D5-audit question entry + the reruns slice's
  question entry — both kept). No source conflicts.
- **Cross-team edits included (PM pre-authorized in the task brief)**:
  `orchestration/workflows/inspect.py` + `status.py` rerouted through the
  new shared selector; 4 Orchestration-owned unit-test files re-seamed by
  necessity. Ordered AFTER the orchestration test-reruns slice; zero file
  overlap confirmed empirically (only WORKLOG/INDEX collided).

## Gate (on the merged tree)

- `env -u PYTHONPATH uv run mypy` → Success, 114 source files.
- Final batch tree **1418 passed / 3 deselected / 47 snapshots** (= +14
  regression tests: 9 unit + 3 e2e + 2 availability).
- Pre-merge review (code-reviewer): **MERGE-OK, zero blocking findings.**
  Reroute equivalence for pure single-engine series traced as provably
  identical (same RunReference identity, same reason/detail strings);
  double-scan confirmed correctness-safe; blast radius of untouched caller
  `workflows/test.py:191` verified gate-safe.

## What changed (behavior an observer can see)

Binding D5 rule: baseline/candidate selection filters by the target run's
`engine_name`. One shared selector `resolve_baseline_for_run` (new public,
`novetest.regression` package export); `resolve_latest_baseline`,
`check_regression_availability`, inspect, and status all route through it.
`compare_runs`' ENGINE_MISMATCH guard stays as defense-in-depth for
user-picked pairs.

## Verification steps (all envelope paths below observed live via the real CLI on the merged tree)

Seed real stores with `novetest.memory.store.store_run_evidence` (recipe in
`tests/integration/regression/test_engine_scoped_baseline_e2e.py`), then:

### G1 — mixed series pairs same-engine across a foreign run (observed)

Store: `[pytest(test_a FAILED), cargo-test, pytest(test_a passed)]`, one
target `tests/`. From the workspace:

```bash
env -u PYTHONPATH uv run --project <repo> novetest regression latest
```

Observed: exit 0, `ok: true`, `command: "regression.latest"`, and under
`data.regression_outcome`:

- `kind == "fact-set"`
- `baseline_run_reference.run_id` = the OLD pytest run,
  `target_run_reference.run_id` = the NEW pytest run — the cargo run in
  between is skipped (pre-D5: `unavailable` via the guaranteed-mismatch
  neighbor)
- `baseline_engine_name == target_engine_name == "pytest"`
- `summary.fixed == 1`; `test_transitions[0]` =
  `(node_id="tests/x.py::test_a", category="fixed")` — a real fail→pass
  transition, distinguishable from any accidental pairing

### G2 — only cross-engine priors → engine-suffixed detail (observed)

Store: one cargo-test run (older) + one pytest run (newer), same target.

Observed under `data.regression_outcome`:

- `kind == "unavailable"`, `reason == "no-comparable-baseline"`
- `detail == "tests/ (engine=pytest)"` — the NEW detail convention,
  emitted ONLY when older runs exist but none share the target's engine.
  (Pre-D5 this surfaced as ENGINE_MISMATCH from `inspect`; that reason
  remains reachable via explicit `regression compare <a> <b>`.)

### G3 — pure single-engine series: zero drift

`init` + `test` twice on `pytest-basic` → `regression latest` emits the
byte-identical pre-D5 envelope (plain `detail` forms; the 7-case block in
`test_baseline_resolution.py` pins this). `novetest inspect <newest>` and
`novetest status` must agree with `regression latest` — agreement is now
by construction (same selector).

### G4 — targeted suites

```bash
env -u PYTHONPATH uv run pytest -q tests/unit/regression \
  tests/integration/regression tests/unit/orchestration/workflows
# observed in-batch: all green (153 in-worktree)
```

## Critical edge cases worth probing

1. **Equal-`created_at` tie (reviewer finding, uncovered by tests)**: if
   the two newest live runs share the same millisecond `created_at`, the
   strictly-older rule skips the tie; with no strictly-older same-engine
   run the result is `no-comparable-baseline` with the engine-suffixed
   detail — diagnostically misleading in that edge (the tie, not the
   engine, eliminated the candidate). Rare (ms ULIDs, sequential runs
   seconds apart). Worth one probe; candidate for a regression-team
   follow-up note.
2. **Tombstoned same-engine prior** is skipped by the selector (pinned by
   unit test) — verify via `memory delete` on the old pytest run in G1:
   result flips to unavailable.
3. **`check_regression_availability`** gained the engine filter (flagged
   scope addition; zero production callers today). Reviewer note: it
   counts any non-self same-target same-engine sibling (not strictly
   older) — pre-existing semantics, diverges from the selector's
   strictly-older rule; matters only for whoever wires the first caller.
4. **D5 audit question for PM** (filed by the team, non-blocking): 3
   engine-blind sites remain OUTSIDE this slice — Coverage
   `compare_coverage_facts` (genuine corruption path: `coverage diff
   <pytest_run> <cargo_run>` silently emits a meaningless delta),
   Localization `try_get_latest_regression_facts` (noise: misses the pair
   cache this slice makes derivable), Orchestration `test.py:290`
   (one-line fix once authorized). Manual Test may reproduce the Coverage
   one to size the finding.

## Notes

- New `detail` convention: `"<target> (engine=<name>)"` appears ONLY in a
  previously-unreachable state; plain `detail=<target>` and `"no-runs"`
  forms are byte-identical to pre-D5.
- No new REASON_*, no envelope-shape change (2026-05-28 freeze untouched).
