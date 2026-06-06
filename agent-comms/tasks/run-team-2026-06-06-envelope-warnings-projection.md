---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-06
slug: envelope-warnings-projection
status: pending
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
  - src/novetest/run/types.py
  - src/novetest/run/normalizer.py
  - src/novetest/run/adapters/dotnet_adapter.py
  - src/novetest/run/adapters/junit_adapter.py
  - src/novetest/run/adapters/cargo_adapter.py
  - src/novetest/run/adapters/pytest_adapter.py
  - src/novetest/run/adapters/jest_adapter.py
  - src/novetest/run/adapters/gotest_adapter.py
  - src/novetest/orchestration/workflows/run.py
  - src/novetest/cli/app.py
  - src/novetest/cli/output.py
---

# Cross-team slice — envelope top-level `warnings` projection for all 6 adapter engines (Option C of 2026-06-06 decision)

## TL;DR

Uniform projection of every adapter-emitted warning to the JSON
envelope's top-level `warnings` field. Today the `Envelope.warnings`
field exists and is JSON-serializable at the CLI boundary, but only the
`localization` handler ever populates it. Adapter-emitted warnings
(`engine-misconfigured`, `xunit-v3-coverage-deferred`,
`ambiguous-build-tool`, `missing-jacoco`, `coverage-requested-but-coverlet-absent`, etc.)
live in `NativeResult.payload["warnings"]` today and are dropped at the
normalizer.

This slice closes the gap structurally across all 6 adapters in one
go. **MVP-blocking** per `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`.

| Phase | Owner | Scope |
|---|---|---|
| **Phase 1 — adapter + types + normalizer** | Run team (charter territory) | Add `AdapterWarning` to `run/types.py`; populate `NativeResult.warnings` from each of 6 adapters; lift through normalizer |
| **Phase 2 — orchestration + CLI projection** | Run team (PM-granted one-time authorization — see §3) | Add `RunOutcome.warnings`; pass `warnings=` to `Envelope(...)` in `run_cmd` and `test_cmd` |
| **Phase 3 — integration tests** | Run team (charter territory) | Integration test per warning kind asserting envelope projection |

**Estimated scope**: ~150-250 LOC src + ~80-120 LOC tests. **4-8 hours.** Single attempt expected.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`** — the binding decision; §"Option C follow-up slice scope" is this brief's contract
4. `agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §1 + §2.5 — pre-handoff gate is binding (this slice modifies adapter integration tests)
5. `agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md` §"Load-bearing lessons" 3 — the cross-team scope creep narrative this slice closes
6. `src/novetest/cli/output.py:36-63` — `EnvelopeWarning` dataclass + `Envelope.warnings` field (the destination)
7. `src/novetest/cli/app.py:759-877` — `localization_run` / `localization_latest` handlers — the existing precedent for populating `envelope.warnings` from the orchestration layer
8. `src/novetest/cli/app.py:281-284` — `run_cmd` constructor today (NO `warnings=` kwarg) — the call site this slice modifies
9. `src/novetest/run/types.py::NativeResult` — current shape; the slice adds `warnings` field
10. `src/novetest/run/normalizer.py:80-114` — `normalize_native_result` — the lift point
11. `src/novetest/run/adapters/dotnet_adapter.py` — the canonical "warning that needs to project" case (coverage-requested-but-coverlet-absent)
12. `src/novetest/run/adapters/junit_adapter.py` — multi-warning adapter (missing-jacoco, ambiguous-build-tool, engine-misconfigured)

---

## §1. Acceptance criteria (binding from the decision file)

