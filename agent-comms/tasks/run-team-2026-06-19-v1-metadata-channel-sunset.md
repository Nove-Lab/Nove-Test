---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-06-19
slug: v1-metadata-channel-sunset
parallel_cohort:
  - agent-comms/tasks/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
  - agent-comms/tasks/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
  - src/novetest/run/adapters/dotnet_adapter.py
  - src/novetest/run/types.py
---

# Task: Sunset the v1 `coverage_unavailable_kind/message` metadata channel

## Mission

Remove the v1 bridge metadata keys (`coverage_unavailable_kind` +
`coverage_unavailable_message`) from the dotnet adapter, now that the
Option C envelope `warnings` projection is operational. Closes Future-
cycle queue item #3 from the MVP release-ready sign-off backlog.

This is a **bookkeeping cleanup**, not a feature change — the
`AdapterWarning(kind="coverlet-absent-or-stale", message=...)` is
already emitted into `NativeResult.warnings` alongside the metadata
write (`dotnet_adapter.py:338, 425, 471`), and the orchestration layer
already projects `NativeResult.warnings → EnvelopeWarning` for the
envelope's top-level `warnings` field. Removing the metadata bridge
leaves the envelope's `warnings` surface as the canonical contract.

## Context — what's already in place (Option C operational)

Per `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`:

- v1 (the bridge being sunset): `RunRecord.metadata["coverage_unavailable_kind"]`
  + `RunRecord.metadata["coverage_unavailable_message"]`
- v2 (Option C, already shipped 2026-06-07): adapter writes
  `AdapterWarning` into `NativeResult.warnings`; orchestration projects
  to `EnvelopeWarning`; CLI surfaces in `envelope.warnings[]`.

Concrete evidence the v2 surface is live:
- `src/novetest/run/types.py:80` defines `AdapterWarning` dataclass.
- `src/novetest/run/types.py:149` `NativeResult.warnings: tuple[AdapterWarning, ...]`.
- `src/novetest/orchestration/workflows/run.py:18-65` projects
  `NativeResult.warnings → AdapterWarning → EnvelopeWarning`.
- `src/novetest/run/adapters/dotnet_adapter.py:338, 359, 425, 471` —
  every site that writes `coverage_unavailable_*` to metadata ALSO
  writes the matching `AdapterWarning` to `result_warnings`.

The 2026-06-06 decision §"Acceptance criteria for Option C slice" #2
states: "Backward-compat: the metadata keys defined in this decision's
v1 table remain populated for one release cycle as a deprecated-but-
functional bridge. Schedule for removal: post-MVP." That removal is
THIS slice.

## Scope

### Files to modify (3)

| File | Change |
|---|---|
| `src/novetest/run/adapters/dotnet_adapter.py` | Remove the 4 lines that write `metadata["coverage_unavailable_kind"]` + `metadata["coverage_unavailable_message"]` (currently lines 627-630). Remove the 2 local variable declarations (`coverage_unavailable_kind`, `coverage_unavailable_message` at lines 382-383) and any assignments to them (line 446-447 + any others — grep first). Update the docstring at lines 70-80 + 372-380 to remove references to the v1 metadata keys; replace with a one-line pointer to `NativeResult.warnings` as the canonical surface. |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | Update the ~5 tests pinning `metadata.get("coverage_unavailable_kind")` / `metadata.get("coverage_unavailable_message")` (around lines 1600, 1738, 1744-1745, 1782-1783, 1805) to pin against `result.warnings` (the `AdapterWarning` tuple). The semantic of each test stays the same — only the assertion surface shifts. The "omits" tests (1749, 1787) become "warnings tuple is empty for the no-coverage / happy paths." |
| `agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` | Append an "Amendment 2026-06-19" section noting the v1 bridge has been sunset; reference this cycle's handoff slug; annotate the v1 reserved-key table as historical-only (do not delete — audit trail matters). |

### Files NOT to modify

- `src/novetest/run/normalizer.py` — already lifts `NativeResult.warnings`; no change.
- `src/novetest/run/types.py` — `AdapterWarning` shape stays; do not remove.
- `src/novetest/orchestration/workflows/run.py` — the `AdapterWarning → EnvelopeWarning` projection is the canonical surface; do not touch.
- Other adapters (`pytest_adapter.py`, `jest_adapter.py`, `go_adapter.py`, `cargo_adapter.py`, `junit_adapter.py`) — none of them ever wrote `coverage_unavailable_kind/message`. No change.
- Integration tests in `tests/integration/run/` — they exercise the envelope-level `warnings` surface, which is unchanged.

## Definition of Done

