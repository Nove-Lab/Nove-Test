---
from: novetest-run-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-06
slug: envelope-warnings-projection
related:
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md
  - agent-comms/findings/manual-test-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - src/novetest/run/adapters/dotnet_adapter.py
  - src/novetest/run/adapters/junit_adapter.py
  - src/novetest/run/types.py
  - src/novetest/run/normalizer.py
  - src/novetest/orchestration/workflows/run.py
  - src/novetest/cli/app.py
  - src/novetest/cli/output.py
---

# Question — formal envelope-level `warnings` projection for adapter-emitted warnings

## TL;DR

The `.NET adapter hotfix #1` brief §2.2 (F1b) requires the
`coverage-requested-but-coverlet-absent` warning to "reach the
envelope's top-level `warnings` field, not just the internal payload."

Run team analyzed the existing plumbing and found that **no
adapter-emitted warning reaches the envelope's top-level `warnings`
field today** — across ALL six native engine adapters. The
infrastructure for envelope `warnings` exists at the CLI boundary
(`cli/output.py::EnvelopeWarning` + `Envelope.warnings`), but only
the `localization` handler currently uses it (for the
`localization-cache-rederived` audit warning, derived inside
orchestration). The `run` handler at
`src/novetest/cli/app.py:281-284` does NOT pass `warnings` to the
envelope.

Adapter-emitted warnings (`engine-misconfigured`,
`xunit-v3-coverage-deferred`, `ambiguous-build-tool`,
`missing-jacoco`, etc.) live in `NativeResult.payload["warnings"]`
and die at the normalizer (`src/novetest/run/normalizer.py:80-114`
lifts `metadata` + `artifact_paths` but NOT `payload`).

Closing the brief's F1b *strictly* (envelope top-level `warnings`)
requires Run-team + Orchestration-team coordinated changes. Run
team CAN do the adapter-side and types-side portions; the
RunOutcome / cli/app.py portions are Orchestration territory per the
team-structure decision of 2026-05-14.

**This hotfix slice ships a Run-team-scope-only partial:**
adapter writes `coverage_unavailable_kind` +
`coverage_unavailable_message` to `NativeResult.metadata`, which
the normalizer already lifts onto `RunRecord.metadata`. The user
sees the warning at `data.memory_entry.run_record.metadata.{kind,message}`
in the envelope — same wire surface as the existing
`coverlet_version` / `xunit_version` / `dotnet_sdk_version` keys.

The question asks PM to decide between three options for the
**formal** envelope `warnings` projection of adapter warnings.

## Empirical inspection of the current plumbing

### What exists today

**`src/novetest/cli/output.py:36-63`** — `EnvelopeWarning` dataclass
+ `Envelope.warnings: tuple[EnvelopeWarning, ...] = ()` field.
Fully wired, JSON-serializable via `Envelope.to_dict`. Top-level
envelope JSON field `warnings: []` always present.

**`src/novetest/cli/app.py:759-877`** — `localization_run` /
`localization_latest` handlers pass `warnings=(warning,)` to
`Envelope(...)`. The warning is built by
`_build_localization_cache_rederived_warning` inside the
orchestration layer (CLI handler module).

### What does NOT exist today

**`src/novetest/run/types.py::NativeResult`** — no `warnings` field.
Existing field: `payload: dict[str, object]`. Adapters write to
`payload["warnings"]` by convention.

**`src/novetest/models/run_record.py::RunRecord`** — no `warnings`
field. Existing fields include `metadata: dict[str, Any]`.

**`src/novetest/orchestration/workflows/run.py::RunOutcome`** — no
`warnings` field. Existing fields: `memory_entry`, `artifact_dir`,
`coverage_outcome`.

**`src/novetest/cli/app.py::run_cmd` (lines 281-284)** —
constructs `Envelope(command="run", ok=ok, data=data)` with NO
`warnings=` kwarg.

**`src/novetest/run/normalizer.py:80-114`** —
`normalize_native_result` lifts only `native_result.metadata` and
`native_result.artifact_paths` onto the `RunRecord`. The
`payload["warnings"]` content is silently dropped.

### What does work today (metadata channel)

`NativeResult.metadata: dict[str, str]` flows through the normalizer
(`metadata: dict[str, Any] = {"native_exit_code": ...}; metadata.update(native_result.metadata)`)
onto `RunRecord.metadata`, which then flows through `MemoryEntry.to_dict()`
to the envelope at `data.memory_entry.run_record.metadata`. The
reserved-key guard in the normalizer only blocks `native_exit_code`;
all other keys pass through. F1b uses this channel today as the
v1 surface.

## Why we did not close F1b fully in this slice

The Run team charter ([`.claude/agents/novetest-run-team.md`])
specifies "Forbidden files / directories" including:
- `src/novetest/cli/**`
- `src/novetest/models/**` (Memory team — propose model changes via questions/)
- `src/novetest/orchestration/**` (Orchestration team)

Closing F1b strictly requires:
1. Adding `warnings: list[EnvelopeWarning-shaped dict]` to one of
   `NativeResult` / `RunRecord` (or both) — boundary discussion.
2. Lifting `payload["warnings"]` (or a new `NativeResult.warnings`)
   onto whichever container chosen above — normalizer change
   (Run-team-owned).
3. Adding `warnings` field to `RunOutcome` (Orchestration territory).
4. Modifying `run_cmd` to pass `warnings=outcome.warnings` to the
   `Envelope` constructor (Orchestration territory).
5. Probably also for `test_cmd` (envelope built via
   `build_test_envelope` — also orchestration).

