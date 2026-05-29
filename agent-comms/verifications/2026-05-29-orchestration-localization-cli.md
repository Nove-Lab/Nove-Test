---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
slug: orchestration-localization-cli
created: 2026-05-29
related:
  - agent-comms/handoffs/orchestration-team-2026-05-29-localization-cli.md
  - agent-comms/tasks/orchestration-team-2026-05-29-localization-cli.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
---

# Verification: Localization CLI slice (Phase 4 §4)

## Merged commit

`385e2dc` — `localization: project engine onto CLI — verbs + --formula/--top-n + inspect section + localization_outcome envelope` (rebased onto `6d9f463` to keep linear history; one WORKLOG.md conflict resolved by keeping both 2026-05-29 entries — localization above cargo).

## Source handoff consumed

- `agent-comms/handoffs/orchestration-team-2026-05-29-localization-cli.md` (orchestration-team, 2026-05-29).

## Scope of the slice

The 4th application of the project's `engine → CLI → freeze` cadence (mirrors the Regression CLI slice `c074226`).

- Two real verbs: `novetest localization <run_id>` and `novetest localization latest`.
- Flags: `--formula` ∈ {`ochiai`, `dstar2`, `op2`, `tarantula`} (default `ochiai`), `--top-n` positive int (default `10`). Validated at the CLI boundary → exit 2 `invalid-flag` on bad values.
- New `localization_outcome` envelope block, discriminated by `kind` ∈ {`fact-set`, `unavailable`}, additive (top-level envelope `schema: novetest/v1` UNCHANGED — same pattern as `coverage_outcome` / `regression_outcome`).
- `novetest inspect <run_id>` gains a `localization_outcome` section (cache-only via `get_localization_findings`) + flips `sub_reports["localization"]` ∈ {`available`, `unavailable`}.

**No engine code touched.** The projection is a verbatim pass of `LocalizationFinding.to_dict()` / `LocalizationUnavailable.to_dict()` — adds the `kind` discriminator, strips the top-level `schema_version`. Where the task brief's pseudo-JSON sketch differed from the actual `to_dict()` output, the projection follows the code (handoff §Deviations from the brief).

## Test-gate result on the merged tip

```
uv run pytest -q tests/unit tests/integration → 667 passed, 5 skipped
uv run mypy                                    → Success: no issues found in 70 source files (strict)
```