Per `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
§"Acceptance criteria for Option C slice":

| # | Criterion | Evidence form |
|---|---|---|
| 1 | `envelope.warnings` is non-empty when any adapter writes a warning, regardless of engine | Integration tests per engine; envelope capture in handoff |
| 2 | Backward-compat: the metadata keys defined in v1 table (`coverage_unavailable_kind`, `coverage_unavailable_message`, future `{topic}_kind`/`{topic}_message`) remain populated for one release cycle as a deprecated-but-functional bridge | grep on adapter sources confirming metadata writes still present alongside new `warnings` writes |
| 3 | `cli/output.py::EnvelopeWarning` is the shared envelope-warning dataclass; `run.types.AdapterWarning` (if introduced) MUST be structurally compatible | Both dataclasses converge at the orchestration boundary |
| 4 | Integration tests pin each of the warnings produces a non-empty `envelope.warnings` on the canonical fixture that surfaces that warning | Test list per §1.2 below |

### §1.1 — Warning catalog (mandatory projection)

The following warnings MUST surface at `envelope.warnings[]` post-slice
(per the decision file's catalog):

| Adapter | Warning kind | Canonical trigger fixture |
|---|---|---|
| .NET (dotnet) | `coverage-requested-but-coverlet-absent` | `tests/fixtures/projects/dotnet-test-basic/` (no coverlet.collector in csproj) + `--coverage` flag |
| .NET (dotnet) | `xunit-v3-coverage-deferred` | xUnit v3 fixture + `--coverage` (deferral path) |
| JUnit | `missing-jacoco` | Maven-Surefire fixture without jacoco-maven-plugin + `--coverage` |
| JUnit | `ambiguous-build-tool` | Fixture with both pom.xml AND build.gradle.kts |
| JUnit | `engine-misconfigured` | Existing JUnit fixture with intentional misconfig |
| cargo | (existing kinds — Run team enumerates) | Existing cargo fixtures |
| pytest, jest, gotest | (none today, but plumbing must support future) | n/a — plumbing test only |

### §1.2 — Integration test matrix

ONE integration test per (adapter, warning kind) row above. Each test:
1. Sets up fixture (existing or new minimal one if missing)
2. Invokes `novetest run` (or `novetest run --coverage`) via CLI subprocess
3. Parses envelope JSON
4. Asserts `envelope.warnings` contains a dict with `kind == "<expected-kind>"` and a non-empty `message`
5. Asserts the v1 metadata-channel keys (where applicable) are STILL present (backward-compat criterion #2)

---

## §2. Design (Run team's call to refine)

PM proposes the following design. Run team may refine if they find a
cleaner shape during implementation; report deviations in the handoff.

### §2.1 — `AdapterWarning` shared dataclass

**Option α (recommended)**: re-export `EnvelopeWarning` from `cli/output.py`
into `run/types.py` so adapters and CLI share the exact dataclass. No
new class introduced; `run.types.AdapterWarning = EnvelopeWarning`.
Conversion is identity.

**Option β**: introduce `AdapterWarning` separately in `run/types.py`
with same fields (`kind: str`, `message: str`); add a `.to_envelope()`
method or normalizer-level conversion. More flexible if envelope and
adapter shapes diverge later, but adds boilerplate.

Run team picks α or β; PM accepts either if structurally compatible
(criterion #3).

### §2.2 — `NativeResult.warnings`

Add to `src/novetest/run/types.py`:

```python
@dataclass
class NativeResult:
    # ... existing fields ...
    warnings: tuple[AdapterWarning, ...] = ()
```

Default `()` so all existing call sites are backward-compat without
edits.

### §2.3 — Per-adapter migration

Each of 6 adapters: replace the existing `payload["warnings"].append({...})`
write with BOTH:

```python
# Existing forensic write (RETAINED per criterion #2)
payload.setdefault("warnings", []).append({"kind": "...", "message": "..."})
# NEW envelope-bound write
result_warnings = list(result.warnings)
result_warnings.append(AdapterWarning(kind="...", message="..."))
result = result._replace(warnings=tuple(result_warnings))   # or whatever immutable update pattern
```

(Adapters may emit zero, one, or many warnings per run. The slice MUST
preserve the existing emit conditions verbatim — do not change WHEN
warnings fire, only the additional surface they reach.)

### §2.4 — Normalizer lift

In `src/novetest/run/normalizer.py::normalize_native_result`:

Where the existing code lifts `native_result.metadata` and
`native_result.artifact_paths`, add a lift of
`native_result.warnings` into a new field on the normalized result.

Run team picks the destination:
- Onto `RunRecord.warnings` (persistent, queryable later)
- Onto a normalizer-return-tuple second element (transient, envelope-only)

PM prefers the **transient (envelope-only)** path — warnings are
notice-grade signals, not facts to persist. But Run team has the
context to decide cleanly.

### §2.5 — Orchestration boundary

**PM-granted cross-team file authorization for this slice ONLY**: Run
team is authorized to touch the following Orchestration files for the
specific changes listed, and ONLY those changes:

#### `src/novetest/orchestration/workflows/run.py`

Add ONE field to `RunOutcome`:

```python
@dataclass
class RunOutcome:
    # ... existing fields ...
    warnings: tuple[EnvelopeWarning, ...] = ()