Run team owns #2 only (and parts of #1 depending on where the
field lives). Run team filed this question rather than touch
orchestration files.

## Options for PM disposition

### Option A — Adapter-side metadata only (status quo of THIS hotfix)

**Scope**: Run team owns; orchestration unchanged.

- Adapter writes `metadata["coverage_unavailable_kind"]` +
  `["..._message"]`.
- User reads the warning at
  `data.memory_entry.run_record.metadata.coverage_unavailable_kind`.
- All other adapter warnings stay in `payload["warnings"]` (die
  at normalizer).

**Pros**: zero cross-team coordination; ships in this hotfix.

**Cons**: doesn't match the brief's literal "envelope top-level
`warnings` field" requirement. Not consistent with the
`localization-cache-rederived` precedent (which DOES surface at
envelope top-level). Each adapter warning that needs envelope
visibility requires a bespoke metadata-key surface, which doesn't
scale to the existing five-adapter warning corpus.

### Option B — Adapter-warnings-lift through metadata via a single reserved key

**Scope**: Run team owns; orchestration unchanged.

- Add a normalizer convention: lift
  `NativeResult.payload["warnings"]` to
  `RunRecord.metadata["_adapter_warnings"]` (or similar key) as a
  JSON-serialized string.
- All adapter warnings become user-visible without per-warning
  bespoke keys.
- User parses
  `json.loads(data.memory_entry.run_record.metadata._adapter_warnings)`
  to read them.

**Pros**: scales to all adapters; Run-team-only change; preserves
the structured `{kind, message}` shape.

**Cons**: indirection through a JSON-serialized string is awkward;
breaks the "metadata is `dict[str, str]`" typed contract; AI
consumers need a two-stage parse.

### Option C — Cross-team plumbing for envelope top-level `warnings` (full F1b)

**Scope**: Run team + Orchestration team (Run-team charter
forbidden territories).

- Add `warnings: tuple[EnvelopeWarning-shaped dict, ...]` to
  `NativeResult` (Run team).
- Adapter writes both `payload["warnings"]` (existing, forensic)
  AND `NativeResult.warnings` (new, envelope-bound).
- Normalizer lifts `NativeResult.warnings` onto a new
  `RunRecord.adapter_warnings` field — or onto a new
  `RunOutcome.adapter_warnings` field (skipping persistence).
- Orchestration: `RunOutcome.warnings` field
  (orchestration-team-owned); `run_cmd` passes
  `warnings=outcome.warnings` to `Envelope(...)`.

**Pros**: matches the brief's strict reading; uniform with the
`localization-cache-rederived` precedent; scales to all adapters;
structured envelope shape AI consumers can pin directly.

**Cons**: cross-team work; PM dispatches Orchestration team in a
follow-up slice; this hotfix ships partial F1b and the formal
envelope projection lands separately.

### Option D — Defer F1b to a separate slice; document gap

**Scope**: PM amends the brief; this hotfix ships F1a + F1c
only.

- Adapter-side restore fix (F1a) closes the actual silent-no-op
  defect. F1b is defense-in-depth; the silent-no-op path is now
  impossible on the happy path post-F1a.
- The metadata surfacing in this hotfix can be reverted; the user
  sees the warning only via `payload["warnings"]` in the (TODO:
  internal) artifact log, not in the envelope.
- A separate cross-team slice (option C) lands the formal envelope
  projection.

**Pros**: smallest possible hotfix scope; brief explicitly notes
F1b as "defense in depth"; F1a alone closes the user-visible D1.

**Cons**: leaves the brief's F1b unmet for any rare future case
where restore succeeds but Coverlet truly absent.

## Recommended disposition

Run team's recommendation: **Option A for this hotfix + Option C
in a follow-up cross-team slice**.

Rationale: the F1a fix alone closes the verdict-blocker (silent
no-op). F1b is genuinely defense-in-depth for the rare
restore-succeeds-but-Coverlet-truly-absent case. The metadata-key
surface (Option A) gives the user *some* visibility in this slice
without cross-team scope creep, and Option C's formal envelope
projection is the right long-term home — for ALL adapters'
warnings, not just .NET's.

This hotfix ships A; PM scopes a follow-up "envelope warnings
projection" slice that touches:
- `src/novetest/run/types.py` (NativeResult.warnings) — Run team
- `src/novetest/run/normalizer.py` (lift + write to RunOutcome
  or similar) — Run team
- `src/novetest/orchestration/workflows/run.py`
  (RunOutcome.warnings) — Orchestration team
- `src/novetest/cli/app.py::run_cmd` + `test_cmd`
  (pass-through to Envelope) — Orchestration team

The follow-up slice can also retroactively expose:
- JUnit's `missing-jacoco`, `ambiguous-build-tool`
- All adapters' `engine-misconfigured`
- xUnit v3 deferral (`xunit-v3-coverage-deferred`)
- Cargo's various warnings
- jest / gotest / pytest analogues

— a single uniform user surface for adapter warnings across all
six engines.

## Acceptance criteria for PM response

PM disposition picks A / B / C / D (or a hybrid) and either:
- Ratifies the metadata surface from THIS hotfix as the v1 surface
  (Option A), OR
- Directs Run team to revert the metadata keys and rely solely on
  F1a (Option D), OR
- Scopes the cross-team follow-up slice (Option C) and orders this
  hotfix's metadata surface to either stay (bridge) or revert
  (clean re-implementation).

This question does NOT block this hotfix slice (the metadata
surfacing is in-charter for Run team); resolution is needed for
the follow-up disposition.

## Effective date

Filed 2026-06-06. Resolution expected within cycle close (PM has
time before the next hotfix or Phase 3 entry).
