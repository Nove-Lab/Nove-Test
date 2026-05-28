---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-28
slug: localization-finding-shape
related:
  - design/interace-contract/localization.md
  - design/implementation-plan/localization-strategy.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/findings/manual-test-team-2026-05-28-localization-phase4-entry.md
---

# Decision: Localization Finding schema v1

CEO-approved on 2026-05-28. Pins the v1 persistence and wire shape of
`LocalizationFinding` and its companion types (`LocalizationEntry`,
`CodeLocation`, `EvidenceCitation`, `LocalizationUnavailable`),
introduced by the Phase 4 entry slice (commit `bbb0356`), so the
upcoming `novetest localization` CLI verb cycle extends rather than
redesigns it. Same ship -> field-test -> freeze cadence Coverage
(`2026-05-16`) and Regression (`2026-05-28`) followed.

## Source of truth (anchors)

- `src/novetest/models/localization_finding.py` — `LocalizationFinding`,
  `LocalizationEntry`, `CodeLocation`, `EvidenceCitation` model
  definitions + `to_dict()` serializers.
- `src/novetest/localization/results.py` — `LocalizationUnavailable` +
  `REASON_*` constants + `KNOWN_REASONS`.
- All shapes below are frozen at the form persisted by commit `bbb0356`
  and field-tested in findings
  `manual-test-team-2026-05-28-localization-phase4-entry.md`.

## Frozen shapes

### §1. `LocalizationFinding` — 12 top-level keys

The persisted JSON document at
`<store>/localization/findings/run_<run_id>/localization_findings.json`
carries exactly these 12 keys in this order (per `to_dict()`):

```json
{
  "schema_version": 1,
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "engine_name": "<string>",
  "ecosystem": "<string>",
  "mode": "sbfl_per_test" | "sbfl_aggregate" | "failure_proximity",
  "confidence": "high" | "medium" | "low",
  "formula": "ochiai" | "op2" | "dstar2" | "tarantula",
  "alternate_scores_available": ["<formula>", ...],
  "top_n": <int>,
  "entries": [<LocalizationEntry>, ...],
  "derived_at": <epoch_ms>,
  "metadata": { ... }
}
```

Notes:
- `alternate_scores_available` is `list[str]`, NOT `bool`. Each element
  names another formula computed alongside the primary `formula`. (The
  Phase-4-entry handoff draft incorrectly described this as a bool;
  Manual Test caught it. Pinned `list[str]` here.)
- `derived_at` is epoch-milliseconds; preserved across cache hits (§A).
- `mode` enum is closed at v1. Only `sbfl_per_test` is produced by the
  Phase-4-entry slice; the other two are reserved enum values for the
  follow-up degradation slices.
- `metadata` is free-form dict at v1; consumers MUST NOT depend on any
  field within `metadata` at this schema version.

### §2. `LocalizationEntry` — 9 keys

Per `LocalizationEntry.to_dict()`:

```json
{
  "rank": <int>,
  "tied_with": ["entry_index_<i>", ...],
  "code_location": <CodeLocation>,
  "score_raw": <float>,
  "score_normalized": <float>,
  "formula": "<formula>",
  "alternate_scores": { "<formula>": <float>, ... },
  "related_failed_tests": ["<node_id>", ...],
  "evidence_citations": [<EvidenceCitation>, ...]
}
```

Notes:
- `rank` is 1-based dense (ties share a rank, next rank skips).
- `formula` is per-entry AND matches the top-level
  `LocalizationFinding.formula` for entries derived by the same SBFL
  pass. Per-entry duplication is intentional — it keeps each
  `LocalizationEntry` self-describing if extracted in isolation.
- `score_normalized` is min-max within the ENTIRE finding set BEFORE
  `top_n` truncation. It may equal `score_raw` when the global maximum
  already appears within `top_n`.
- `alternate_scores` carries the other formulas' scores for the SAME
  `code_location` so consumers can re-rank without re-derivation.

### §3. `tied_with` convention

Stringly-typed positional references in the literal format
`"entry_index_<i>"` where `<i>` is the 0-based index of the tied entry
inside the truncated `entries` tuple. So `"entry_index_0"` points at
the top-ranked entry. References stay strictly within
`[0, len(entries))` — cross-boundary references to entries past
`top_n` are forbidden.

### §4. `CodeLocation` — 6 keys

