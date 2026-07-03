---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-16
slug: coverage-delta-envelope-shape
---

# Decision: `data.coverage_delta` envelope shape v1

CEO-approved on 2026-05-16. Pins the v1 wire shape of the `coverage_delta`
block introduced by the `coverage show / diff` slice (commit `50c9170`),
so the upcoming `inspect` Coverage section (Phase 2 DoD #3) and the
future `novetest compare` Regression+Coverage composition (Phase 3) can
extend rather than redesign it.

Companion to `decisions/2026-05-16-coverage-outcome-envelope-shape.md` —
both pin the two halves of the Coverage CLI envelope surface.

## Shape

The `coverage_delta` block is OPTIONAL on any envelope. When present, it
is an object discriminated by the `kind` field. Two kinds are defined at
v1:

### `kind: "delta"`

Emitted when both baseline and target Coverage Facts were successfully
loaded and the cross-run delta was computed.

```json
{
  "kind": "delta",
  "baseline_run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "target_run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "baseline_granularity": "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "target_granularity": "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "summary_before": { ... CoverageSummary.to_dict() ... },
  "summary_after": { ... CoverageSummary.to_dict() ... },
  "files_added": ["path/to/new_file.py", ...],
  "files_removed": ["path/to/dropped_file.py", ...],
  "file_deltas": [ ... FileCoverageDelta.to_dict() ... ]
}
```

Mirrors `CoverageDelta.to_dict()` from `src/novetest/coverage/compare.py`
byte-for-byte. The `mapping_granularity` enum mirrors the binding
constraint in `decisions/2026-05-15-coverage-facts-json-layout.md`.

### `kind: "unavailable"`

Emitted when either side's facts are missing/corrupt — `CoverageUnavailable`
propagated from `compare_coverage_facts`. Carries the offending
`run_reference` so consumers know WHICH side is missing.

```json
{
  "kind": "unavailable",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "reason": "missing-derived-facts" | "native-payload-corrupt" | "run-not-found" | "engine-mismatch",
  "detail": "human-readable explanation"
}
```

The `reason` enum mirrors `coverage_outcome.kind: "unavailable"` —
`REASON_*` constants in `src/novetest/coverage/results.py` are the
source of truth.

> **Amendment 2026-07-03** (PM pre-authorized in
> `tasks/coverage-team-2026-07-03-coverage-compare-engine-guard.md`;
> policy source `decisions/2026-07-03-engine-selection-policy.md` D5):
> additive reason `"engine-mismatch"` — emitted by
> `compare_coverage_facts` when the two sides' `CoverageFactSet.engine_name`
> values differ. Same wire string as Regression's `REASON_ENGINE_MISMATCH`
> so agents match one constant across both engines. For this pair-level
> reason, `run_reference` names the **baseline** side (extending binding
> constraint #4's tie-break convention to reasons not attributable to a
> single side); `detail` carries both engine names
> (`baseline engine_name='pytest' != target engine_name='cargo-test'`).

## Binding constraints

1. **`kind` is the discriminator.** Consumers must branch on `kind`
   first. Fields outside the discriminated set for a given kind are
   illegal.
2. **Per-kind required fields are mandatory.** `delta` always carries
   all 9 fields above; `unavailable` always carries `run_reference +
   reason + detail`. Missing any required field is a wire-contract
   violation.
3. **`unavailable` is NOT a CLI error.** Exit code is `0`, envelope
   `ok: true`. The verb succeeded; the unavailability is part of the
   result payload. CLI exit code `2` is reserved for not-found /
   usage errors (e.g. `novetest coverage diff <fake-id> <other-id>` →
   `errors[0].code == "not-found"`, exit `2`).
4. **`run_reference` semantics in `unavailable`.** Names the SIDE
   that was unavailable. If both sides are unavailable, the baseline
   is named (per `compare_coverage_facts`'s short-circuit order).
5. **Block omission semantics.** When a command was not asked to
   produce a delta (any verb other than `coverage diff` + future
   `compare` / `inspect`-with-delta-composition), the `coverage_delta`
   key is OMITTED entirely from `data`. Emitting `null` is forbidden.
6. **Schema version unchanged.** Additive on commands that produce a
   delta. Envelope-level `schema: novetest/v1` stays. Bumping requires
   its own decision.

## Forward-compatible extension rules

- Adding a new `kind` requires a v2 of this decision.
- Adding a new optional field inside an existing `kind` is non-breaking
  and does not require a decision update.
- Adding a new `reason` requires updating the enum list above and
  adding the constant in `coverage/results.py`.
- Adding a new `mapping_granularity` value requires coordination with
  `decisions/2026-05-15-coverage-facts-json-layout.md` (the on-disk
  source of truth for the enum).

## Affected commands

- `novetest coverage diff <id1> <id2>` (commit `50c9170` — already
  emitting this shape; locked by `tests/unit/cli/test_coverage_cmd.py`
  and `tests/integration/orchestration/test_coverage_cli.py`).
- `novetest inspect <run_id>` (future Phase 2 DoD #3 slice) — if it
  composes per-run deltas (against the prior baseline), reuses this
  shape inside its Coverage section.
- `novetest compare <id1> <id2>` (future Phase 3 — Regression engine
  composition) — composes Regression + Coverage; the Coverage half
  reuses this shape.

## Rationale

Field-tested by Manual Test on the `coverage-show-diff` slice: happy
path (`kind: "delta"`), unavailable path (one side missing facts),
help surface — all clean. Freezing now is cheap and prevents the next
coverage-diff-consuming verb from improvising a different shape.

## Affected teams / files

- **Orchestration Team** — owns the projection logic
  (`cli/app.py::_coverage_delta_payload`). Future CLI verbs emitting
  `coverage_delta` reuse this projection or extend per the rules
  above.
- **Coverage Team** — owns `CoverageDelta.to_dict()` and the `REASON_*`
  constants. Adding a new `reason` requires coordination with this
  decision.
- **Regression Team** — when Phase 3's `novetest compare` lands, the
  Coverage half of the response reuses this shape.

## Effective date

2026-05-16.

## Supersedes

None. Companion to
`decisions/2026-05-16-coverage-outcome-envelope-shape.md`; together they
pin the two halves of the Coverage CLI envelope surface.
