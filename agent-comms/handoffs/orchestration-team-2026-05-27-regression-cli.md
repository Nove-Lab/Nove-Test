---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-27
slug: regression-cli
related:
  - agent-comms/tasks/orchestration-team-2026-05-27-regression-cli.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - design/interace-contract/regression.md
  - design/interace-contract/orchestration.md
  - design/implementation-plan/delivery-phasing.md
---

# Handoff: Phase 3 Regression CLI surface + `inspect` Regression section

## Worktree

- Path: `/home/yjshin/dev/novetest-regression-cli`
- Branch: `worktree-regression-cli`
- Base commit: `ce1bd44` (matches `82e1775` pre-flight baseline — `ce1bd44`
  is the comms-only task-queueing commit that landed after the
  baseline-resolution cycle closed; src/tests state is identical).
- Single commit: `c074226 feat(orchestration): wire Phase 3 Regression CLI surface`

## Files touched

### Source (2 edited, no new src files)

- `src/novetest/cli/app.py`
  - New imports: `RegressionFactSet`, `RegressionUnavailable`,
    `compare_runs`, `derive_latest_regression` from `novetest.regression`.
  - New `regression_app = App(name="regression", ...)` sub-App.
  - New handlers: `regression_compare(baseline, target)`,
    `regression_latest()`, `compare_cmd(baseline, target)`.
  - New `_regression_outcome_payload(outcome)` projection helper
    (mirrors `_coverage_delta_payload`'s `body = to_dict()` +
    `pop("schema_version")` + `**body` pattern for `kind: "fact-set"`;
    independently-nullable `baseline_run_reference` / `target_run_reference`
    for `kind: "unavailable"`).
  - `_register_flat_stub` tuple drops `"compare"`;
    `_register_group_stub("regression", ...)` registration removed entirely.
  - `inspect_cmd` docstring updated to describe the now-real Regression
    section.

- `src/novetest/orchestration/workflows/inspect.py`
  - New imports: `find_runs_for_target` from `novetest.memory`;
    `REASON_NO_COMPARABLE_BASELINE`, `RegressionFactSet`,
    `RegressionUnavailable`, `compare_runs` from `novetest.regression`.
  - `InspectView` gains a `regression_outcome` field.
  - `to_dict()` emits a top-level `regression_outcome` block and flips
    `sub_reports["regression"]` from hardcoded `"unavailable"` to the
    actual outcome (`"available" if regression_present else "unavailable"`).
  - New `_resolve_inspect_regression(store, inspected)` helper composes
    `find_runs_for_target(include_tombstoned=False)` + `compare_runs`
    against the run IMMEDIATELY before the inspected one — NOT the
    global latest pair.
  - New `_regression_outcome_section` helper (intentional duplicate of
    `cli/app.py::_regression_outcome_payload` to avoid an
    `orchestration → cli` import cycle, same precedent as
    `_coverage_outcome_section`).

### Tests (5 new files, 2 edited)

- `tests/unit/cli/test_regression_compare.py` (NEW, 10 cases)
- `tests/unit/cli/test_regression_latest.py` (NEW, 5 cases)
- `tests/unit/cli/test_compare.py` (NEW, 6 cases)
- `tests/unit/orchestration/workflows/test_inspect_regression.py` (NEW, 8 cases)
- `tests/integration/cli/test_regression_e2e.py` (NEW, 3 cases)
- `tests/unit/orchestration/workflows/test_inspect.py` (MODIFIED):
  `_patch_memory` helper extended with `siblings=` parameter +
  `find_runs_for_target` stub + a `compare_runs` "must-not-be-called"
  guard. Existing assertions hold (single-entry case → no comparable
  baseline → `sub_reports["regression"]` stays `"unavailable"`).
- `tests/integration/cli/test_subcommand_stubs.py` (MODIFIED): parametrize
  drops `compare`, `regression compare`, `regression latest`; only
  `replay` + `localization` stubs remain.

### Other

- `WORKLOG.md`: appended `2026-05-27 — phase3 / regression-cli` entry.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **471 passed + 3
  skipped** (base `82e1775`: 442+3 → +29 net = 32 added − 3 stub
  parametrize cases dropped; the 3 skips are the pre-existing
  Node-dependent jest integration tests on this dev host).
- `uv run mypy` → **clean**, 57 source files, `--strict` (no new src
  files, count unchanged).
- Manual smoke (subprocess, tmp Project Store, two real `RunRecord`s via
  `store_run_evidence`, baseline = pass, target = fail on the same
  node_id):
  - `regression compare <b> <t>` → exit 0, `regression_outcome.kind ==
    "fact-set"`, `summary.regressed == 1`.
  - `regression latest` → exit 0, identical fact-set (engine cache hit).
  - `compare <b> <t>` → exit 0, `data` keys =
    `{"coverage_delta", "regression_outcome"}`, coverage half is
    `kind: "unavailable"` `reason: "missing-derived-facts"` (neither
    smoke run had `--coverage`, expected).

