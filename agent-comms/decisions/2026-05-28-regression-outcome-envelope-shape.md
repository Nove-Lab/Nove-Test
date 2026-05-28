---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-28
slug: regression-outcome-envelope-shape
---

# Decision: `data.regression_outcome` envelope shape v1

CEO-approved on 2026-05-28. Pins the v1 wire shape of the `regression_outcome`
block introduced by the Phase 3 Regression CLI surface slice (commit
`c074226`), so any future verb that touches Regression facts extends rather
than redesigns it.

Companion to `decisions/2026-05-16-coverage-outcome-envelope-shape.md` —
same pattern, same forward-compatible rules, parallel structure.

## Source-of-truth

- `src/novetest/models/regression_fact_set.py::RegressionFactSet.to_dict`
  for `kind: "fact-set"`.
- `src/novetest/regression/results.py::RegressionUnavailable` for
  `kind: "unavailable"` (closed 6-`REASON_*` set per
  `decisions/2026-05-26-regression-facts-json-layout.md` §7).

The wire shape below is the `to_dict()` output with the top-level
`schema_version` stripped (envelope versioning lives at the outer
`schema: novetest/v1`). Inner blocks retain their own `schema_version`
because they round-trip through dataclass `from_dict` validators.

## Shape

The `regression_outcome` block is OPTIONAL on any envelope. When present,
it is an object discriminated by the `kind` field. Two kinds are defined
at v1.

### `kind: "fact-set"`

Emitted when Regression Facts were successfully derived (or retrieved via
cache) for the (baseline, target) pair.

```json
{
  "kind": "fact-set",
  "baseline_run_reference": { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "target_run_reference":   { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "baseline_engine_name":    "pytest" | "jest" | "go-test" | "junit" | "dotnet" | "cargo",
  "target_engine_name":      "pytest" | "jest" | "go-test" | "junit" | "dotnet" | "cargo",
  "baseline_engine_version": "<string>" | null,
  "target_engine_version":   "<string>" | null,
  "derived_at": <epoch_ms>,
  "summary": {
    "regressed": <int>, "fixed": <int>,
    "still_failing": <int>, "still_passing": <int>, "still_skipped": <int>,
    "newly_skipped": <int>, "newly_active": <int>,
    "added": <int>, "removed": <int>,
    "total_baseline_tests": <int>, "total_target_tests": <int>
  },
  "test_transitions": [
    {
      "schema_version": 1,
      "node_id": "<string>",
      "category": "regressed" | "fixed" | "still_failing" | "still_passing"
                | "still_skipped" | "newly_skipped" | "newly_active"
                | "added" | "removed",
      "baseline_outcome": "<string>" | null,
      "target_outcome":   "<string>" | null,
      "baseline_failure_reference": "<string>" | null,
      "target_failure_reference":   "<string>" | null,
      "baseline_duration_ms": <int> | null,
      "target_duration_ms":   <int> | null
    }
  ],
  "output_diff": null | {
    "baseline_stdout_sha256": "<hex>" | null,
    "target_stdout_sha256":   "<hex>" | null,
    "baseline_stderr_sha256": "<hex>" | null,
    "target_stderr_sha256":   "<hex>" | null,
    "stdout_identical": <bool>,
    "stderr_identical": <bool>,
    "baseline_stdout_path": "<project-store-relative>" | null,
    "target_stdout_path":   "<project-store-relative>" | null,
    "baseline_stderr_path": "<project-store-relative>" | null,
    "target_stderr_path":   "<project-store-relative>" | null
  },
  "coverage_change": null | <CoverageDelta.to_dict() verbatim, see decisions/2026-05-16-coverage-delta-envelope-shape.md>,
  "warnings": [],
  "metadata": {}
}
```

### `kind: "unavailable"`

Emitted when Regression Facts cannot be produced for the requested pair.
Unavailable is **data, not a transport error** — envelope `ok` remains
`true`, exit code remains `0`. (CLI transport errors like `not-found`
on a typo'd run_id short-circuit BEFORE the engine runs and use the
standard `errors[]` channel with exit `2`.)

```json
{
  "kind": "unavailable",
  "baseline_run_reference": null | { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "target_run_reference":   null | { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "reason": "run-not-found" | "run-tombstoned" | "no-comparable-baseline"
          | "missing-derived-facts" | "engine-mismatch" | "target-mismatch",
  "detail": "<string>" | null
}
```

The 6 `reason` values are the closed set pinned by
`decisions/2026-05-26-regression-facts-json-layout.md` §7. Adding a new
reason requires updating that decision AND adding the `REASON_*` constant
in `src/novetest/regression/results.py`.

## Binding constraints

1. **`kind` is the discriminator.** Consumers must branch on `kind`
   first. Fields outside the discriminated set for a given kind are
   illegal on the wire.

2. **Both `*_run_reference` fields are INDEPENDENTLY nullable on
   `unavailable`** — richer than Coverage's single-ref Unavailable. This
   lets consumers tell WHICH side failed:
   - `run-not-found` on baseline → `baseline_run_reference: null`,
     `target_run_reference: {...}` (or both null if both unresolvable).
   - `run-tombstoned` of baseline → both refs populated (consumer still
     knows what pair was asked for), `detail` carries `"baseline"`.
   - `no-comparable-baseline` from `derive_latest_regression` empty store
     → both refs `null`, `detail == "no-runs"`.
   - `no-comparable-baseline` from `derive_latest_regression` single-run
     store → both refs `null`, `detail == <target_expression>`.
   - `engine-mismatch` / `target-mismatch` → both refs populated, `detail`
     carries the diff template (see constraint 4).

