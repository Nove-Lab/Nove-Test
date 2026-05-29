---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-29
slug: localization-cli
related:
  - design/implementation-plan/delivery-phasing.md
  - design/interace-contract/localization.md
  - design/workflows/localization.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - agent-comms/history/2026-05-28-localization-engine-complete.md
---

# Task: Localization CLI sweep — verbs, `--formula`/`--top-n` flags, `inspect` section, `localization_outcome` envelope (Phase 4 §4 entry)

This slice **projects the now-complete Localization engine surface onto
the CLI**. The engine is 100% Internal-table covered (per
`agent-comms/history/2026-05-28-localization-engine-complete.md`); your
job is the pure CLI projection — same pattern Coverage and Regression
followed.

This is the **fourth application** of the project's `engine → CLI →
freeze` cadence; you are mirroring the Phase 3 Regression CLI slice
(`c074226`) almost line-for-line. Read that diff before you start —
your code will rhyme with it.

## Goal

Ship the External row of the Localization interface table
(`design/interace-contract/localization.md`):

1. `novetest localization <run_id>` (verb)
2. `novetest localization latest` (verb)
3. `inspect` Localization section (engine projection inside the
   aggregated single-run view)
4. `--formula <name>` flag (closed enum)
5. `--top-n <int>` flag (positive integer override of default 10)
6. `localization_outcome` envelope block discriminated by `kind` —
   **working draft** for this slice; PM freezes the shape AFTER
   Manual Test fields it (same cadence the 3 prior envelope shapes
   followed).

When this lands, Phase 4 DoD bullets **[186]** and **[189]** close.
**[187]** is partially satisfied (per-test mode populates correctly;
the `sbfl_aggregate` / `failure_proximity` modes are separate
post-CLI Localization engine slices, not your work).

## Engine surface you consume (do NOT modify)

All entry points are re-exported from `novetest.localization`. Read
their signatures from `src/novetest/localization/__init__.py`:

```python
from novetest.localization import (
    LocalizationFinding,
    LocalizationUnavailable,
    FORMULAS,                         # frozenset; closed enum
    derive_localization_findings,     # (store, run_ref, *, top_n=10, formula="ochiai") -> Finding | Unavailable
    derive_latest_localization,       # (store, *, formula="ochiai", top_n=10)         -> Finding | Unavailable
    get_localization_findings,        # (store, run_ref)                                -> Finding | Unavailable (cache-only; missing → REASON_MISSING_DERIVED_FACTS)
    check_localization_availability,  # (store, run_ref)                                -> bool
    resolve_latest_analyzable_run,    # (store)                                         -> RunReference | Unavailable
    REASON_MISSING_DERIVED_FACTS,     # = "missing_derived_facts" (underscore form per v2 §X′)
)
```

All four `derive*`/`get*`/`resolve*` calls return a union;
`isinstance(outcome, LocalizationUnavailable)` is the discriminator.
The Unavailable carries a 5-element `reason` from `KNOWN_REASONS`
(v2 supersede §X′), a `run_reference: RunReference | None`, and a
`detail: str | None`.

**Forbidden:** do not touch `src/novetest/localization/**`. If a
mismatch surfaces between this brief's wire-shape contract and the
engine's `to_dict()` output, the engine is the source of truth — file
`agent-comms/questions/orchestration-team-2026-05-29-<slug>.md` and
stop.

## Wire shape (working draft for this slice)

The `localization_outcome` block is OPTIONAL on the envelope. When
present it is an object discriminated by `kind`. Two values at v1.

### `kind: "fact-set"`

Emitted when Localization Findings were successfully derived OR
retrieved via cache for the requested run.

```json
{
  "kind": "fact-set",
  "run_reference":     { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "mode":              "sbfl_per_test",
  "confidence":        "high" | "medium" | "low",
  "primary_formula":   "ochiai" | "op2" | "dstar2" | "tarantula",
  "alternate_scores_available": ["op2", "dstar2", "tarantula"],
  "derived_at":        <epoch_ms>,
  "top_n":             <int>,
  "total_candidates":  <int>,
  "entries": [
    {
      "schema_version": 1,
      "rank":              <int>,
      "score_raw":         <float>,
      "score_normalized":  <float>,
      "alternate_scores":  { "op2": <float>, "dstar2": <float>, "tarantula": <float> },
      "code_location":     { ...CodeLocation 6-key shape per v1 §4 },
      "related_failed_tests": ["<node_id>", ...],
      "evidence_citations":  [ { ...EvidenceCitation 3-key shape per v1 §5 }, ... ],
      "evidence_lines":      [<int>, ...],
      "tied_with":           ["entry_index_<i>", ...]
    }
  ],
  "warnings": [],
  "metadata": {}
}
```

**Source of truth:** `LocalizationFinding.to_dict()` — 12 keys (v1 §1).
The projection strips the top-level `schema_version` and prefixes
`kind: "fact-set"`. The 9-key `LocalizationEntry.to_dict()` (v1 §2),
6-key `CodeLocation.to_dict()` (v1 §4), and 3-key
`EvidenceCitation.to_dict()` (v1 §5) all round-trip verbatim — do not
re-shape them in the CLI projection.

Notes on specific fields:
- `mode` — only `"sbfl_per_test"` is emitted by Phase 4 entry; aggregate/proximity are future engine slices.
- `alternate_scores_available` is **`list[str]`**, not `bool` (per v1 §1; corrected from the original handoff draft).
- `tied_with[i]` is the 0-based index INTO the truncated `top_n` list — entries truncated out lose their `tied_with` refs.
- `evidence_lines` is engine-capped at 10.
- `score_normalized` is **global-not-truncated** min-max — top entry may be < 1.0 if a higher-score candidate exists outside `top_n`.

### `kind: "unavailable"`

Emitted when Localization Findings cannot be produced (or are not
cached and the verb is read-only). Unavailable is **data, not a
transport error** — envelope `ok` stays `true`, exit code stays `0`.

```json
{
  "kind": "unavailable",
  "run_reference": null | { "run_id": "<ULID>", "created_at": <epoch_ms>, "schema_version": 1 },
  "reason": "no_failed_tests" | "no_coverage" | "no_run_evidence"
          | "missing_derived_facts" | "run_not_analyzable",
  "detail": "<string>" | null
}
```

**Source of truth:** `LocalizationUnavailable.to_dict()` — 3 keys
(v2 §6′), key order `run_reference`, `reason`, `detail`, all keys
always present (null-not-absent). Reasons are the closed 5-element
`KNOWN_REASONS` (v2 §X′). The projection prefixes
`kind: "unavailable"`.

**Underscore vs hyphen convention pin:** Localization reasons use
**underscore form** (`missing_derived_facts`), distinct from
Regression's hyphenated form (`missing-derived-facts`). Do NOT
normalize.

## Verbs — pinned semantics

### `novetest localization <run_id>` (default behavior + flags)

```
novetest localization <run_id> [--formula <name>] [--top-n <int>]
```

- `_resolve_run_reference(store, "localization", run_id)` first — fake
  run_id → structured `not-found` envelope, exit 2 (same pattern as
  `regression compare`, `coverage show`, `inspect`).
- Then call `derive_localization_findings(store, ref, top_n=N, formula=F)`.
  The engine cache-short-circuits on disk hit.
- Tombstoned input → `LocalizationUnavailable(reason="run_not_analyzable")`
  with `ok: true`, exit 0 — surfaces as `kind: "unavailable"`.
- Coverage missing / `mapping_granularity != "per-test"` →
  `LocalizationUnavailable(reason="no_coverage")`.
- No failed tests → `LocalizationUnavailable(reason="no_failed_tests")`.

`--formula` validation:
- Closed enum from `FORMULAS = {"ochiai", "op2", "dstar2", "tarantula"}`
  (note `"dstar2"` not `"dstar"` — pinned by v1 §1, asymmetric with the
  doc-level "DStar" branding).
- Default: `"ochiai"`.
- Invalid value → structured envelope with `code: "invalid-flag"`,
  exit 2 (transport error). Do NOT delegate to the engine for this
  validation; reject at the CLI boundary so the engine never sees a bad
  string.

`--top-n` validation:
- Positive integer.
- Default: `10`.
- Zero / negative → `code: "invalid-flag"`, exit 2.

### `novetest localization latest` (no positional args)

```
novetest localization latest [--formula <name>] [--top-n <int>]
```

- `derive_latest_localization(store, formula=F, top_n=N)` end-to-end.
- Empty store → `LocalizationUnavailable(reason="no_run_evidence", detail="no runs in store")`.
- All runs non-analyzable → `LocalizationUnavailable(reason="run_not_analyzable", detail="no analyzable runs in store (N candidates checked)")`.
- Same flag validation as the explicit-run verb.

### `inspect <run_id>` extends — Localization section

`inspect` is a **pure read over stored evidence** (no derivation, no
subprocess). For Localization the rule is **cache-only**:

- Call `get_localization_findings(store, inspected_run_ref)`.
- Cache hit → emit `localization_outcome.kind == "fact-set"` with the
  cached findings (whatever `--formula` / `--top-n` they were derived
  with — `inspect` does not re-pivot).
- Cache miss → emit `localization_outcome.kind == "unavailable"` with
  `reason: "missing_derived_facts"`, `detail: "findings not yet derived"`,
  and `run_reference` populated (the engine fills this when the input
  ref resolves but cache is empty).

This is **deliberately different from `inspect`'s Regression handling**:
Regression in inspect composes (`find_runs_for_target` + `compare_runs`)
because Regression has no per-run cache (the cache is per-pair, and the
"immediate-prior" pair is per-inspection). Localization HAS a per-run
cache (`<store>/localization/findings/run_<id>/localization_findings.json`),
so cache-only is the right primitive — mirrors Coverage's inspect
behavior (cache-only via `get_coverage_facts`).

**`sub_reports["localization"]` marker** flips `"available"` ↔
`"unavailable"` to mirror the discriminated `kind` (same pattern Coverage
and Regression follow). When the cache is empty, the marker reads
`"unavailable"` even though the underlying run is analyzable — the
sub_reports field reflects WHAT IS IN THE ENVELOPE, not what could be
derived.

## Files to touch (explicit allowlist)

**Edit:**
- `src/novetest/cli/app.py` — add `localization_app` sub-App, two verbs
  (`localization` for `<run_id>`, `localization latest`), the
  `_localization_outcome_payload` projection helper. Remove
  `"localization"` from the `_register_flat_stub` loop at line 744.
  Add `--formula` / `--top-n` flag handling. Mirror `regression_app`
  structure (lines 548–608).
- `src/novetest/orchestration/workflows/inspect.py` — extend
  `InspectView` with `localization_outcome: LocalizationFinding |
  LocalizationUnavailable` field; add `_resolve_inspect_localization`
  helper (cache-only via `get_localization_findings`); `to_dict()`
  emits top-level `localization_outcome` block; flip
  `sub_reports["localization"]` from hardcoded `"unavailable"` to
  `"available" if localization_present else "unavailable"`. Add the
  duplicated `_localization_outcome_section` projection helper (same
  precedent as `_coverage_outcome_section` / `_regression_outcome_section`
  — `orchestration → cli` import would cycle).
- `tests/integration/cli/test_subcommand_stubs.py` — drop `"localization"`
  from the parametrize list.

**Add:**
- `tests/unit/cli/test_localization.py` (`novetest localization <run_id>`)
- `tests/unit/cli/test_localization_latest.py`
- `tests/unit/orchestration/workflows/test_inspect_localization.py`
- `tests/integration/cli/test_localization_e2e.py`

**Do NOT touch:**
- `src/novetest/localization/**` — engine territory (Localization team)
- `src/novetest/models/**` — Memory team
- `src/novetest/run/**`, `coverage/**`, `regression/**`, `memory/**` —
  other teams
- `agent-comms/decisions/**` — PM-only

## Verb behaviors — test expectations (~26 net new tests)

### `tests/unit/cli/test_localization.py` (10 cases)

1. Happy path: real `LocalizationFinding` → `kind: "fact-set"`, `data.localization_outcome.entries[0].rank == 1`, top-level `schema_version` absent.
2. Cache hit preserves `derived_at` (engine short-circuit verified by spy on `build_spectra`).
3. Fake run_id → structured `not-found` envelope, exit 2 (`code: "not-found"`).
4. Tombstoned run → `kind: "unavailable"`, `reason: "run_not_analyzable"`, `ok: true`, exit 0.
5. Run with no failed tests → `kind: "unavailable"`, `reason: "no_failed_tests"`.
6. Run with coverage missing → `kind: "unavailable"`, `reason: "no_coverage"`.
7. `--formula op2` flips `primary_formula` to `"op2"`, removes `"op2"` from `alternate_scores`, adds `"ochiai"` to `alternate_scores`.
8. `--formula bogus` → `code: "invalid-flag"`, exit 2 BEFORE engine call (assert engine spy not invoked).
9. `--top-n 3` truncates `entries` to ≤ 3.
10. `--top-n 0` → `code: "invalid-flag"`, exit 2.

### `tests/unit/cli/test_localization_latest.py` (5 cases)

1. Happy path: latest analyzable run → `kind: "fact-set"`, projection identical to `<run_id>` verb.
2. Empty store → `kind: "unavailable"`, `reason: "no_run_evidence"`, `detail: "no runs in store"`, `run_reference: null`.
3. All-tombstoned store → `kind: "unavailable"`, `reason: "run_not_analyzable"`, `detail` matches the engine's "no analyzable runs in store (N candidates checked)" template.
4. `--formula tarantula --top-n 5` forwards both kwargs to `derive_latest_localization`.
5. Uninitialized (no `.novetest/`) → standard uninitialized envelope, exit 2.

### `tests/unit/orchestration/workflows/test_inspect_localization.py` (8 cases)

1. Cache hit (existing `localization_findings.json`) → `localization_outcome.kind == "fact-set"`, `sub_reports["localization"] == "available"`.
2. Cache miss on analyzable run → `kind: "unavailable"`, `reason: "missing_derived_facts"`, `sub_reports["localization"] == "unavailable"`.
3. Cache miss on a run with Coverage but no failed tests → `reason: "missing_derived_facts"` (NOT `"no_failed_tests"` — `get_localization_findings` is cache-only, so cache empty always surfaces as `missing_derived_facts`; the `no_failed_tests` reason only fires from `derive_localization_findings`).
4. Inspecting a tombstoned run with cached findings → `kind: "fact-set"` (cache wins; tombstoned-input gating happens at `derive` time, not at `get` time — confirm against engine handoff).
5. Inspecting a tombstoned run WITHOUT cached findings → `kind: "unavailable"`, `reason: "missing_derived_facts"`.
6. Fake run_id → structured `not-found`, exit 2 (same as Regression inspect).
7. `inspect` does NOT call `derive_localization_findings` (spy assertion — orthogonal to the cache-only contract).
8. `sub_reports["localization"]` marker flips consistently across the above 6 happy/unhappy paths.

### `tests/integration/cli/test_localization_e2e.py` (3 cases)

1. Subprocess: `localization <run_id>` against a tmp Project Store seeded with the `localization-branch` fixture's expected on-disk Run Record + Coverage Facts → emits `kind: "fact-set"`, `entries[0].code_location.symbol == "divide"`, `entries[0].score_raw == 1.0`.
2. Subprocess: `localization latest` against the same store → byte-equivalent envelope to (1).
3. Subprocess: `inspect <run_id>` after running `localization <run_id>` once → `data.localization_outcome.kind == "fact-set"`, `sub_reports.localization == "available"`.

Total: **~26 new tests**. Existing `test_inspect.py` may need `_patch_memory` updates to stub the new `get_localization_findings` call (similar to how it was updated for `find_runs_for_target` in the Regression CLI cycle); count any necessary updates separately and report in the handoff.

## Worktree & branch

Branch: `novetest-localization-cli` (off `main` tip `f2243b8`).

## Verification gate

- `uv run pytest -q tests/unit tests/integration` — all green.
  Worktree baseline at `f2243b8`: **611 passed + 5 skipped** (the 5
  skips are Node-dependent Jest integration; expected). Expected delta:
  **~+26 new tests**, all green; no unrelated count drift.
- `uv run mypy` — clean, `--strict`, no new source files. Source file
  count remains **69** (you are editing 2 source files, not adding any).

## DoD bullets believed closed

When you write your handoff, name these in the "DoD bullets believed
closed" list. PM verifies and ticks during cycle cleanup:

- `delivery-phasing.md` Phase 4 §4 **[186]** —
  "`novetest localization latest --output json` against
  `localization-branch` ranks the bug in top 3." (Integration test
  case 1 in `test_localization_e2e.py` closes this; the engine already
  ranks `divide` at #1 with Ochiai 1.0 per the engine-completion handoff.)
- `delivery-phasing.md` Phase 4 §4 **[189]** —
  "All four formulas computed and persisted; `--formula` flag selects
  which is presented as primary." (Engine already computes & persists
  all four; your `--formula` flag closes the "selects which is
  presented as primary" half.)

Do NOT claim **[187]** ("Mode field populated correctly across all
three fixtures") — that requires `sbfl_aggregate` /
`failure_proximity` mode engines + their fixtures, which are
post-CLI Localization slices, not this work.

Do NOT claim **[188]** (perf NFR-LOC-002) — separate perf cycle.

## Out of scope (do NOT do)

- `sbfl_aggregate` mode engine work (post-CLI Localization slice).
- `failure_proximity` mode engine work (post-CLI Localization slice).
- `localization-aggregate-only` / `localization-no-coverage` fixtures
  (Localization team territory; needed for the degraded-mode slices).
- Perf NFR-LOC-002 (separate perf cycle).
- Modifying any engine code (`src/novetest/localization/**` is
  frozen as far as this slice is concerned).
- Default-verb alias `novetest <target>` ≡ `novetest test <target>`
  (Phase 6).
- `--baseline` / `--since` overrides (Phase 6 / Recommendation
  synthesis territory).
- Freezing the `localization_outcome` envelope shape — that is
  PM's job AFTER Manual Test fields the projection.

## Conventions reminders

- `--strict` mypy stays clean.
- CLI handlers are thin: wrap the engine call + the v1 envelope.
  No business logic.
- The 12-key `LocalizationFinding.to_dict()` / 9-key
  `LocalizationEntry.to_dict()` / 6-key `CodeLocation.to_dict()` /
  3-key `EvidenceCitation.to_dict()` / 3-key
  `LocalizationUnavailable.to_dict()` are LOAD-BEARING — do not
  re-shape them in the projection. The projection's only job is to
  add `kind` and strip the top-level `schema_version`.

## Post-cycle PM follow-up (informational)

After Manual Test fields the working draft, PM writes
`decisions/2026-05-XX-localization-outcome-envelope-shape.md` to
freeze the wire shape (4th application of the ship → field-test →
freeze cadence). The frozen decision will mirror the structure of
`decisions/2026-05-28-regression-outcome-envelope-shape.md` and
`decisions/2026-05-16-coverage-outcome-envelope-shape.md`.

If you discover **shape divergences from this brief** (e.g. an engine
`to_dict()` output that doesn't match the JSON-shape table above), do
NOT improvise — file a Run-team-style "deviations from the brief"
section in your handoff. PM resolves before the freeze.