## Envelope shape — working draft for PM

The `regression_outcome` block emitted by `regression compare`,
`regression latest`, `compare` (within `data`), and `inspect` (within
`data`) uses this wire shape. **Source-of-truth verified against
`src/novetest/models/regression_fact_set.py::RegressionFactSet.to_dict`
and `src/novetest/regression/results.py::RegressionUnavailable`.**

### `kind: "fact-set"`

Top-level keys (in dict-iteration order):

```
{
  "kind": "fact-set",
  "baseline_run_reference": { "run_id": "...", "created_at": ..., "schema_version": 1 },
  "target_run_reference":   { "run_id": "...", "created_at": ..., "schema_version": 1 },
  "baseline_engine_name": "pytest",
  "target_engine_name":   "pytest",
  "baseline_engine_version": "8.2.0" | null,
  "target_engine_version":   "8.2.0" | null,
  "derived_at": <epoch_ms>,
  "summary": {
    "regressed": 0, "fixed": 1, "still_failing": 0, "still_passing": 12,
    "still_skipped": 0, "newly_skipped": 0, "newly_active": 0,
    "added": 1, "removed": 0,
    "total_baseline_tests": 13, "total_target_tests": 14
  },
  "test_transitions": [
    { "schema_version": 1, "node_id": "...", "category": "fixed",
      "baseline_outcome": "failed" | null, "target_outcome": "passed" | null,
      "baseline_failure_reference": "..." | null,
      "target_failure_reference": "..." | null,
      "baseline_duration_ms": 12 | null,
      "target_duration_ms": 9 | null }
  ],
  "output_diff": null | {
    "baseline_stdout_sha256": "..." | null,
    "target_stdout_sha256":   "..." | null,
    "baseline_stderr_sha256": "..." | null,
    "target_stderr_sha256":   "..." | null,
    "stdout_identical": true | false,
    "stderr_identical": true | false,
    "baseline_stdout_path": "..." | null,
    "target_stdout_path":   "..." | null,
    "baseline_stderr_path": "..." | null,
    "target_stderr_path":   "..." | null
  },
  "coverage_change": null | { /* CoverageDelta.to_dict() verbatim */ },
  "warnings": [],
  "metadata": {}
}
```

Notes for PM's freeze decision:

1. **No top-level `engine_name` / `ecosystem` / `target_type` /
   `target_expression`** — the brief's idealized draft showed those, but
   `RegressionFactSet.to_dict()` only emits the per-side `*_engine_name`
   / `*_engine_version` fields. Consumers needing the target expression
   can read it from the embedded `RunReference` consumer's own Memory
   lookup (Memory's `MemoryEntry.run_record.target_expression`), or PM
   can decide to lift it onto the wire shape via a follow-up
   `RegressionFactSet` schema bump (would require Regression team
   coordination + `SCHEMA_VERSION` bump).
2. **`*_run_reference` blocks carry `schema_version`** — the inner
   `RunReference.to_dict()` emits three keys (`run_id`, `created_at`,
   `schema_version`). The same gotcha PM accepted for `coverage_outcome`
   applies here; consistent across all verbs.
3. **`schema_version` is stripped from the top-level block** — envelope
   versioning lives at `schema: "novetest/v1"`. Inner blocks
   (`test_transitions[*]`, embedded `coverage_change`) retain their own
   `schema_version` because they round-trip through their dataclass
   `from_dict` validators.
4. **`warnings` is `[]` not omitted** — `to_dict()` always emits the
   field. Read-side tolerance allows omission per decision §8, but
   write-side always emits.

### `kind: "unavailable"`

```
{
  "kind": "unavailable",
  "baseline_run_reference": null | { "run_id": "...", "created_at": ..., "schema_version": 1 },
  "target_run_reference":   null | { "run_id": "...", "created_at": ..., "schema_version": 1 },
  "reason": "run-not-found" | "run-tombstoned" | "no-comparable-baseline"
          | "missing-derived-facts" | "engine-mismatch" | "target-mismatch",
  "detail": "..." | null
}
```

Notes:

1. **Both refs are independently nullable** — richer than Coverage's
   single-`run_reference` Unavailable. `RegressionUnavailable` populates
   them per the engine's tombstone / not-found / engine-mismatch paths
   so the consumer can tell which side failed.
2. **`detail` may be `null`** — `RegressionUnavailable.detail`'s
   dataclass default is `None`. No production engine path ships
   `detail=None` today (every return site provides a string), but the
   type signature allows it; the freeze decision should pin the
   nullability.
3. **The 6 `REASON_*` values are closed** per decision §7.

### `compare` verb's combined envelope

```
{
  "schema": "novetest/v1",
  "command": "compare",
  "ok": true,
  "data": {
    "regression_outcome": { /* as above */ },
    "coverage_delta":     { /* existing frozen shape from
                              decisions/2026-05-16-coverage-delta-envelope-shape.md */ }
  },
  "errors": [],
  "warnings": []
}
```

`coverage_delta` is **the same shape `coverage diff` emits** — projected
via the existing `_coverage_delta_payload` function in `cli/app.py`. No
new shape work for the coverage half.

### `inspect` envelope (extended)

The inspect envelope's `data` now carries one additional top-level
field, `regression_outcome` (same shape as above), and
`data.sub_reports.regression` flips from hardcoded `"unavailable"` to
the actual outcome (`"available"` when a `RegressionFactSet` lands,
`"unavailable"` otherwise). All other inspect fields unchanged.

## DoD bullets believed closed (PM verifies + ticks)

From `design/implementation-plan/delivery-phasing.md`:

- `[156]` `novetest regression latest` resolves the latest pair for the
  resolved Test Target and returns Regression Facts (with Coverage
  changes when available).
- `[157]` `novetest compare` returns the composed Regression + Coverage
  delta.
- `[158]` `inspect` populates Regression section using the resolved
  baseline.

I did NOT tick them — only PM can edit `delivery-phasing.md` per
charter.

## Envelope-shape divergences from the task brief's draft

1. **No flat `engine_name` / `ecosystem` / `target_type` /
   `target_expression`** on the `fact-set` block. Brief showed those;
   actual `to_dict()` does not. Reconciled by mirroring the actual
   `to_dict()` shape verbatim — see "Envelope shape" section above.

2. **`test_transitions[*]` retains its `schema_version: 1`** on the
   wire. Only the top-level `schema_version` is stripped (envelope
   versioning lives at `schema`). The brief was silent on inner
   `schema_version` stripping; following the precedent set by
   `coverage_delta` (which retains inner block schemata).

3. **`RegressionUnavailable.detail` is nullable**. Brief's draft showed
   `"detail": "human-readable string"` unconditionally; the dataclass
   default is `None`. The projection passes whatever the engine produces
   through verbatim.

These divergences should not block the freeze decision — PM has the
actual to_dict shape pinned above; the brief explicitly invited shape
divergence ("update this draft if the source differs") at task lines
317–318 and 483–487.

## Behaviour notes for Manual Test

When Manual Test fields this:

- **All 4 verbs are exit-0 on success AND on unavailable outcome** —
  unavailable is data, not a transport error. Exit 2 only for
  `not-found` (typo'd run_id) and `uninitialized` (no `.novetest/`
  ancestor).
- **`regression compare` with stale-cache-but-tombstoned-now** should
  return `regression_outcome.kind == "unavailable"` `reason ==
  "run-tombstoned"` per decision §C.1 — the engine fails hard even
  when the pair's `regression_facts.json` exists on disk. Worth
  probing.
- **`compare` is NOT the same as `regression compare`** — the latter
  emits only `regression_outcome`; the former emits both
  `regression_outcome` AND `coverage_delta`. Distinct verbs.
- **`inspect <middle_run>` baselines against the IMMEDIATE prior**,
  NOT the global latest pair on the target. So inspecting an old run
  in a 3-run history should show the 2-run comparison vs the run
  immediately before it. The unit test
  `test_inspecting_an_old_run_uses_immediate_prior_not_global_latest`
  pins this; Manual Test should sanity-check on a real 3-run target.

## What was NOT touched (charter compliance)

- No `src/novetest/regression/**` or `src/novetest/memory/**` source
  changes.
- No new `REASON_*` constants, no new `TRANSITION_CATEGORIES` values, no
  new discriminator kinds.
- No `--baseline=<id>` / `--since` overrides for `regression latest`
  (Phase 6 territory per the brief).
- No default-verb alias (Phase 6).
- No `test` / `replay` / `localization` stub replacement.
- No `coverage_delta` shape changes.
- No `decisions/` writes (PM-only).
- No `delivery-phasing.md` edits (PM-only).
- No engine-team contract edits (read-only consumer).

## Open questions for PM

None. The brief was specced down to the line; the only judgment call
was the projection-duplication issue (kept the precedent set by the
inspect-aggregated-view slice) and the
`_resolve_inspect_regression`-vs-`resolve_latest_baseline` composition
question (kept the orchestration-layer composition per the brief's own
recommendation at line 396).

## After merge

Per the task brief:

1. Main Branch team merges + pushes (push omission watched per the
   brief).
2. Manual Test fields all 4 verbs against a real Project Store; probes
   each `REASON_*` propagation path; validates the `compare` envelope's
   combined shape.
3. PM writes `decisions/2026-05-XX-regression-outcome-envelope-shape.md`
   anchored on the actual `to_dict()` shape above, gets CEO approval,
   commits.
4. PM cleanup: tick DoD `[156] [157] [158]`, write history entry,
   delete transient files, regen INDEX.
