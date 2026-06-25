---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-25
slug: orchestration-reset-import-path
related:
  - agent-comms/handoffs/orchestration-team-2026-06-24-reset-verb.md
  - agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
  - agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md
---

# Kick-back: Orchestration `reset-verb` import path mismatch with Memory's public surface

## Status

- **Memory's `wipe_project_store` primitive merged** at `cfffa70` (independently green — mypy Success / 1333 passed / verification filed).
- **Orchestration's `reset-verb` slice NOT merged** — its worktree at `/home/yjshin/dev/aispace/novetest-reset-verb` (branch `orchestration/reset-verb`) was rebased onto `cfffa70` and FF-merged into main locally, but the **post-merge `mypy --strict` gate FAILED** with 4 errors. I reset main back to `cfffa70` and kicked the slice back.

## The failure

On the combined tree (memory primitive present, orchestration consumer present), `env -u PYTHONPATH uv run mypy --strict src/novetest` reported the SAME 4 errors that Orchestration's handoff predicted would resolve once Memory landed:

```
src/novetest/orchestration/workflows/reset.py:30: error: Module "novetest.memory" has no attribute "WipeReport"  [attr-defined]
src/novetest/orchestration/workflows/reset.py:60: error: Module "novetest.memory" has no attribute "ProjectStoreNotFoundError"  [attr-defined]
src/novetest/orchestration/workflows/reset.py:60: error: Module "novetest.memory" has no attribute "wipe_project_store"  [attr-defined]
src/novetest/cli/app.py:276: error: Module "novetest.memory" has no attribute "ProjectStoreNotFoundError"  [attr-defined]
```

Verbatim same lines as Orchestration's pre-merge measurement. Memory landing didn't fix them — and that's because of an import-path mismatch, not a missing symbol.

## Root cause: import path mismatch

Orchestration's code imports from `novetest.memory` (the package):

```python
# src/novetest/orchestration/workflows/reset.py:30
from novetest.memory import WipeReport
# src/novetest/orchestration/workflows/reset.py:60
from novetest.memory import (
    ProjectStoreNotFoundError,
    wipe_project_store,
)
# src/novetest/cli/app.py:276
from novetest.memory import ProjectStoreNotFoundError
```

But Memory delivered the 3 new symbols at the **module path** `novetest.memory.project_store`, NOT re-exported through the package's `__init__.py::__all__`:

```python
# src/novetest/memory/__init__.py current state at cfffa70
from novetest.memory.project_store import (
    ENV_NOVETEST_HOME, STORE_DIRNAME, STORE_METADATA_FILENAME,
    ProjectStore, ProjectStoreCorruptError,
    create_project_store, get_project_store_state, locate_project_store,
)
# wipe_project_store, WipeReport, ProjectStoreNotFoundError NOT re-exported
```

## Why this is Orchestration's bug (not Memory's, not a mid-air contract dispute)

The task brief AND Memory's handoff both pinned the module path. Memory delivered exactly what was specified.

- **`agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md:49`**: "`wipe_report: WipeReport` (from `novetest.memory.project_store`)" — the brief explicitly names the module path for the new symbols.
- **`agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md:81-82`**: "**Public surface added** (importable from `novetest.memory.project_store`): `wipe_project_store`, `WipeReport`, `ProjectStoreNotFoundError`. These are the exact symbol names Orchestration's task pre-committed to consuming."

Orchestration's brief did use `# from novetest.memory` in the comment on line 40, but that line was about `locate_project_store` — a *pre-existing* public symbol that IS in `novetest.memory.__init__.py`. The brief was consistent: pre-existing public surface from the package, new symbols from the module.

Orchestration's handoff `§"Decisions made / flagged for PM review"` doesn't mention the import path as a deliberate divergence — it appears to be an unflagged assumption that all of Memory's surface flows through `__init__.py`.

## The fix (Orchestration's territory, 4 lines)

Change 4 import statements in 2 files (both Orchestration-owned):

```python
# src/novetest/orchestration/workflows/reset.py:30
from novetest.memory.project_store import WipeReport
# src/novetest/orchestration/workflows/reset.py:60
from novetest.memory.project_store import (
    ProjectStoreNotFoundError,
    wipe_project_store,
)
# src/novetest/cli/app.py:276
from novetest.memory.project_store import ProjectStoreNotFoundError
```

(The 4th error is the second symbol on line 60.) `src/novetest/cli/app.py:44`'s pre-existing `from novetest.memory import (...)` of long-standing public symbols stays unchanged — those ARE in `__init__.py`.

After the fix, on the combined tree (Memory's `cfffa70` already on main + Orchestration's fix on top), `mypy --strict src/novetest` should return **Success: 114 source files** and the round-trip e2e (`tests/integration/cli/test_reset_e2e.py`) should de-skip and pass — matching Orchestration's original handoff prediction.

## Alternative considered + rejected

PM could instruct Memory to re-export the 3 new symbols through `__init__.py::__all__`. Two reasons not to:

1. **It overrides Memory's deliberately-narrower public surface choice.** Memory's handoff §"Public surface added" was explicit about the module-path scope. If PM wants to enlarge the package-level public surface, that's a separate design decision.
2. **The brief Orchestration agreed to already pinned the module path.** Asking Memory to change after the fact rewards Orchestration's import assumption.

## Other carry-forwards

Aside from the import path fix, Orchestration's slice looked otherwise clean during the rebase + dry-run merge:

- Rebase onto `cfffa70` produced one trivial WORKLOG.md conflict (both teams added top entries — I resolved newest-on-top, then aborted the merge along with the reset; the rebase work is preserved on `orchestration/reset-verb` branch as commit `d43d27a` should they want to reuse it, but they may also discard and re-author cleanly on top of `cfffa70`).
- INDEX.md rebase absorbed cleanly (no orchestration-specific divergence after memory's regen on `cfffa70`).
- No other file collisions.
- Their handoff §"Decisions made / flagged for PM review" item 2 (`available_in_phase=7` bump) and item 3 (test path under `tests/integration/cli/`) are still flagged for PM regardless of the import fix; not gate-blocking.

## Worktree state

- **Worktree preserved**: `/home/yjshin/dev/aispace/novetest-reset-verb` left in place (HEAD on `orchestration/reset-verb` at `ee8ec68`; my rebase to `d43d27a` was abandoned along with the main reset, so the branch tip is back at the original `ee8ec68` — Orchestration team's territory to fix and re-handoff).
- **Branch preserved**: `orchestration/reset-verb` local-only (never pushed).
- I did NOT remove either, per "originating team fixes; you do not."

## What I need from PM

1. Confirm the fix scope (4 import lines, 2 Orchestration-owned files).
2. Re-dispatch Orchestration with a brief amendment pin: "use `from novetest.memory.project_store import ...` for the 3 new symbols (not `from novetest.memory import ...`)."
3. Orchestration files a new handoff; Main Branch FF-merges + verifies on the combined tree (which now has Memory on `main`).
