---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-24
updated: 2026-06-25
slug: reset-verb
related:
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/history/2026-06-25-memory-wipe-primitive-and-module-path-contract.md
  - agent-comms/questions/main-branch-team-2026-06-25-orchestration-reset-import-path.md
---

# Handoff — `novetest reset --confirm` verb (Orchestration half) — RE-HANDOFF after kick-back fix

## Status: READY TO FF-MERGE NOW

The 2026-06-25 import-path kick-back is **resolved**. Memory's
`wipe_project_store` primitive is already on `main` (`cfffa70`); this
branch is rebased on it and merges cleanly with **no remaining gate**.

- `mypy --strict src/novetest` → **Success, 114 source files** (the 4
  prior `[attr-defined]` errors are gone).
- `pytest -q tests/unit tests/integration` → **1348 passed / 3 skipped / 0
  failed** (3 skips = pre-existing jest/Node-12 host issue, unrelated).
- The destructive round-trip e2e **de-skips and passes** against the real
  primitive.

## What the kick-back was, and the fix

Main Branch's combined-tree `mypy --strict` gate (Memory `cfffa70` + this
worktree) surfaced 4 `[attr-defined]` errors: the slice imported Memory's
3 new symbols via the **package** path `from novetest.memory import …`,
but Memory ships them **module-path-only** at
`novetest.memory.project_store` (deliberately not re-exported through
`__init__`). Per the brief amendment 2026-06-25, the fix is the import
path on `WipeReport` / `ProjectStoreNotFoundError` / `wipe_project_store`:

| File | Site | Now imports from |
|---|---|---|
| `workflows/reset.py` | `TYPE_CHECKING` (`WipeReport`) | `novetest.memory.project_store` |
| `workflows/reset.py` | deferred (`ProjectStoreNotFoundError`, `wipe_project_store`) | `novetest.memory.project_store` |
| `cli/app.py` | handler deferred (`ProjectStoreNotFoundError`) | `novetest.memory.project_store` |

`locate_project_store` stays on `novetest.memory` (it IS in Memory's
`__init__::__all__`). Unit-test monkeypatches were retargeted to the
module path and now use Memory's **real** `ProjectStoreNotFoundError`; the
e2e skip-guard was removed (primitive is permanently on `main`).

Commit `ad78ab3` carries the fix on top of the original slice
(`f144b05` code + `d43d27a` first handoff).

## Worktree / branch

- Worktree: `/home/yjshin/dev/aispace/novetest-reset-verb`
- Branch: `orchestration/reset-verb`, sitting on Memory's `cfffa70` (the base Main Branch arranged post-kick-back)
- Commits on top of `cfffa70`: `f144b05` (verb) → `d43d27a` (1st handoff) → `ad78ab3` (import fix) → branch-tip comms (this re-handoff + INDEX)
- **Merge mechanics**: `main` has advanced past `cfffa70` with **comms-only** commits (kick-back close, test-reruns decision/briefs) + one Marketing file (`design/website-plan/handoff/terminal-examples.md`). **None overlap this slice's `src/` / `tests/` / `design/workflows/` footprint — zero code conflict.** The only shared file is the auto-generated `agent-comms/INDEX.md` (regennable via `tools/regen_comms_index.py`). So this is a rebase-or-merge onto current `main`, not a pure FF; the reconciliation is mechanical and conflict-free except the regennable INDEX. The reset-verb task file on `main` already carries PM's 2026-06-25 amendment (this branch never modified it).

## Files (full slice)

| File | Change |
|---|---|
| `src/novetest/orchestration/workflows/reset.py` | NEW — `reset_project_workspace` + `ResetResult` (locate → wipe → re-init) |
| `src/novetest/cli/renderers/reset.py` | NEW — `render_reset` |
| `src/novetest/cli/app.py` | MOD — `reset_cmd` handler + `"reset"` in `_SUBCOMMAND_TOKENS` |
| `src/novetest/cli/renderers/registry.py` | MOD — `"reset": render_reset` |
| `src/novetest/cli/renderers/_format.py` | MOD — shared `format_engine_readiness()` |
| `src/novetest/cli/renderers/init.py` | MOD — uses helper (output byte-identical) |
| `src/novetest/orchestration/onboarding/command_surface.py` | MOD — onboarding `novetest reset`, `available_in_phase=7` |
| `src/novetest/orchestration/workflows/__init__.py` | MOD — exports |
| `tests/unit/orchestration/workflows/test_reset.py` | NEW — 2 (compose-order + refusal) |
| `tests/unit/cli/test_reset_cmd.py` (+ snapshot) | NEW — 5 paths + happy-envelope snapshot |
| `tests/unit/cli/renderers/test_reset.py` (+ snapshot) | NEW — full/all-zero/partial/error |
| `tests/integration/cli/test_reset_e2e.py` | NEW — round-trip (runs) + confirm-gate |
| `tests/unit/cli/test_command_surface.py` | MOD — onboarding-includes-reset + phase invariant 6→7 |
| `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` | MOD — additive onboarding block |
| `design/workflows/orchestration.md` | MOD — §Reset |

No `src/novetest/memory/**`, `NOTICES.md`, `pyproject.toml`, or `README.md` touch.

## Pre-merge gate commands (verbatim)

```
env -u PYTHONPATH uv run mypy --strict src/novetest
# -> Success: no issues found in 114 source files

env -u PYTHONPATH uv run pytest -q tests/unit tests/integration
# -> 1348 passed, 3 skipped, 0 failed, 44 snapshots passed

env -u PYTHONPATH uv run pytest tests/integration/cli/test_reset_e2e.py
# -> 2 passed (round-trip de-skips against real wipe_project_store)
```

## Envelope-schema implications

None. `schema` stays `novetest/v1`; `data.onboarding` grows 3 → 4 (additive). The `command:"reset"` envelope byte-matches decision §"Envelope (happy path)".

## DoD (PM ticks — none this slice per brief; close after merge)

All in-scope deliverables done + the onboarding-enumeration acceptance criterion + the §Reset doc. The second-half cycle (this verb) closes after Main Branch merge + Manual Test, per the kick-back history.

## Carry-forward items for PM review (independent of the import fix)

1. **`available_in_phase=7`** on the reset CommandSpec (first post-MVP verb; matches the "Phase 7-adjacent" framing). Required bumping `test_phase_numbers_are_sane` upper bound 6 → 7. Confirm the phase number.
2. **Integration test at `tests/integration/cli/test_reset_e2e.py`** (not the brief's `tests/integration/`) — needs the `run_cli` fixture from `tests/integration/cli/conftest.py`; matches existing CLI-e2e convention.

## Post-merge actions

PM: replace `rm -rf .novetest && novetest init` with `novetest reset --confirm` in user-doc (`human/` + `agent/`) + website Docs troubleshooting, per decision §"Updates".

NOT self-merged, NOT pushed.