1. `grep -rn "coverage_unavailable_kind\|coverage_unavailable_message" src/ tests/` returns **zero** matches. (The decision-file amendment retains historical references inside `agent-comms/decisions/`, which the grep above does not scan.)
2. `uv run mypy --strict src/novetest` → `Success: no issues found in <N> source files` (baseline unchanged at 109 source files as of 2026-06-18).
3. `uv run pytest -q tests/unit tests/integration` → equal-or-greater pass count vs pre-slice baseline (1281 passed / 23-26 skipped / 1 pre-existing chronic dotnet failure on dev hosts without dotnet SDK installed; chronic 1-failure stays unchanged).
4. Empirical check (best effort): invoke `novetest test --output json` on a `tests/fixtures/projects/dotnet-*` fixture where Coverlet is absent. The envelope's top-level `warnings[]` MUST contain a `{"code": "coverlet-absent-or-stale", "message": "..."}` entry; the envelope's `data.memory_entry.run_record.metadata` MUST NOT contain `coverage_unavailable_kind` or `coverage_unavailable_message` keys. If no fixture exists for the empty-Coverlet path, document the surface in the handoff and rely on the test-suite assertion adjustment in #3.
5. Handoff lists the decision-file amendment shape so PM can verify before cycle-close.

## Verification posture

- **Host**: equipped (per `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md` §1 SHOULD tier — Run team adapter slice, but **§2.5 pre-handoff gate DOES fire** because this touches `src/novetest/run/adapters/dotnet_adapter.py` and `tests/unit/run/adapters/test_dotnet_adapter.py`). Run team's pre-handoff `pytest tests/unit/run/adapters/test_dotnet_adapter.py -v` MUST pass on the equipped host (dotnet SDK + Coverlet 6.0.2 installed) for the slice to be eligible for handoff.
- **CI matrix verdict criterion (per §4 amendment 2026-06-19)**: the surface is **path/OS-INSENSITIVE** (pure adapter logic, no path-handling, no OS-gating, no Python-version branches). The §4 MUST does NOT fire. SHOULD tier applies — Linux green sufficient, but if the equipped host runs Linux only, citing the post-merge `ci.yml` matrix run is recommended for symmetry with the parallel cohort.
- **Test runs**: pre-slice baseline = 1281 passed; post-slice expectation = same or +deltas for the new `warnings` tuple assertions (no test removed; assertions migrate).

## Out of scope

- DO NOT modify the `NativeResult.warnings` shape or the `AdapterWarning` dataclass. Both are the canonical post-sunset surface.
- DO NOT modify the orchestration projection at `workflows/run.py`. The `EnvelopeWarning` shape is the contract.
- DO NOT touch `src/novetest/run/normalizer.py`. The `metadata` lift behavior is fine — only the dotnet adapter stops writing the bridge keys.
- DO NOT modify other adapters (`pytest`, `jest`, `go`, `cargo`, `junit`). Only dotnet ever used the v1 bridge.
- DO NOT regenerate any envelope snapshot files. If a snapshot pin fails because it included the v1 metadata keys verbatim, migrate the test to assert against `warnings[]` directly rather than regenerating — preserves the byte-identity guard discipline from the 2026-06-18 text-renderer cycle's load-bearing learning #2.

## Failure modes (anticipated)

1. **Snapshot test breakage**: if any existing snapshot includes the full `run_record.metadata` dict including the v1 keys, removing the writes will cause snapshot mismatch. Discriminate: (a) if the snapshot only asserts the envelope's `warnings[]` field, no breakage; (b) if the snapshot includes the full metadata dict verbatim, migrate the test to assert against `warnings[]` directly. Snapshot regeneration is acceptable only with handoff justification.
2. **Test fixture absence**: DoD #4 requires a no-Coverlet dotnet fixture. If none exists (the existing dotnet fixtures all have Coverlet), DoD #4 collapses to the test-suite assertion migration only. Note this in the handoff.
3. **Adapter `result_warnings` ordering**: the 4 sites that emit `AdapterWarning` write in a specific order. Do not reorder; preserve current emission sequence so envelope `warnings[]` ordering is stable.

## Procedural posture

- **Branch**: `run/v1-metadata-channel-sunset` off `main` HEAD (currently `a2679a0`).
- **Worktree**: per Run team standard worktree root.
- **Handoff target**: Main Branch (standard worktree → FF-merge flow). The `gh` auth read-only situation from 2026-06-18 may still apply — branch push handed off to CEO if 403.
- **WORKLOG entry required**: yes (this touches `src/` + `tests/`).
- **Handoff file**: `agent-comms/handoffs/run-team-2026-06-19-v1-metadata-channel-sunset.md` with "DoD bullets believed closed" list per CLAUDE.md convention.

## Parallel cohort awareness

This slice runs in **Wave 1 parallel** with two other team cycles + 1 PM-internal task. File-footprint matrix:

| Slice | Owned area | Conflict with this slice? |
|---|---|---|
| Release: NOTICES + perf bench + wheel-NOTICES probe | `NOTICES.md`, `.github/workflows/release-test.yml` | None ✓ |
| Coverage: `workspace_relpath` utility promotion | `src/novetest/utils/`, `src/novetest/coverage/`, `src/novetest/localization/` | None ✓ |
| PM (no dispatch): CI verdict meta-decision amendment | `agent-comms/decisions/` (already merged in cycle dispatch commit) | None ✓ |

Standard FF-merge order is alphabetical-by-team (Coverage → Release → Run) per 2026-06-09 Windows-CI fix triple precedent.

## Estimated effort

~1 cycle. ~50-100 LOC src diff (mostly deletions), ~80-150 LOC test diff (assertion migrations). Single-author; no cross-team coordination needed.