```

Populate from the normalizer's lifted warnings. Do not modify any
other RunOutcome field, helper, or workflow logic.

#### `src/novetest/cli/app.py`

Two surgical changes only:

1. `run_cmd` (around line 281-284): pass `warnings=outcome.warnings` to
   `Envelope(...)`.
2. `test_cmd` (build_test_envelope or wherever the envelope is built
   for the integrated workflow): pass `warnings=` from the integrated
   outcome's warnings tuple.

Do NOT modify any other CLI handler, error path, or envelope construction.

#### Scope guard

If during implementation Run team discovers that ANY other orchestration
or CLI file needs editing to make this work (e.g. the integrated
workflow merges warnings from multiple sub-engines), STOP and file a
`questions/` entry to PM. Do not silently expand scope.

### §2.6 — Test placement

- Unit tests for adapter changes: `tests/unit/run/adapters/test_<engine>_adapter.py` (Run team territory)
- Unit tests for normalizer: `tests/unit/run/test_normalizer.py` (Run team territory)
- Integration tests for envelope projection: `tests/integration/run/test_<engine>_warnings.py` (NEW; Run team territory)
- IF orchestration-side unit tests are warranted: `tests/unit/orchestration/test_run_workflow.py` (under PM's cross-team authorization above)

---

## §3. Cross-team authorization (one-time, this slice only)

PM grants Run team explicit authorization to touch the following files
for this slice, scoped to the changes named in §2.5:

- `src/novetest/orchestration/workflows/run.py` — add `RunOutcome.warnings` field + populator wiring
- `src/novetest/cli/app.py` — pass `warnings=` to `Envelope(...)` in `run_cmd` + `test_cmd`

This authorization does NOT extend to:
- Other orchestration workflows (init, test, memory, inspect, compare, status)
- Other CLI handlers (init_cmd, test_cmd workflow internals, memory_cmd, etc.)
- Any model changes (`src/novetest/models/**` — Memory team territory)

Run team's pre-handoff exercise verifies the scope guard held: handoff
includes a `git diff --stat` summary confirming only the authorized files
in those two paths changed.

If Run team needs to touch `src/novetest/cli/output.py` (e.g. to
re-export `EnvelopeWarning` per Option α in §2.1), PM grants that too —
re-export is one-line and structural.

---

## §4. §2.5 binding (equip-and-exercise pre-handoff gate)

This slice modifies `src/novetest/run/adapters/*_adapter.py` (all 6)
AND `tests/integration/run/test_<engine>_warnings.py` (new) →
**§2.5 IS BINDING.**

Run team's pre-handoff gate:
1. **Equipped host** — host MUST have at least: `python` (always),
   `node`+`npm` (jest), `go` (gotest), `dotnet` (dotnet), `java`+`mvn`
   (junit), `cargo` (cargo). Skip-gate elimination across all 6
   adapters is the criterion.
2. **Full suite pass** — `uv run pytest -q tests/unit tests/integration`
   produces 0 fails. Skip count is documented (some engines may legitimately
   skip if equip is partial; document which).
3. **Per-warning integration test pass** — the new
   `test_<engine>_warnings.py` files MUST all pass on the equipped host
   with the engine's tooling resolvable. No skipping the canonical-
   trigger test for the warning kind being tested.
4. **CLI smoke per adapter** — for each adapter with a non-trivial
   warning being projected (dotnet, junit, cargo at minimum), Run team
   runs the CLI smoke against the trigger fixture and captures the
   envelope; pastes the `envelope.warnings[]` content in the handoff.

If Run team's host cannot equip every engine (legitimate per-engine
skip), document which ones in the handoff and PM/Manual Test rerun on
the equipped fallback host before merge.

---

## §5. DoD bullets (PM ticks at cycle close)

| # | Bullet | Evidence form expected |
|---|---|---|
| 1 | `AdapterWarning` dataclass landed (Option α or β); structurally compatible with `cli.output.EnvelopeWarning` per criterion #3 | `git diff src/novetest/run/types.py` |
| 2 | `NativeResult.warnings: tuple[AdapterWarning, ...]` field added, default `()` | grep on `run/types.py` |
| 3 | All 6 adapters write to `result.warnings` for every warning they emit; existing `payload["warnings"]` forensic writes retained per criterion #2 | grep + per-adapter unit test |
| 4 | `normalizer.py` lifts `NativeResult.warnings` into the chosen destination | `git diff src/novetest/run/normalizer.py` |
| 5 | `RunOutcome.warnings` field added; populated from normalized run | `git diff src/novetest/orchestration/workflows/run.py` |
| 6 | `run_cmd` + `test_cmd` pass `warnings=outcome.warnings` to `Envelope(...)` | `git diff src/novetest/cli/app.py` |
| 7 | Cross-team scope guard held: only the explicitly-authorized files in `orchestration/` and `cli/` changed | `git diff --stat` in handoff |
| 8 | Per-warning integration tests added (one per row of §1.1); all PASS on equipped host | `pytest -v tests/integration/run/test_*_warnings.py` |
| 9 | Backward-compat: v1 metadata keys (`coverage_unavailable_kind` etc.) STILL populated alongside new `envelope.warnings` projection per criterion #2 | per-test assertion + grep |
| 10 | `mypy --strict` clean | mypy output in handoff |
| 11 | §2.5 pre-handoff gate per §4 above; 0 fails on equipped host; per-engine smoke envelope captures pasted in handoff | handoff §"Pre-handoff gate environment" |

---

## §6. Out of scope (NOT in this slice)

- Removing the v1 metadata keys (`coverage_unavailable_kind` etc.) —
  decision file says they stay as deprecated bridge for one release
  cycle; removal is post-MVP
- Adding NEW warning kinds to any adapter beyond §1.1 catalog
- Changing WHEN warnings fire (only the additional surface they reach
  matters here)
- Persisting warnings to the RunRecord JSON (transient/envelope-only is
  PM's preference per §2.4)
- Memory engine RunRecord schema changes (Memory team territory; NOT
  authorized for this slice)
- localization-cache-rederived warning's plumbing (already works; do
  not refactor)
- xUnit v3 actual MTP coverage support (out of MVP per `decisions/2026-06-03-coverlet-pertestcoverage-key.md` §6)

---

## §7. Decisions referenced

| Decision | Honored as |
|---|---|
| `2026-06-06-adapter-warning-surface-v1-metadata-channel.md` | This slice IS the Option C follow-up. v1 metadata keys retained as bridge. |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md` §1 + §2.5 | Binding pre-handoff gate per §4 |
| `2026-06-03-coverlet-pertestcoverage-key.md` | xUnit v3 deferral warning is one of the catalog entries |
| `2026-05-25-supported-engine-matrix.md` (Maven amended 3.9 → 3.8) | All engine floors hold; this slice doesn't change matrix |
| `2026-05-30-native-result-metadata-slot.md` | `NativeResult.metadata` plumbing convention is the reference pattern for `NativeResult.warnings` plumbing |

---

## §8. Effective date

Brief queued 2026-06-06 PM. CEO will dispatch Run team when ready.
Expected single-attempt close (no hotfixes); equip-and-exercise §2.5
catches any structural defect before handoff.

**On clean Manual Test pass**: envelope-warnings projection MVP-blocker
closes; A track of the post-Phase-2.5 backlog clears.