3. **Top-level `schema_version` is stripped on the wire.** The
   on-disk `regression_facts.json` retains it (`from_dict` requires it),
   but the envelope's outer `schema: "novetest/v1"` is the wire
   versioning surface. Inner blocks (`*_run_reference`,
   `test_transitions[*]`, embedded `coverage_change`) RETAIN their own
   `schema_version` because they round-trip through their own
   `from_dict` validators. Same precedent as `coverage_outcome` /
   `coverage_delta`.

4. **`detail` template conventions** (pinned by Manual Test field-test
   2026-05-27, decision required so AI consumers can pattern-match):
   - **Tombstone**: `detail` is one of the literal strings `"baseline"`,
     `"target"`, or `"both"` — identifies which side was tombstoned.
   - **`no-comparable-baseline` from `derive_latest_regression`**:
     `detail` is either the literal `"no-runs"` (empty store) or the
     `target_expression` (single-run-on-target). Same `reason`, different
     `detail` carries the disambiguation.
   - **engine-mismatch**: `detail` follows the template
     `"baseline engine_name='<a>' != target engine_name='<b>'"`.
   - **target-mismatch**: `detail` follows the template
     `"baseline target_expression='<a>' != target target_expression='<b>'"`.
   - **`missing-derived-facts` / `run-not-found`**: `detail` is
     human-readable free-form text (no fixed template).
   - **`detail == null` is permitted by the dataclass** but no production
     engine path emits it today. Consumers must tolerate `null`.

5. **`warnings` and `metadata` on `fact-set` are always emitted** —
   write-side emits `warnings: []` and `metadata: {}` even when empty
   (mirrors `RegressionFactSet.to_dict`). Read-side tolerance per
   `decisions/2026-05-26-regression-facts-json-layout.md` §8 allows
   omission; write-side does not omit.

6. **Block omission semantics.** When a command does not produce a
   Regression view at all (e.g. `novetest run`, `novetest init`, plain
   `novetest test`), the `regression_outcome` key is OMITTED entirely
   from `data`. Emitting `null` is forbidden — breaks the byte-
   equivalence guarantee for non-regression envelopes.

7. **Schema version unchanged.** This block is an additive extension to
   `data` on commands that emit Regression. The envelope-level
   `schema: "novetest/v1"` stays. Bumping requires its own decision.

## Forward-compatible extension rules

- Adding a new `kind` requires v2 of this decision.
- Adding a new optional field inside an existing `kind` is non-breaking
  and does not require a decision update.
- Adding a new `reason` requires updating
  `decisions/2026-05-26-regression-facts-json-layout.md` §7,
  `src/novetest/regression/results.py::REASON_*`, AND the enum list
  above.
- Adding a new `TestTransition.category` requires a `RegressionFactSet`
  `SCHEMA_VERSION` bump (closed 9-category enum is load-bearing for
  consumers — see `regression_fact_set.py` line 43-55).
- The `detail` templates in constraint 4 are pinned — changing them
  requires v2 of this decision.

## Affected commands

- `novetest regression compare <baseline> <target>` — emits both kinds.
- `novetest regression latest` — emits both kinds.
- `novetest compare <baseline> <target>` — emits `regression_outcome`
  as one of two top-level keys under `data` (the other being
  `coverage_delta`). Same shape, composed with Coverage delta in one
  envelope.
- `novetest inspect <run_id>` — emits `regression_outcome` under `data`;
  `sub_reports.regression` flips `"available"` ↔ `"unavailable"` to
  mirror the discriminated `kind`. Baselines against the IMMEDIATE
  PRIOR live run on the same target (NOT the global latest pair) —
  pinned by unit test
  `test_inspecting_an_old_run_uses_immediate_prior_not_global_latest`.

## Rationale

The shape was field-tested across three consecutive cycles:
1. 2026-05-26 Regression engine slice (`compare_runs` + persistence)
2. 2026-05-27 baseline-resolution slice (`derive_latest_regression`)
3. 2026-05-27 CLI surface slice (`regression compare` / `regression
   latest` / `compare` / `inspect`).

The third cycle's Manual Test verdict was `passed` with zero envelope
divergences. Freezing now closes the ship → field-test → freeze cadence
(decision `2026-05-26-regression-facts-json-layout.md` §C.2) and
prevents future Regression-touching verbs from improvising.

## Affected teams / files

- **Orchestration Team** — owns the projection logic
  (`cli/app.py::_regression_outcome_payload` and
  `orchestration/workflows/inspect.py::_regression_outcome_section` — the
  intentional duplicate avoids an `orchestration → cli` import cycle,
  same precedent as `_coverage_outcome_section`).
- **Regression Team** — owns the source-of-truth dataclasses
  (`models/regression_fact_set.py::RegressionFactSet.to_dict` and
  `regression/results.py::RegressionUnavailable`). Shape changes must
  start there and propagate through this decision.
- **All teams** — the shape is binding for any envelope that emits a
  `regression_outcome` block.

## Effective date

2026-05-28.

## Supersedes

None. First decision on the `regression_outcome` envelope shape.
