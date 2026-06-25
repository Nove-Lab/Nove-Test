---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-06-25
slug: memory-wipe-primitive-and-module-path-contract
related:
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - src/novetest/memory/project_store.py
  - src/novetest/memory/__init__.py
---

# History: Memory `wipe_project_store` primitive landed; Orchestration verb half kicked back on module-path contract

## Summary

First slice of the `novetest reset` cycle — Memory's `wipe_project_store` primitive — merged at `cfffa70` (2026-06-25) with full verification + Manual Test verdict PASSED (1333 tests / mypy clean / CI 10/10). Companion Orchestration `novetest reset --confirm` verb slice was kicked back the same day for importing 3 new symbols from the package path (`from novetest.memory import ...`) instead of the module path (`from novetest.memory.project_store import ...`) that the task brief AND Memory's handoff both explicitly pinned. PM directed the 4-line fix via brief amendment; CEO re-dispatches Orchestration on a follow-up cycle.

The reset cycle is **half-complete**. Memory primitive is production-ready; CLI verb is pending Orchestration's redo.

## Load-bearing lessons for future agents

### 1. Module-path vs package-path public surface is a deliberate API-design choice

When an engine team adds new public symbols, two options exist:
- **Module-path-only** (`from novetest.<engine>.<module> import ...`): symbols are public but callers must address the module explicitly.
- **Package-path** (`from novetest.<engine> import ...`): symbols are re-exported through `__init__.py::__all__` and become first-class engine surface.

Memory chose module-path-only for `wipe_project_store`, `WipeReport`, `ProjectStoreNotFoundError`. The decision was correct because (a) the symbols are new and untested in production, may need iteration before promoting; (b) the single consumer (Orchestration's reset workflow) addresses the module path with no friction; (c) the engine's "official" public surface stays narrow and stable.

**Pattern for future teams**: when adding new public symbols, default to module-path. Only re-export at package level after consumer demand justifies it (typically 2+ consumers, or external API users).

### 2. Decoupled slicing reduces merge-order coupling

Memory's primitive shipped **independently of its consumer** because it is purely additive — no existing call site, no behavior change. Full test suite went from 1327 → 1333 passes (exactly +6 for the new tests); mypy clean; CI 10/10.

This pattern works when (a) the primitive has no existing caller; (b) tests are self-contained at unit level; (c) the primitive's interface is pinned in a decision doc BEFORE the consumer starts.

**Pattern for future cycles**: when a primitive can ship without its consumer, do so. It unblocks the producing team's queue and reduces merge-order coupling. The consumer cycle then composes against a stable foundation.

### 3. Pre-merge gates catch contract violations before main pollution

Main Branch's pre-merge `mypy --strict src/novetest` gate caught the import-path mismatch on the **combined tree** (Memory's `cfffa70` + Orchestration's worktree). 4 `[attr-defined]` errors surfaced exactly the Orchestration handoff's own pre-merge prediction (which had assumed the package-path import would resolve once Memory landed — but the resolution required module path, not just primitive presence). Without the combined-tree gate, the broken Orchestration slice would have merged and required revert + re-merge.

**Pattern**: a green-on-worktree slice is not the same as green-on-combined-tree. The combined-tree mypy run is the binding gate. Keep it strict.

### 4. `agent-comms/questions/` is the kick-back routing channel — never team-to-team direct

Main Branch did not message Orchestration "fix your imports". Instead Main Branch filed a question to PM (`agent-comms/questions/main-branch-team-2026-06-25-orchestration-reset-import-path.md`) explaining the contract mismatch + the proposed 4-line fix. PM then has the visibility to (a) direct the trivial fix, (b) adjust the brief / decision if the contract was ambiguous, or (c) escalate to CEO if the mismatch is structural.

**Pattern**: when a team-to-team handoff fails, route via PM. Don't fix-and-forget at the team layer — let PM see the routing problem so the brief / decision can be tightened if needed.

## What's still pending after this history entry

- **Orchestration `novetest reset --confirm` verb redo** — worktree preserved at `/home/yjshin/dev/aispace/novetest-reset-verb`, branch `orchestration/reset-verb`, currently at `d43d27a` already rebased on top of `cfffa70`. 4-line import fix per the amendment now appended to `agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md`. CEO re-dispatches.
- **After Orchestration verb lands** — new handoff → Main Branch verify + merge → Manual Test → second-half cycle close (a fresh history entry references this one).
- **After full cycle close** — PM updates user-doc + Docs handoff to replace `rm -rf .novetest && novetest init` with `novetest reset --confirm` per decision doc §"Updates".

## Standing recommendation carried forward

- **Dev-host Node 12 pollution**: 3 jest integration tests fail locally on the dev box with `node --version` v12.22.9 (jest-cli 29.7.0 requires Node ≥ 14). CI Ubuntu (Node 20+) is the binding gate; this is a host-hygiene matter, not a product issue. Carried from 2026-06-22 and 2026-06-23 findings. Resolution options: upgrade Node, or add a pytest marker that auto-deselects on old Node. Not blocking; logged for the next dev-env audit.
