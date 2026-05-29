---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-30
slug: localization-outcome-envelope-shape
related:
  - agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/verifications/2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/findings/manual-test-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - src/novetest/cli/app.py
  - src/novetest/localization/results.py
---

# Decision: `localization_outcome` envelope shape — v1 freeze

CEO-approved on 2026-05-30. **5th application of the project's
`engine → CLI → freeze` cadence** (after regression-outcome v1,
localization-finding-shape v1, localization-finding-shape v2,
regression-facts-json-layout). Pins the entire wire surface the two
`novetest localization` CLI verbs emit.

## Scope

This decision pins **the CLI-emitted envelope shape for `localization`
and `localization.latest` commands**, byte-identical to the merged code
at commit `5fa2381`. It is the contract AI consumers query and the
contract every future `localization_outcome`-touching slice MUST
preserve (or supersede with an explicit v2).

In scope:
1. `data.localization_outcome` block shape (the 12/9/6/3-key
   `LocalizationFinding` fact-set + the `LocalizationUnavailable`
   variant), carried from `2026-05-28-localization-finding-shape-v2.md`.
2. The `kind ∈ {"fact-set", "unavailable"}` discriminator added by
   `_localization_outcome_payload`.
3. The envelope-level `warnings[]` for cache-vs-request mismatch.
4. `REASON_NO_RUN_EVIDENCE` semantic boundaries (when this reason
   fires vs when bogus-`run_id` routes to `not-found`).
5. Bogus-`run_id` → `not-found` envelope routing.
6. The `cache_path` template in the warning's details.

Out of scope (explicitly NOT decided here):
- Cyclopts help-text rendering for the `None`-sentinel flags (Manual
  Test Edge 6 finding — future Orchestration UX polish; not
  load-bearing).
- `LocalizationUnavailable.reason` value-set semantics beyond the
  no-run-evidence boundary; the other 4 reasons (`no_failed_tests`,
  `no_coverage`, `missing_derived_facts`, `run_not_analyzable`) are
  owned by Localization engine and the
  `localization-finding-shape-v2` decision.
- Modes (`sbfl_per_test`, `sbfl_aggregate`, `failure_proximity`)
  and their fixtures — Phase 4 §4 #2 future slice.

## Pinned shape

### Top-level envelope (sorted keys per `Envelope.to_dict()`)

```json
{
  "command": "localization" | "localization.latest",
  "data": { "localization_outcome": { ... } },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": [ { ... }? ]
}
```

- `warnings` lives at the **envelope top level** (NOT nested inside
  `localization_outcome`). The shared
  `Envelope.warnings: tuple[EnvelopeWarning, ...]` slot at
  `src/novetest/cli/output.py:52` is the canonical channel. Future
  Localization slices MUST NOT introduce a parallel per-block
  warnings slot.
- `ok` is `true` for both cache hits and fresh derives (cache
  mismatch is a *warning*, not an error). `ok` is `false` only for
  true errors (invalid flag, run not found, etc.).
- Exit code is `0` for the warning-emitting path. Warnings never
  affect exit code.

### `data.localization_outcome` — the discriminated block

Carried from `2026-05-28-localization-finding-shape-v2.md`. The
discriminator is added by `_localization_outcome_payload` (out of
scope to modify in any future Localization slice without v2):

**`kind == "fact-set"`** (cache hit OR fresh derive of a
`LocalizationFinding`):

The 12/9/6/3-key shape pinned by
`2026-05-28-localization-finding-shape-v2.md` (top-level 12 keys,
9-key `entries[*]`, 6-key `entries[*].code_location`, 3-key
`entries[*].alternate_scores`). Not re-listed here — that decision
is the source of truth.

**`kind == "unavailable"`** (`LocalizationUnavailable`):

```json
{
  "kind": "unavailable",
  "reason": "<one of the 5 REASON_* constants>",
  "run_reference": {...} | null,
  "context": {...}
}
```

The 5 `REASON_*` constants live at
`src/novetest/localization/results.py:55-59`:
- `REASON_NO_FAILED_TESTS = "no_failed_tests"`
- `REASON_NO_COVERAGE = "no_coverage"`
- `REASON_NO_RUN_EVIDENCE = "no_run_evidence"`
- `REASON_MISSING_DERIVED_FACTS = "missing_derived_facts"`
- `REASON_RUN_NOT_ANALYZABLE = "run_not_analyzable"`

### `REASON_NO_RUN_EVIDENCE` — semantic boundary

