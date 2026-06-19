---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-06
slug: adapter-warning-surface-v1-metadata-channel
related:
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/questions/run-team-2026-06-06-envelope-warnings-projection.md
  - agent-comms/findings/manual-test-team-2026-06-06-phase2.5-dotnet-adapter-hotfix.md
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md
  - src/novetest/run/adapters/dotnet_adapter.py
  - src/novetest/run/adapters/junit_adapter.py
  - src/novetest/run/types.py
  - src/novetest/run/normalizer.py
  - src/novetest/orchestration/workflows/run.py
  - src/novetest/cli/app.py
  - src/novetest/cli/output.py
---

# Decision: v1 adapter-warning surface is the `RunRecord.metadata` channel (Option A); envelope top-level `warnings` projection is queued as an MVP-blocking follow-up slice (Option C)

CEO-approved on 2026-06-06 in response to the .NET adapter hotfix cycle's
open question
(`questions/run-team-2026-06-06-envelope-warnings-projection.md`). Both
Run team (the originator of the question) and Manual Test (the verdict
voter on the hotfix slice) independently recommended the same
disposition — Option A as v1 + Option C as cross-team follow-up. This
decision ratifies that recommendation.

## Context

The .NET adapter hotfix #1 brief §2.2 (F1b) required the
`coverage-requested-but-coverlet-absent` defense-in-depth warning to
reach the envelope's top-level `warnings` field, not just an internal
adapter payload. Run team's empirical inspection of the existing
plumbing found that **no adapter-emitted warning reaches the envelope
top-level today** — across all six native engine adapters
(`pytest`, `jest`, `go test`, `cargo`, `junit`, `dotnet`).

The infrastructure for envelope `warnings` exists at the CLI boundary
(`cli/output.py::EnvelopeWarning` + `Envelope.warnings`), but only the
`localization` handler currently uses it (for the
`localization-cache-rederived` audit warning, derived inside
orchestration). The `run` handler at `cli/app.py:281-284` constructs
the envelope without a `warnings=` kwarg. Adapter-emitted warnings
(`engine-misconfigured`, `xunit-v3-coverage-deferred`,
`ambiguous-build-tool`, `missing-jacoco`, etc.) live in
`NativeResult.payload["warnings"]` and are dropped at the normalizer
(`run/normalizer.py:80-114` lifts `metadata` + `artifact_paths` onto
`RunRecord` but NOT `payload`).