Per `CodeLocation.to_dict()`:

```json
{
  "kind": "symbol" | "line" | "branch" | "file",
  "file": "<repo-relative path>",
  "symbol": "<qualname>" | null,
  "line_range": [<start>, <end>] | null,
  "primary_line": <int>,
  "evidence_lines": [<int>, ...]
}
```

Notes:
- `kind` enum closed at v1. `symbol` and `file` are produced today;
  `line` and `branch` are reserved enum values (no producer yet — the
  Phase-4-entry slice does not emit them). Consumers MUST accept all
  four values.
- `symbol` and `line_range` are independently nullable. File-level
  entries (module-level code, fallback when the symbol resolver yields
  nothing) carry `symbol=null, line_range=null`. Symbol-level entries
  carry both populated.
- `primary_line` is ALWAYS populated (never null).
- `evidence_lines` is capped at 10 entries by the derive layer (lines
  beyond the cap are dropped; the cap is an implementation detail
  callers MUST NOT assume).
- **No `is_test_code` field.** See §N.

### §5. `EvidenceCitation` — 3 keys

Per `EvidenceCitation.to_dict()`:

```json
{
  "kind": "test_result" | "coverage_fact",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "selector": { ... }
}
```

`selector` is a discriminated payload whose shape depends on `kind`:

- `kind == "test_result"` ->
  `selector = {"test_id": "<node_id>", "outcome": "failed"}`
- `kind == "coverage_fact"` ->
  `selector = {"file": "<repo-relative path>", "lines": [<int>, ...]}`

`kind` enum closed at v1. `regression_fact` is reserved for the
aggregate-mode follow-up slice (FLUCCS-style regression-aware
reweighting) but NOT in the closed set today.

### §6. `LocalizationUnavailable` — 3 fields

Per the dataclass:

```python
@dataclass(slots=True, frozen=True)
class LocalizationUnavailable:
    run_reference: RunReference | None
    reason: str   # one of KNOWN_REASONS
    detail: str | None = None
```

`KNOWN_REASONS` set at v1 (all four field-tested by Manual Test, each
firing in its documented target condition):

| Reason | Fires when |
|---|---|
| `no_failed_tests` | Run Record has 0 failed test results |
| `no_coverage` | Coverage Facts unavailable OR have `mapping_granularity != "per-test"` |
| `no_run_evidence` | `retrieve_run_evidence` raises (no live and no tombstoned record) |
| `run_not_analyzable` | Two overloaded sub-cases today: (a) findings not yet derived (cache empty), (b) Run Record is tombstoned |

The `run_not_analyzable` overload is acknowledged and will be split.
See §X.

**Known gap:** `LocalizationUnavailable` has NO `to_dict()` method at
v1, unlike `RegressionUnavailable`. CLI / orchestration code that
needs to serialize this into a JSON envelope must format it ad-hoc
until the follow-up CLI verb cycle adds `to_dict()`. The field shape
above is binding; the serializer is the only outstanding item.

### §7. Persistence path layout

```
<store>/localization/findings/run_<run_id>/localization_findings.json
```

One file per run. Whole-document overwrite on re-derive. No partial
writes, no auxiliary sidecar files at v1. This exact path is
load-bearing — Memory's `_availability_flags` probe
(`src/novetest/memory/store.py::_availability_flags`) auto-flips
`MemoryEntry.has_localization_findings` based on the existence of this
exact path. Renaming or relocating requires a coordinated Memory +
Localization change and a new decision.

## §A. Cache short-circuit semantics

- `derive_localization_findings()` and `get_localization_findings()`
  MUST preserve `derived_at` across cache hits — re-deriving the same
  run does NOT re-stamp the timestamp. Manual Test confirmed this with
  50ms sleeps between calls (`derived_at` byte-identical across three
  calls).