`REASON_NO_RUN_EVIDENCE` (string value `"no_run_evidence"`) fires in
exactly two cases:
1. `localization latest` invoked against a Project Store with **zero
   resolvable runs** (empty store, or all runs tombstoned beyond the
   latest-analyzable resolver's reach).
2. A resolvable Run that **lacks the upstream evidence** the
   Localization engine needs to construct a spectrum (no per-test
   coverage AND no failure evidence).

It does **NOT** fire for:
- **Non-existent `run_id`** passed to `localization <run_id>` —
  those route to an envelope-level error (see §"Bogus-`run_id`"
  below).
- **Tombstoned runs** that the resolver finds — those surface
  `REASON_RUN_NOT_ANALYZABLE`, not `REASON_NO_RUN_EVIDENCE`.
  Verified by Manual Test Edge 2 in the cycle's findings.

This boundary resolves the 2026-05-29 Manual Test Issue §1 (bogus
`run_id` shape divergence) per Option A from the prior cycle close:
keep the envelope-level error for not-found inputs, distinct from
the engine's semantic "this run can't be analyzed" signal.

### Bogus-`run_id` → `not-found` envelope routing

`localization <run_id>` against a non-resolvable `run_id`:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "run-not-found",
      "message": "<run_id not resolvable in the Project Store>",
      "details": {"run_id": "<input>"}
    }
  ],
  "data": {},
  "warnings": []
}
```

Exit code: `2` (`EXIT_USER_INPUT_INVALID`).

This shape is consistent with `inspect`, `coverage`, and `regression`
verbs.

### Cache-vs-request mismatch warning

When either Localization verb returns cached findings AND at least
one of `--formula` / `--top-n` is user-explicit AND the explicit
value differs from the cached value:

```json
{
  "code": "localization-cache-args-ignored",
  "message": "requested --formula='<R>' --top-n=<R> but cached findings were derived with --formula='<C>' --top-n=<C>; delete cache (<cache_path>) and re-run to override",
  "details": {
    "requested": {
      "formula": "<str>",
      "top_n": <int>,
      "formula_explicit": <bool>,
      "top_n_explicit": <bool>
    },
    "cached": {
      "formula": "<str>",
      "top_n": <int>
    },
    "cache_path": "<project-relative path>"
  }
}
```

Source of truth: `src/novetest/cli/app.py:855-927`
(`_build_localization_cache_mismatch_warning`).

Pinned design choices (cross-validated by Manual Test
`findings/manual-test-team-2026-05-30-localization-cache-mismatch-warnings.md`
8 scenarios + 6 edge cases):

1. **One warning per invocation**, even when both flags mismatch.
   The single warning's `details` covers both flags. Multi-warning
   alternatives would introduce ordering questions and split the
   user's mental model. Manual Test explicit vote: keep.
2. **`*_explicit` booleans gate emission.** When `formula_explicit
   == false`, that flag's mismatch alone never triggers the warning.
   The warning's existence implies AT LEAST ONE `*_explicit == true`.
3. **`cache_path` is template-computed, project-relative**:
   `f".novetest/localization/findings/run_{run_id}/localization_findings.json"`.
   The on-disk layout is pinned by `localization/persistence.py` +
   Memory's `_availability_flags` probe. If that layout changes,
   both must move together. Manual Test Edge 4 confirmed the
   template resolves to a real file on disk (the "delete cache"
   instruction is literal). Manual Test explicit vote: pin
   production layout.
4. **Detection via peek-after-derive**, not pre-check: the helper
   reads `outcome.formula` / `outcome.top_n` from the returned
   `LocalizationFinding` and compares against the requested values.
   A fresh derive returns kwargs-written values; a cache hit returns
   cached values. `derive.py` is untouched (engine stays unaware of
   CLI provenance).
5. **`LocalizationUnavailable` outcomes short-circuit to `None`** —
   nothing cached → nothing to warn about. Manual Test Edge 2 + 3
   confirmed.

### `inspect` does NOT emit this warning

`inspect <run_id>` reads cached Localization data via
`get_localization_findings` and never constructs a request, so the
warning helper is unreachable from that path. `inspect` envelopes
carry `warnings: []` for the Localization section. Confirmed by
Manual Test Scenario 7. This is intentional and pinned.

### NDJSON output mode

The warning surfaces verbatim in NDJSON mode (single line; same
`to_dict()` serializer at `src/novetest/cli/output.py:55-63`). AI
consumers streaming the envelope receive the warning with no loss.
Confirmed by Manual Test Edge 5.

## Manual Test verification reference

All shapes above were verified verbatim against the merged code
(commit `5fa2381`) by:
- Main Branch verification doc:
  `agent-comms/verifications/2026-05-30-localization-cache-mismatch-warnings.md`
  (cited verbatim source lines `cli/app.py:855-927`, `:906-910`,
  `:914-926`)
- Manual Test findings doc:
  `agent-comms/findings/manual-test-team-2026-05-30-localization-cache-mismatch-warnings.md`
  — 8 scenarios + 6 edge cases, all PASS verdict, zero functional
  regressions

Both Manual Test votes (production `cache_path` layout; single
warning per invocation) are pinned above (§"Cache-vs-request
mismatch warning" items 1 + 3).

## Forward-compatible extension rules

Additive (no v2 required):
- New `EnvelopeWarning` `code` values for other Localization cache
  conditions (e.g. stale-cache, schema-version-mismatch).
- Adding mode-specific fields under `localization_outcome` when
  `kind == "fact-set"` that the v2 finding-shape decision already
  permits (e.g. when modes #2 ships, `mode` field surfaces in the
  envelope per `2026-05-28-localization-finding-shape-v2.md`).
- New `REASON_*` constants in the unavailable kind, provided their
  semantics do not overlap `REASON_NO_RUN_EVIDENCE` or the
  envelope-level `run-not-found` boundary above.

Requires v2 supersede:
- Moving `warnings` from envelope-level into `localization_outcome`
  (reverses §"Top-level envelope" pinning).
- Changing the `cache_path` template (couples to `persistence.py`
  change).
- Allowing multiple warnings per invocation for the same mismatch.
- Removing the `*_explicit` booleans from the warning's `details`.

## Effective date

2026-05-30.

## Supersedes

Nothing on the `localization_outcome` envelope shell. Layers on top
of:
- `decisions/2026-05-28-localization-finding-shape.md` (v1
  `LocalizationFinding` shape)
- `decisions/2026-05-28-localization-finding-shape-v2.md` (v2
  top-`n` key rename)

Those decisions remain in force; this freeze adds the envelope
shell + warning + boundary semantics around them.