Closing F1b strictly requires changes across Run team's territory
(`src/novetest/run/types.py`, `src/novetest/run/normalizer.py`) AND
Orchestration team's territory (`src/novetest/orchestration/workflows/
run.py` adds `RunOutcome.warnings`; `src/novetest/cli/app.py` passes
`warnings=outcome.warnings` to `Envelope`). The hotfix slice was
Run-team-only by brief scope; touching the orchestration files would
have been a cross-team scope creep that the §2.5 binding gate could
not have validated cleanly.

Run team's question filed four options (A through D); both Run team
and Manual Test recommended **A + C**.

## Decision

**v1 (effective immediately, ratified by this decision):**
Adapter-emitted "coverage unavailable" signals — and any other
adapter warnings that need user/AI visibility before the cross-team
slice lands — surface via the `RunRecord.metadata` channel using
**reserved key names** of the shape `coverage_unavailable_kind` +
`coverage_unavailable_message` (or analogous `{topic}_kind` +
`{topic}_message` pairs for non-coverage warnings).

Reserved metadata keys for v1:

| Reserved key | Producer | Value shape | Semantic |
|---|---|---|---|
| `coverage_unavailable_kind` | adapter (any of the 6) | short slug string, e.g. `coverlet-absent-or-stale`, `jacoco-absent`, `coverage-tool-unsupported` | machine-friendly kind for AI/programmatic consumers |
| `coverage_unavailable_message` | adapter (any of the 6) | user-readable string with actionable remediation hint (e.g. the exact `<PackageReference>` snippet for .NET, the Maven `<dependency>` for JaCoCo) | human-friendly message |

Adapters MAY add additional `{topic}_kind` / `{topic}_message` pairs
for non-coverage warnings (e.g. `xunit_v3_kind: coverage-deferred` for
the xUnit v3 deferral path) as needed. The keys are flat strings under
`RunRecord.metadata: dict[str, str]`; no JSON-in-string indirection
(Option B is rejected).

**Forensic `NativeResult.payload["warnings"]` retained** — adapters
continue writing structured `{kind, message}` warnings to the internal
payload for debug/reproduction. This is the source-of-truth for the
cross-team follow-up slice to draw from when it lands.

**v2 (Option C follow-up, MVP-blocking, scoped below):**
A separate cross-team slice MUST land before MVP public release. It
adds a uniform envelope top-level `warnings` projection for ALL
adapter warnings, matching the `localization-cache-rederived`
precedent. See §"Option C follow-up slice scope" below.

## Why A is the right v1 surface (vs B / D)

**Option A (metadata channel) is empirically actionable today.** Manual
Test's verification of the hotfix slice (Cap-4 capture) confirmed that
a first-time user encountering the safety-net path sees a fully-
actionable message — the metadata names `coverlet.collector`, gives
the exact `<PackageReference Include="coverlet.collector" Version="6.0.2" />`
snippet, and points at `stderr.log` for deeper debug. The wire surface
(`data.memory_entry.run_record.metadata.coverage_unavailable_*`) is
exactly the same envelope path as the existing `coverlet_version`,
`xunit_version`, `dotnet_sdk_version` keys — AI consumers already pin
this path family for other adapter metadata.

**Option B (JSON-in-string under a reserved key) is rejected** because
it breaks the `dict[str, str]` typed contract of `RunRecord.metadata`
and forces AI consumers into a two-stage parse (`json.loads(...)`).
The indirection adds zero capability over Option A while increasing
schema surface complexity.

**Option D (revert metadata surface; rely solely on F1a)** is rejected
because the hotfix brief explicitly listed F1b as defense-in-depth for
the rare restore-succeeds-but-Coverlet-truly-absent case. Reverting the
metadata channel would leave that path silent again. The metadata
surface MUST stay as a bridge until Option C ships.

## Option C follow-up slice scope (MVP-blocking)

Filed as PM-managed backlog. PM will write the brief and dispatch when
CEO orders. Scope:

### Files touched (cross-team)

| File | Owner | Change |
|---|---|---|
| `src/novetest/run/types.py` | Run team | Add `warnings: tuple[AdapterWarning, ...] = ()` to `NativeResult`; define `AdapterWarning` dataclass mirroring `cli.output.EnvelopeWarning` shape |
| `src/novetest/run/normalizer.py` | Run team | Lift `NativeResult.warnings` into a new `NormalizedRun.warnings` (or pass-through to RunOutcome) |
| `src/novetest/run/adapters/*_adapter.py` (all 6) | Run team | Replace `payload["warnings"].append(...)` writes with `result.warnings += (AdapterWarning(...),)` |
| `src/novetest/orchestration/workflows/run.py` | Orchestration team | Add `warnings: tuple[EnvelopeWarning, ...]` to `RunOutcome`; populate from normalized run |
| `src/novetest/cli/app.py::run_cmd` + `test_cmd` | Orchestration team | Pass `warnings=outcome.warnings` to `Envelope(...)` |

### What MUST be retroactively projected to envelope top-level

Run team and Manual Test catalogued the following adapter warnings
across all 6 engines that the follow-up slice MUST expose:

| Adapter | Warning kind | Today | After Option C |
|---|---|---|---|
| .NET (dotnet) | `coverage-requested-but-coverlet-absent` | `metadata.coverage_unavailable_kind/message` | `envelope.warnings[]` (kind + message) |
| .NET (dotnet) | `xunit-v3-coverage-deferred` | `payload["warnings"]` (dropped) | `envelope.warnings[]` |
| JUnit | `missing-jacoco` | `payload["warnings"]` (dropped) | `envelope.warnings[]` |
| JUnit | `ambiguous-build-tool` | `payload["warnings"]` (dropped) | `envelope.warnings[]` |
| JUnit | `engine-misconfigured` | `payload["warnings"]` (dropped) | `envelope.warnings[]` |
| cargo | (various) | `payload["warnings"]` (dropped) | `envelope.warnings[]` |
| pytest / jest / gotest | (when adapters add warnings) | `payload["warnings"]` (dropped) | `envelope.warnings[]` |

### Acceptance criteria for Option C slice

1. `envelope.warnings` is non-empty when any adapter writes a warning,
   regardless of engine.
2. Backward-compat: the metadata keys defined in this decision's v1
   table (`coverage_unavailable_kind`, `coverage_unavailable_message`,
   future `{topic}_kind`/`{topic}_message`) remain populated for one
   release cycle as a deprecated-but-functional bridge. Schedule for
   removal: post-MVP.
3. `cli/output.py::EnvelopeWarning` is the shared envelope-warning
   dataclass; `run.types.AdapterWarning` (if introduced) MUST be
   structurally compatible.
4. Integration tests pin each of the warnings in the table above
   produces a non-empty `envelope.warnings` on the canonical fixture
   that surfaces that warning.

### Timing

The slice is **MVP-blocking** — it MUST land before public-MVP
release. PM places it after Phase 3 closure but before B1/B2 polish.
Estimated scope: ~150-250 LOC src + ~80-120 LOC tests; 4-8 hours;
one cycle, single attempt expected.

## Why this is the right disposition (vs queuing C without ratifying A)

Without this decision, the metadata surface that Manual Test verified
as "empirically actionable for the user TODAY" would be in an
unratified gray zone — Run team might revert it in a future cycle
without realizing it's the v1 contract. Ratifying A and queuing C
together turns the metadata surface into a known bridge with a known
sunset path.

## Effective dates

- **v1 (this decision)**: effective immediately upon merge of the
  cycle-close commit landing this decision file. Run team MAY use the
  reserved metadata key convention for any future adapter warning
  that needs envelope visibility before Option C ships.
- **v2 (Option C slice)**: PM dispatches the brief when CEO orders.
  MVP-blocking. Likely scheduling: after Phase 3 closure, before B1/B2
  polish.

## Affected teams / files

- **Run team**: Continues using the reserved metadata key convention
  for v1; will be the primary implementer of `NativeResult.warnings`
  and `normalizer.py` changes when Option C lands.
- **Orchestration team**: Will receive the Option C brief that touches
  `workflows/run.py` and `cli/app.py`. No action required until then.
- **Main Branch team**: Verification docs SHOULD assert against
  `data.memory_entry.run_record.metadata.{topic}_kind/message` until
  Option C ships, then switch to `envelope.warnings[]`.
- **Manual Test team**: Verifies both the metadata channel (v1) and
  the envelope.warnings projection (v2) when each cycle's verification
  doc points at them.

## Related history

- 2026-06-04: equip-and-exercise decision (the §2.5 binding gate that
  caught the F1b plumbing gap during this same hotfix cycle by
  forcing the Run-team-scope-only partial vs the cross-team-required
  full implementation distinction to surface as a question rather than
  as an unverified design assumption).
- 2026-06-05: .NET adapter original cycle (verdict-failed on D1 silent
  no-op; hotfix #1 closes D1 at the F1a layer and ships F1b as the
  v1 metadata channel surfaced here).

## Amendment 2026-06-19 — v1 metadata channel sunset

CEO-dispatched cycle `run-team-2026-06-19-v1-metadata-channel-sunset.md`
removes the v1 reserved-key metadata bridge introduced by this
decision. The one-release-cycle backward-compat window declared by
§"Acceptance criteria for Option C slice" criterion #2 closed cleanly:
Option C (envelope-warnings-projection) shipped on 2026-06-07 and has
been the operational user-visible surface for `.NET` adapter warnings
since. The metadata bridge keys were the last remaining dual-channel
artifact; removing them leaves `envelope.warnings[]` as the **single**
canonical surface for adapter-emitted warnings.

### What changed in this amendment

| Surface | Pre-2026-06-19 | Post-2026-06-19 |
|---|---|---|
| `envelope.warnings[]` | populated (Option C, since 2026-06-07) | **populated — sole canonical surface** |
| `RunRecord.metadata.coverage_unavailable_kind` | populated (v1 bridge) | **REMOVED** |
| `RunRecord.metadata.coverage_unavailable_message` | populated (v1 bridge) | **REMOVED** |
| `NativeResult.payload["warnings"]` | populated (forensic) | populated (forensic — in-process debug only; does NOT propagate to envelope) |

### Scope of the amendment

- **`.NET` (dotnet) adapter**: the only adapter that ever wrote the v1
  bridge keys. The two write sites in `src/novetest/run/adapters/dotnet_adapter.py`
  (the `coverlet-absent-or-stale` safety-net at the probe-returns-None
  branch and the deferred metadata assignment at the result-construction
  site) were removed. The `AdapterWarning` emit on `NativeResult.warnings`
  was retained unchanged — it is the canonical envelope-bound surface.
- **JUnit / pytest / jest / gotest / cargo adapters**: never used the
  v1 bridge convention. Untouched.
- **`src/novetest/run/normalizer.py`**: unchanged. The metadata-lift
  pipeline still passes through `NativeResult.metadata` keys verbatim
  to `RunRecord.metadata`; the dotnet adapter simply stops writing the
  removed keys.
- **`src/novetest/orchestration/workflows/run.py`** + **`src/novetest/cli/app.py`**:
  unchanged. The `NativeResult.warnings → AdapterWarning →
  EnvelopeWarning` projection is the canonical surface.
- **§"Reserved metadata keys for v1"** table above is annotated
  historical-only by this amendment. The convention itself
  (`{topic}_kind` / `{topic}_message` flat strings under
  `RunRecord.metadata`) remains available for any future adapter
  warning that genuinely needs the metadata channel — but new adapter
  warnings introduced post-2026-06-19 SHOULD use
  `NativeResult.warnings` exclusively and surface via the envelope
  projection. The metadata channel is no longer the v1 bridge — it is
  reserved for adapter metadata that genuinely belongs on
  `RunRecord.metadata` (engine versions, native exit codes, etc.).

### Backward-compat posture

This amendment **breaks** any external consumer that pinned
`run_record.metadata.coverage_unavailable_kind` or
`run_record.metadata.coverage_unavailable_message`. Per the original
decision's "Schedule for removal: post-MVP" disposition and the
2026-06-07 Option C operational date, the one-release-cycle window
has expired. The envelope `warnings[]` surface is the documented
migration target and has been operational for 12 days; AI consumers
and dashboards should pin envelope.warnings[].code +
envelope.warnings[].message + envelope.warnings[].details going
forward.

### Empirical sunset evidence (handoff `run-team-2026-06-19-v1-metadata-channel-sunset.md`)

- `grep -rn 'coverage_unavailable_kind\|coverage_unavailable_message' src/ tests/` returns zero matches.
- CLI smoke against the `dotnet-test-basic` fixture (Coverlet absent)
  with `novetest run --coverage`: envelope contains
  `warnings[0].code == "engine-misconfigured"` AND
  `run_record.metadata` has only `dotnet_sdk_version` /
  `xunit_version` / `native_exit_code` keys (no `coverage_unavailable_*`).
- `uv run pytest tests/unit tests/integration` → 1300 passed,
  5 skipped, 0 failed on equipped host (§2.5 binding gate, dotnet SDK +
  Coverlet 6.0.2 installed).