- This stable-`derived_at` guarantee is binding; later consumers
  (e.g. Regression's coverage-coupling check) may depend on it.

## §N. Test code in localization output — intended behavior

Localization output may include test code lines in the ranking. This
is intended behavior. The schema does NOT carry a discriminator for
"this is test code," and `derive_localization_findings` does NOT
post-rank-filter test paths.

Rationale:

1. **Test code itself can be the source of a defect.** Faulty
   assertions, incorrect fixture setup, and buggy test logic are
   legitimate failure causes. The user-facing question Localization
   answers — "which line is most likely to be buggy?" — sometimes
   genuinely points at a test line. Any test-path-based filter would
   silence this signal and force users to debug production code when
   the actual bug is in the test.
2. **SBFL math naturally degrades test-code rank in realistic suites.**
   A failing test's function body is executed only by its own test, so
   under Ochiai its score is `1 / sqrt(totalfail)`. With a single
   failing test (`totalfail = 1`) the test body ties with the bug at
   1.0; with multiple failing tests sharing a production code path the
   bug's score holds near 1.0 while test-body scores drop
   (`totalfail = 5` -> 0.447; `totalfail = 10` -> 0.316). The "rank-1
   tie between bug and test body" observed in the Phase-4-entry
   verification fixture is a single-failing-test corner case, not a
   representative failure mode.

`CodeLocation` therefore does NOT carry an `is_test_code` discriminator
at v1. Future CLI surfaces MAY offer presentation-layer flags (e.g. a
`--exclude-test-code` opt-in toggle) without altering the persisted
Finding shape, but that decision is deferred to the CLI verb cycle.

## §X. Open refinement — `REASON_MISSING_DERIVED_FACTS` split (planned)

CEO-approved 2026-05-28: the `run_not_analyzable` overload will be
split into two reason codes, mirroring Regression's pattern
(`src/novetest/regression/results.py:31`):

| Reason | Meaning |
|---|---|
| `missing_derived_facts` (new) | Cache empty — findings not yet derived for this run. Recoverable: call `derive_localization_findings`. |
| `run_not_analyzable` (retained, narrower) | Run is structurally non-derivable (tombstoned record, evidence corruption). NOT recoverable. |

A task brief for the Localization team will queue this change. When
implemented, this decision is superseded by v2; until then, callers
must rely on the `detail` string to disambiguate the two sub-cases.

## Binding constraints

1. **`schema_version` is an integer** — the persisted document carries
   `"schema_version": 1` exactly. Bumping requires a v2 of this decision.
2. **Enum closures.** `mode`, `confidence`, `formula`,
   `CodeLocation.kind`, `EvidenceCitation.kind`, and `KNOWN_REASONS`
   are closed at v1. Adding a value requires a v2 of this decision.
3. **All required keys are mandatory.** Optional-by-nullability fields
   on `CodeLocation` (`symbol`, `line_range`) MUST be present as keys
   with `null` value when not applicable; omitting the key is a
   wire-contract violation. `LocalizationEntry.tied_with` is always
   present (empty list when no ties).
4. **`tied_with` stays within `[0, len(entries))`.** References past
   the truncated tail are forbidden.
5. **Persistence path is exact.** No alternate layouts.
6. **`derived_at` is preserved on cache hits.** Re-stamping is a
   contract violation.

## Forward-compatible extension rules

- Adding a new optional field inside an existing shape is non-breaking
  if the field is omitted entirely when not applicable AND is
  documented in a follow-up decision (or this decision's v2).
- Adding a value to a closed enum requires a v2 of this decision.
- Splitting `run_not_analyzable` per §X is the first planned v2
  trigger.
- Adding `LocalizationUnavailable.to_dict()` is non-breaking (the
  field shape stays); it can land any time without a new decision.

## Affected commands

- **`novetest localization` CLI verb (next Localization cycle)** —
  must emit this shape unchanged. Adding command-specific projection
  fields (e.g. a `--exclude-test-code` flag) is allowed at the CLI
  layer but MUST NOT alter the persisted Finding shape.
- **`inspect` Localization section (Phase 4 follow-up)** — must reuse
  this shape inside its `localization_outcome` block.

## Affected teams / files

- **Localization Team** — owns the shape source-of-truth
  (`models/localization_finding.py`, `localization/results.py`). §X
  split lands here; §6 `to_dict()` addition lands here.
- **Orchestration Team** — owns the CLI projection. A presentation-layer
  `--exclude-test-code` flag is its territory and deferrable to the
  CLI verb cycle.
- **Memory Team** — owns the `has_localization_findings` availability
  flag whose probe path is pinned by §7. Any relocation requires
  coordinated change.
- **All teams** — the shape is binding for any envelope / persisted
  document that emits these structures.

## Effective date

2026-05-28.

## Supersedes

None. First decision on the Localization Finding shape. Future v2
expected per §X.
