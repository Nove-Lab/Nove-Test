---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-16
slug: coverage-outcome-envelope-shape
---

# Decision: `data.coverage_outcome` envelope shape v1

CEO-approved on 2026-05-16. Pins the v1 wire shape of the `coverage_outcome`
block introduced by the `--coverage` wiring slice (commit `10300bb`), so
follow-up coverage-touching CLI verbs (`coverage show`, `coverage diff`,
`inspect` Coverage section) extend rather than redesign it.

## Shape

The `coverage_outcome` block is OPTIONAL on any envelope. When present, it
is an object discriminated by the `kind` field. Two kinds are defined at
v1:

### `kind: "fact-set"`

Emitted when Coverage Facts were successfully derived (or retrieved) for
the relevant run.

```json
{
  "kind": "fact-set",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "mapping_granularity": "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "summary": { ... CoverageSummary.to_dict() ... }
}
```

`mapping_granularity` enum mirrors the binding constraint in
`decisions/2026-05-15-coverage-facts-json-layout.md`.

### `kind: "unavailable"`

Emitted for the REQ-COV-004 outcome: no Coverage Facts could be produced
or retrieved for the relevant run.

```json
{
  "kind": "unavailable",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "reason": "missing-native-payload" | "native-payload-corrupt" | "run-not-found",
  "detail": "human-readable explanation"
}
```

The `reason` enum is the set of `REASON_*` constants defined in
`src/novetest/coverage/results.py`. Adding a new reason requires updating
the enum list here AND adding the constant in that module.

## Binding constraints

1. **`kind` is the discriminator.** Consumers must branch on `kind`
   first. Fields outside the discriminated set for a given kind are
   illegal.
2. **`run_reference` is mandatory in both kinds.** It identifies which
   run the outcome belongs to so consumers do not have to correlate
   externally.
3. **Per-kind required fields are mandatory.** `fact-set` always carries
   `mapping_granularity` + `summary`; `unavailable` always carries
   `reason` + `detail`. Missing any required field is a wire-contract
   violation.
4. **Block omission semantics.** When a command was not asked to produce
   coverage at all (e.g. `novetest run` without `--coverage`), the
   `coverage_outcome` key is OMITTED entirely from `data`. Emitting
   `null` is forbidden — it breaks the byte-equivalence guarantee for
   non-coverage envelopes.
5. **Schema version unchanged.** This block is an additive extension to
   `data` on commands that opt in to coverage. The envelope-level
   `schema: novetest/v1` stays. Bumping requires its own decision.

## Forward-compatible extension rules

- Adding a new `kind` requires a v2 of this decision.
- Adding a new optional field inside an existing `kind` is non-breaking
  and does not require a decision update.
- Adding a new `reason` requires updating the enum list above and
  adding the corresponding constant in `coverage/results.py`.

## Affected commands

- `novetest run --coverage` — present `kind: "fact-set"` on success;
  `kind: "unavailable"` is not reachable via this verb today (the
  failure surfaces upstream as `adapter-missing-plugin` / engine
  readiness errors, before `coverage_outcome` is set). Locked by
  `tests/unit/cli/test_run_cmd.py`.
- `novetest coverage show <run_id>` (future Phase 2 DoD #2 slice) — must
  emit both kinds.
- `novetest coverage diff <id1> <id2>` (future Phase 2 DoD #2 slice) —
  emits one `coverage_outcome` per run reference plus its own
  diff-specific payload (out of scope for this decision; that slice may
  add its own decisions entry for the diff payload shape).
- `novetest inspect <run_id>` (future Phase 2 DoD #3 slice) — should
  reuse this shape inside its Coverage section so consumers see one
  consistent block across verbs.

## Rationale

The shape was field-tested by Manual Test on the `--coverage` wiring
slice and confirmed clean across happy path, both flag spellings, both
arg orderings, no-coverage byte-equivalence, help surface, and
python-API parity. Freezing now is cheap and prevents the next CLI verb
from improvising a different shape.

## Affected teams / files

- **Orchestration Team** — owns the projection logic
  (`cli/app.py::_coverage_outcome_payload`). Future CLI verbs that emit
  this block reuse the same projection or extend it through the
  forward-compatible extension rules above.
- **Coverage Team** — owns the enum source-of-truth
  (`coverage/results.py::REASON_*`). Adding a new reason requires
  coordination with this decision.
- **All teams** — the shape is binding for any envelope that emits a
  `coverage_outcome` block.

## Effective date

2026-05-16.

## Supersedes

None. First decision on the `coverage_outcome` envelope shape.