The 5 skips: 3 pre-existing Node-dependent jest integration tests + 2 new Rust-dependent cargo integration tests (the parallel cycle's other slice).

## Wire shapes pinned by running the merged code

Probed against `tests/fixtures/projects/localization-branch` (the deliberate-bug pytest fixture: `divide(a, b)` returns `a + b`).

### `localization_outcome` fact-set shape — 12 top-level keys (NO `schema_version`)

`novetest localization <run_id> --output json` after `novetest run --coverage`:

```json
{
  "command": "localization",
  "data": {
    "localization_outcome": {
      "alternate_scores_available": ["dstar2", "op2", "tarantula"],
      "confidence": "high",
      "derived_at": "<ISO8601>",
      "ecosystem": "python",
      "engine_name": "pytest",
      "entries": [ /* 10 of these by default */ ],
      "formula": "ochiai",
      "kind": "fact-set",
      "metadata": { /* engine-specific */ },
      "mode": "sbfl_per_test",
      "run_reference": { "created_at": <int>, "run_id": "<ULID>", "schema_version": 1 },
      "top_n": 10
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Keys to anchor:
- `kind` discriminator at position 0 of the projection (the discriminator the consumer branches on).
- `formula` is the **presentation primary** (the formula whose score drives `rank`). The other 3 are always computed; their names appear in `alternate_scores_available`.
- `mode` is `"sbfl_per_test"` (NOT `"per-test"` — handoff prose abbreviates).
- `ecosystem` / `engine_name` echo the **Run's** native engine (here `"python"` / `"pytest"`), NOT the localization engine itself.
- Top-level `schema_version` is **stripped** (the engine emits it; the CLI projection drops it because envelope-level `schema` already pins the version).

### `entries[*]` shape — 9 keys

```json
{
  "alternate_scores": { "dstar2": 0.0, "op2": 1.0, "tarantula": 1.0 },
  "code_location": { /* 6-key sub-shape — see below */ },
  "evidence_citations": [ /* discriminated 3-key shape — see below */ ],
  "formula": "ochiai",
  "rank": 1,
  "related_failed_tests": ["tests/test_calculator.py::test_divide_yields_quotient"],
  "score_normalized": 1.0,
  "score_raw": 1.0,
  "tied_with": ["entry_index_1"]
}
```

- `alternate_scores` keys = `alternate_scores_available` (the 3 non-primary formulas), values are the computed scores per formula.
- `formula` on each entry echoes the **same** top-level primary — the entry-level repeat is redundant by design (mirrors the engine to_dict).
- Entry-level `evidence_lines` does NOT exist — suspicious lines live inside `code_location.evidence_lines` (handoff §Deviations from the brief #2).
- Entry-level `schema_version` does NOT exist — only the top-level finding carries it, and the CLI strips even that (handoff §Deviations from the brief #3).

### `code_location` shape — 6 keys

```json
{
  "evidence_lines": [34],
  "file": "localization_branch/calculator.py",
  "kind": "symbol",
  "line_range": [31, 34],
  "primary_line": 34,
  "symbol": "divide"
}
```

### `evidence_citations[*]` shape — 3 keys (discriminated by `kind`)

```json
{ "kind": "test_result", "run_reference": {...}, "selector": { "outcome": "failed", "test_id": "tests/test_calculator.py::test_divide_yields_quotient" } }
{ "kind": "coverage_fact", "run_reference": {...}, "selector": { "file": "localization_branch/calculator.py", "lines": [34] } }
```

`selector` shape is discriminated on `kind` — test_result carries `{outcome, test_id}`, coverage_fact carries `{file, lines}`. Pin this when writing scenarios.

### `localization_outcome` unavailable shape — 4 keys (ALL ALWAYS PRESENT)

```json
{
  "kind": "unavailable",
  "run_reference": null | { "created_at": <int>, "run_id": "<ULID>", "schema_version": 1 },
  "reason": "no_failed_tests" | "no_coverage" | "no_run_evidence" | "missing_derived_facts" | "run_not_analyzable",
  "detail": "<human-readable>" | null
}
```

`run_reference` is `null` ONLY for `latest`-resolution edge cases (e.g. empty store, all-non-analyzable runs); for specific-run paths it is always populated even when the reason is `no_run_evidence` (the caller-supplied reference echoes back).

`reason` uses **underscore** form — `no_failed_tests` not `no-failed-tests`. The Localization engine convention is independent of Regression's hyphenated form.

### `inspect` Localization section + sub_reports flag

`novetest inspect <run_id> --output json` after a derive:

```
data.localization_outcome — the same 12-key fact-set OR 4-key unavailable shape above.
data.sub_reports.localization — "available" (cache hit) | "unavailable" (cache miss or upstream unavailable).
```

Cache-miss inspect probe pinned shape:

```json
{
  "kind": "unavailable",
  "reason": "missing_derived_facts",
  "detail": "findings not yet derived",
  "run_reference": { ... }
}
```

`sub_reports` in this case: `{"coverage": "available", "localization": "unavailable", "regression": "unavailable", "replay": "unavailable"}`.

## Verification steps for Manual Test

### 1. End-to-end: run → derive → inspect

```bash
PROBE=/tmp/novetest-manual-localization && rm -rf "$PROBE" && mkdir -p "$PROBE"
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/localization-branch "$PROBE/sut"
cd "$PROBE/sut"
NV=/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest

$NV init --output json | jq .data.store_state         # ready

RUN_ID=$($NV run --coverage --output json | jq -r .data.memory_entry.run_record.run_reference.run_id)
echo "RUN_ID=$RUN_ID"

# Default --formula ochiai, --top-n 10:
$NV localization "$RUN_ID" --output json | jq '.data.localization_outcome | {kind, formula, top_n, alternate_scores_available, n_entries: (.entries|length)}'
# Expect: kind="fact-set", formula="ochiai", top_n=10, alternate_scores_available=["dstar2","op2","tarantula"], n_entries=10
# Top entry symbol should be "divide", score_raw=1.0, rank=1.

$NV localization latest --output json | jq '.data.localization_outcome.kind, .command'
# Expect: "fact-set", "localization.latest"

$NV inspect "$RUN_ID" --output json | jq '.data.sub_reports.localization, .data.localization_outcome.kind, .data.localization_outcome.formula'
# Expect: "available", "fact-set", "ochiai"
```

### 2. Flag-validation invariants (exit 2 `invalid-flag`)

```bash
# --formula bogus:
$NV localization 01ABCDEFGHIJK --formula bogus --output json
# Expect: ok=false, errors[0].code="invalid-flag",
#         message="Invalid --formula='bogus'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']"
#         exit=2

# --top-n 0:
$NV localization 01ABCDEFGHIJK --top-n 0 --output json
# Expect: ok=false, errors[0].code="invalid-flag",
#         message="Invalid --top-n=0; expected a positive integer"
#         exit=2

# Same two scenarios against `localization latest`:
$NV localization latest --formula bogus --output json   # exit 2
$NV localization latest --top-n -5 --output json        # exit 2
```

Flag validation runs BEFORE run resolution — so a bogus flag with a nonexistent run_id still exits 2 `invalid-flag`, not whatever the run-not-found path would be.

### 3. `--formula` / `--top-n` on a fresh derive (cache-miss path)

**This is the IMPORTANT cache subtlety.** On a fresh run (no cached findings):

```bash
PROBE2=/tmp/novetest-manual-localization-b && rm -rf "$PROBE2" && mkdir -p "$PROBE2"
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/localization-branch "$PROBE2/sut"
cd "$PROBE2/sut"
$NV init --output json > /dev/null
RUN_ID=$($NV run --coverage --output json | jq -r .data.memory_entry.run_record.run_reference.run_id)

$NV localization "$RUN_ID" --formula dstar2 --top-n 3 --output json \
  | jq '.data.localization_outcome | {formula, top_n, alternate_scores_available, n_entries: (.entries|length)}'
# Expect: formula="dstar2", top_n=3, n_entries=3,
#         alternate_scores_available=["ochiai","op2","tarantula"]
#         (the 3 non-primary formulas; ochiai now appears here because dstar2 is primary).
```

On a fresh derive, the chosen `--formula` IS honored as the primary. Top-1 under dstar2 in this fixture is `add` (not `divide`) — formulas pick different culprits.

### 4. Cache-hit behaviour — `--formula` / `--top-n` are NOT re-honored

**Critical subtlety to lock down.** Once findings are cached for a run (any prior `localization` or `inspect` call that derived), subsequent `localization <same_run_id>` calls with different `--formula` / `--top-n` return the CACHED finding unchanged — the new flags are silently ignored. This is the engine's documented design (see `derive_localization_findings` docstring: "this slice does NOT auto-invalidate").

```bash
# Continuing from step 3 above:
$NV localization "$RUN_ID" --formula ochiai --top-n 10 --output json \
  | jq '.data.localization_outcome | {formula, top_n, n_entries: (.entries|length)}'
# Expect: formula="dstar2", top_n=3, n_entries=3 — UNCHANGED from the cached derive.
# NOT formula="ochiai", NOT top_n=10.
```

**Manual Test action**: confirm this behaviour and flag whether the silent-ignore-on-cache-hit is acceptable UX or a finding to escalate to PM. (The strategy may be "consumers should know to delete the cache to re-derive with new flags"; document whichever way you land.)

### 5. The 5 `REASON_*` unavailable paths

Probe each of these and confirm the `localization_outcome.kind == "unavailable"` projection with the right `reason` + `detail`:

| Reason | How to trigger |
|---|---|
| `no_run_evidence` | `localization 01FAKEFAKEFAKEFAKEFAKEFAKE` against an empty store (no such run). |
| `no_run_evidence` (latest variant) | `localization latest` against a JUST-initted store with zero runs → `run_reference: null`, `detail: "no runs in store"`. |
| `no_failed_tests` | `run` against a project whose tests all pass, then `localization <run_id>`. |
| `no_coverage` | `run` WITHOUT `--coverage`, then `localization <run_id>` → reason=no_coverage, detail mentioning failure_proximity not yet implemented. |
| `missing_derived_facts` | `inspect <run_id>` (cache-only) on a run before any `localization` call has derived → reason=missing_derived_facts, detail="findings not yet derived". |
| `run_not_analyzable` | Tombstone the run via `memory tombstone <run_id> --reason <r>` if that CLI exists; otherwise hand-tombstone via the store file layout. (Less critical to probe; engine unit tests cover it.) |

For each path, confirm:
- Envelope `ok: true` (the unavailable outcome is a structured response, not an error).
- `kind: "unavailable"`, `reason: <expected>`, `detail` non-null (except possibly latest-no-runs), `run_reference` populated when known.

### 6. `inspect` cache-only contract

`inspect` MUST NOT derive — it only reads cached findings. Confirm:

```bash
# Run without ever calling localization:
$NV init --output json > /dev/null  # fresh store
RUN_ID=$($NV run --coverage --output json | jq -r .data.memory_entry.run_record.run_reference.run_id)

# Inspect immediately:
$NV inspect "$RUN_ID" --output json | jq '.data.sub_reports.localization, .data.localization_outcome'
# Expect: "unavailable", with kind="unavailable", reason="missing_derived_facts"

# After:
$NV localization "$RUN_ID" --output json > /dev/null

# Inspect again — should now hit cache:
$NV inspect "$RUN_ID" --output json | jq '.data.sub_reports.localization, .data.localization_outcome.kind'
# Expect: "available", "fact-set"
```

If `inspect` ever DERIVES on miss (state-mutating instead of cache-only), that's a finding to escalate.

### 7. `derived_at` preservation across cache hits

```bash
$NV localization "$RUN_ID" --output json | jq -r .data.localization_outcome.derived_at
DERIVED_AT_1=$(...)
sleep 2
$NV localization "$RUN_ID" --output json | jq -r .data.localization_outcome.derived_at
DERIVED_AT_2=$(...)
# Expect: DERIVED_AT_1 == DERIVED_AT_2 (cache hit, no re-derive timestamp).
```

## Critical edge cases worth probing

1. **Cache + `--formula` interaction (covered above as step 4).** Most likely the single most surprising behaviour. Worth writing a clear finding either way.

2. **`localization latest` on a store where the latest run is non-analyzable but an earlier one is.** The engine has `resolve_latest_analyzable_run` semantics — confirm it walks past tombstoned / non-analyzable heads correctly. The handoff says `latest` covers "the latest-resolution empty / all-non-analyzable cases" with `run_reference: null`.

3. **Envelope discriminator-position invariance.** Consumers branch on `data.localization_outcome.kind` first. Make sure across ALL 3 surfaces (`localization`, `localization latest`, `inspect`), the `kind` key is present at the same nesting depth and the rest of the payload is shaped consistently.

4. **Entry-level field ABSENCES.** The brief's pseudo-JSON had:
   - entry-level `evidence_lines` — does NOT exist; only `entry.code_location.evidence_lines`.
   - entry-level `schema_version` — does NOT exist.
   - top-level `primary_formula` — does NOT exist; it's `formula`.
   Write at least one scenario that asserts these keys are **absent** (jq `has(...)` returning false), not just that some other expected key is present — to catch any drift in subsequent slices that might add them back.

5. **`alternate_scores_available` list invariance.** Always a 3-element list of strings (the 3 non-primary formulas, sorted). Never includes the primary; never includes a 5th value. Pin this in a scenario.

6. **The `inspect` envelope's existing fields are NOT broken.** This slice added `localization_outcome` to inspect's data block and a new `sub_reports.localization` key. Confirm the pre-existing inspect data keys (`coverage_outcome`, `regression_outcome`, `run_reference`, `run_summary`, `sub_reports`) are still present and unchanged in shape.

## Envelope-schema freeze (PM-side; informational)

- The `localization_outcome` block shape is a **working draft**. After Manual Test fields it, PM freezes via `decisions/2026-05-XX-localization-outcome-envelope-shape.md` (mirrors the two Coverage + Regression envelope freezes). DO NOT freeze any wire shape yourself — surface findings and let PM resolve.
- The 7 schema items the Localization Phase 4 entry handoff flagged for freeze (from the prior cycle) remain PM-side bookkeeping.

## Notes from the merge

- Localization-CLI branch base was `f2243b8` (one PM-comms commit behind main tip `3094d1e`).
- Rebased onto `main` (now `6d9f463` after cargo merge); `WORKLOG.md` conflicted (both 2026-05-29 entries collided) — resolved by keeping both, localization on top (newest), single blank line between entries. `agent-comms/INDEX.md` auto-merged cleanly to match main.
- INDEX.md was regenerated post-merge via `python3 tools/regen_comms_index.py` per the handoff's "action required" callout (the worktree's regen had produced a stale Pending section due to base-commit drift).
- Tip after merge: `385e2dc`. Clean linear history: `3094d1e → 6d9f463 → 385e2dc`.
