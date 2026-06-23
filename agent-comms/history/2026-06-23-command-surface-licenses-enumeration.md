---
from: novetest-pm-team
to: all
type: history
created: 2026-06-23
slug: command-surface-licenses-enumeration
cycle_window: 2026-06-23 (single-day; standalone follow-up from 2026-06-22 #2b cycle)
related:
  - agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md  # parent cycle (raised Nit #1)
---

# `command_surface.py` enumeration for `licenses` — discoverability gap closed

## TL;DR

Atomic 1-commit follow-up cycle closing the discoverability gap raised
as Manual Test Nit #1 on 2026-06-22. Single `CommandSpec(name="novetest
licenses", group="orchestration", available_in_phase=0, summary=...)`
appended to `_OPERATING` tuple + protected snapshot
`test_help_envelope_no_store.ambr` regenerated. `novetest --help
--output json` now enumerates 15 verbs (was 14), with `licenses` at
index 14.

**Surgical to the byte**: `git diff main --name-only` returned exactly
2 files; snapshot diff is one hunk / 6 added lines / 0 removed / 0
modified. CI on merged HEAD `8baa3fd` shows **10/10 GREEN** (3 OS × 3
Python + perf).

Manual Test verdict: **PASSED** — 7/7 scenarios + 4/4 edge cases green.

## Cycle arc

| Event | Commit |
|---|---|
| PM dispatch | `78785cf` |
| Orchestration code slice | `e55ba52` |
| Orchestration handoff + INDEX | `bc1a8bc` |
| Main Branch verification routing | `8baa3fd` |
| Manual Test PASSED findings | _(at cycle close)_ |
| PM cycle-close (this entry + transient cleanup) | _(this commit)_ |

## What landed (2 files, 6 lines)

| File | Change |
|---|---|
| `src/novetest/orchestration/onboarding/command_surface.py` | MOD: 15th `CommandSpec` appended to end of `_OPERATING` tuple. 4 fields verbatim per data contract. No reorder of 14 existing entries. |
| `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` | MOD (`--snapshot-update`): additive only. 1 hunk, 6 added lines (the new `dict({...})` block after `novetest replay`). |

Plus comms slice (handoff + INDEX); zero `cli/`, zero
`orchestration/licenses/`, zero `NOTICES.md`, zero `pyproject.toml`,
zero `README.md` touch.

## Load-bearing learnings (2 — both reusable patterns)

### 1. The "deferred follow-up resolution" 1-commit cycle pattern works

The 2026-06-22 parent brief (#2b) explicitly deferred this snapshot
regen because it forbade `.ambr` modification. Manual Test surfaced it
as Nit #1. PM dispatched today; full loop (brief → code → handoff →
merge → verify → findings → close) ran in **<6 hours wall** with **zero
regressions and zero scope creep**.

**Template for future similar cycles**:
- Brief stays focused on the ONE deferred item (e.g., "regen one
  protected snapshot to enumerate one new entity"). 
- DoD pins surgical scope (`git diff main --name-only` must show exactly
  N files).
- Verification asserts byte-identity of NON-changed surfaces (the 14
  pre-existing entries here) — guards against accidental reorder/edit
  during snapshot regen.
- Snapshot regen via `--snapshot-update` + immediate re-run
  WITHOUT `--snapshot-update` to verify stability — pinned in the
  verification commands.

This pattern lets PM safely break a larger cycle into "the core slice
+ a follow-up that resolves the snapshot constraint" without losing
audit trail or correctness.

### 2. Dev-host Node 12 pollution is now a STANDING item (3rd recurrence)

Same 3 jest tests (`test_jest_basic`, `test_jest_coverage`,
`test_run_coverage_on_jest_workspace_produces_fact_set`) fail on this
dev host due to Node 12.22.9 vs jest-cli 29.7.0 (CommonJS loader incompat).
First documented 2026-06-22 verification §"Critical edge cases #3";
re-surfaced 2026-06-22 release verification; surfaced again here.

**Causal nexus**: zero in all 3 cases — none of those cycles touched
`jest_adapter.py` or jest fixtures. CI on Ubuntu runners with modern
Node has been GREEN every time.

**Standing item for Release / Dev-env owner** (NOT blocking any product
cycle):
- (a) Upgrade Node on the canonical dev box to ≥14
- (b) Add a pytest marker (`@pytest.mark.requires_node_ge(14)`) that
  auto-deselects jest tests when `node --version` < 14, matching the
  CI behavior on dev hosts by default

Pin both options here so the next surfacing has a documented mitigation
path. PM disposition: defer until the next Release cycle that touches
jest or CI configuration; not worth a standalone cycle.

## Future-cycle queue impact

No queue change. The Nit #1 was a 2026-06-22 spawn (not part of the
original 10-item backlog from 2026-06-09 sign-off). Closing it is pure
quality polish.

Remaining open items (unchanged from yesterday):
- **#10 `novetest workspaces test` orchestrator** — optional, gated on
  user feedback per 2026-06-09 disposition.
- **Marketing PM dispatch** for `design/website-plan/` finalization →
  ailovestesting.com site build — CEO discretion.
- **v0.1.0 draft release cleanup** — 1-line `gh api DELETE` (cosmetic).
- **`gh` CLI permanent fix** — upgrade to 2.40+ + multi-account setup
  OR GH_TOKEN env var (so dispatch + release operations work for
  nove-admin from any session).
- **Dev-host Node 12 pollution** (above standing item) — next Release
  cycle.

## Cycle transcript (commits)

- `78785cf` — PM: dispatch brief
- `e55ba52` — Orchestration: `cli: enumerate licenses verb in top-level command surface`
- `bc1a8bc` — Orchestration: handoff + INDEX
- `8baa3fd` — Main Branch: verification routing
- _(this commit)_ — PM: cycle-close (this history + transient cleanup + INDEX regen)

## Closure

The 2026-06-22 fast-follow loop is operationally complete. AI agents
inspecting `novetest --help --output json` now enumerate `licenses`
alongside the other 14 operating verbs. The product is identical in
behavior, slightly more discoverable. Total elapsed time from Nit #1
filing (2026-06-22 evening) to merge GREEN (2026-06-23 morning): under
24 hours.
