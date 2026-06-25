---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-24
slug: reset-verb
related:
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md
---

# Task: Orchestration — `novetest reset --confirm` verb

- **Owner**: novetest-orchestration-team
- **Status**: pending
- **Created**: 2026-06-24
- **Pinned decision**: `agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md`
- **Sibling task**: `agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md` (provides the destructive primitive you consume)
- **Phase**: first slice **after** 0.1.x stable release tagged. Do **not** start until 0.1.x is on `main`.

## Goal

Register `novetest reset --confirm` as the 20th verb on the top-level command surface, with the workflow + renderer + envelope shape pinned by the decision doc.

## Why

novetest documents `rm -rf .novetest && novetest init` today as the official "start over" pattern. That recommendation violates the CLI's envelope-determinism / cross-platform / agent-callable positioning. This verb replaces the shell-out with a first-class CLI verb that emits a `novetest/v1` envelope.

## Scope

### In scope (you do this)

#### 1. New workflow at `src/novetest/orchestration/workflows/reset.py`

Mirror the shape of the existing `init.py` workflow (it's 32 lines — your reset workflow will be similar size). Composition:

```python
async def reset_project_workspace(workspace_path: Path) -> ResetResult:
    store = locate_project_store(workspace_path)         # from novetest.memory
    if store is None:
        raise ProjectStoreNotFoundError(...)             # exact exception type pinned by Memory's task
    report = wipe_project_store(store.path)              # NEW primitive Memory team is shipping
    init_result = await initialize_project_workspace(workspace_path)
    return ResetResult(wipe_report=report, init_result=init_result)
```

Add `ResetResult` dataclass (slots, frozen) carrying:
- `wipe_report: WipeReport` (from `novetest.memory.project_store`)
- `init_result: InitializationResult` (existing — from `novetest.orchestration.workflows.init`)

#### 2. Verb registration in `src/novetest/cli/app.py`

Add a `reset_cmd` handler beside the existing `init` handler (file is 1584 lines; the existing `licenses_cmd` at line 358 is the canonical small-verb template to mirror). Signature:

```python
@app.command(name="reset")
def reset_cmd(
    *,
    confirm: Annotated[bool, Parameter(name=["--confirm"])] = False,
) -> None:
    """Wipe the active Project Store and re-initialize. Requires --confirm."""
    if not confirm:
        _emit_and_exit(
            Envelope(
                command="reset", ok=False,
                errors=(EnvelopeError(
                    code="confirm-required",
                    message="`novetest reset` is destructive. Pass --confirm to acknowledge.",
                ),),
            ),
            EXIT_USAGE,
        )
    workspace = Path.cwd()
    try:
        result = asyncio.run(reset_project_workspace(workspace))
    except ProjectStoreNotFoundError as exc:
        _emit_and_exit(
            Envelope(command="reset", ok=False,
                     errors=(EnvelopeError(code="uninitialized", message=str(exc)),)),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        _emit_and_exit(
            Envelope(command="reset", ok=False,
                     errors=(EnvelopeError(code="store-corrupt", message=str(exc)),)),
            EXIT_STORAGE,
        )
    except OSError as exc:
        _emit_and_exit(
            Envelope(command="reset", ok=False,
                     errors=(EnvelopeError(code="store-wipe-failed", message=str(exc)),)),
            EXIT_STORAGE,
        )
    data = {
        "store_path": str(result.init_result.store.path),
        "store_state": result.init_result.store.store_state,
        "previous_initialized_at": result.wipe_report.previous_initialized_at,
        "initialized_at": result.init_result.store.initialized_at,
        "items_removed": result.wipe_report.items_removed,
        "engine_readiness": _readiness_payload(result.init_result.engine_readiness),
    }
    _emit_and_exit(Envelope(command="reset", ok=True, data=data), EXIT_OK)
```

This is the **byte-exact envelope shape** the decision doc pinned. Match it.

Also add the verb token to the reserved-token set used by the bare-target alias logic (the decision logic that prevents `novetest reset` from being misread as `novetest test reset` if there's a `reset/` directory in the workspace). Search `app.py` for where the existing verb tokens are reserved (line 92 area: `"licenses", "init"` etc.) and add `"reset"` to that list.

#### 3. New text-mode renderer at `src/novetest/cli/renderers/reset.py`

Mirror the shape of the existing `render_init` (in `src/novetest/cli/renderers/init.py`). Output:

```
✓ Reset .novetest/ at /abs/path/.novetest
  removed: 12 runs · 1 tombstone · 12 coverage · 7 regression · 8 localization · 2 replay
  engine readiness: ready — python/pytest 8.0.0
```

Header line uses `GLYPH_OK` (already imported via `_format`). The "removed" summary is a one-liner pluralization of `items_removed` slot values; suppress any zero-valued category to keep the line short. The "engine readiness" line is the same projection `render_init` uses — feel free to extract a shared helper if you do it cleanly without touching init's tests.

Wire the renderer into `src/novetest/cli/renderers/registry.py` — add `"reset": render_reset` to the `_RENDERERS` dict.

#### 4. Tests

- `tests/unit/cli/test_reset_cmd.py`:
  - `--confirm` missing → exit 2, `errors[0].code == "confirm-required"`.
  - No store walked-up → exit 2, `errors[0].code == "uninitialized"`.
  - Corrupt store → exit 5, `errors[0].code == "store-corrupt"`, store left intact (refusal property).
  - Wipe primitive raises OSError mid-flight → exit 5, `errors[0].code == "store-wipe-failed"`.
  - Happy path with a faked memory entry + coverage fact pre-seeded → exit 0, envelope `data.items_removed` matches, `data.store_state == "ready"`, `data.previous_initialized_at` is the old store's epoch-ms.
  - Mock `wipe_project_store` in the unit tests via monkeypatch; do not depend on Memory team's primitive landing first for unit-level coverage.
- `tests/integration/test_reset_e2e.py`:
  - End-to-end: `novetest init` → run a quick test → `novetest reset --confirm` → assert `novetest status` returns "no runs yet" envelope.
  - This integration test DOES depend on Memory's primitive being merged. PM will gate the cycle so the round-trip is provable.
- Snapshot pin: add the happy-path envelope to whichever directory the existing CLI snapshot tests live in (search for the `licenses` snapshot as the template).

#### 5. Renderer text-mode snapshot pin

Same dir as the other renderer snapshots; pin the byte-exact text output for the happy path.

### Out of scope (NOT your job)

- The `wipe_project_store()` primitive itself — that's Memory's task.
- Updating user-doc / website-plan handoff — PM will do that across both `human/` + `agent/` sets after both team handoffs land.
- The `vacuum` verb (open question #6 — separate, future cycle).
- Persisted "reset history" (no, deliberately — reset is destructive of history by definition).

## Pinned file list

- **Edit**: `src/novetest/cli/app.py` (add `reset_cmd` + register `"reset"` in the reserved-token set), `src/novetest/cli/renderers/registry.py` (1-line addition).
- **Create**: `src/novetest/orchestration/workflows/reset.py`, `src/novetest/cli/renderers/reset.py`.
- **Edit (tests)**: `tests/unit/cli/test_reset_cmd.py` (new), `tests/integration/test_reset_e2e.py` (new), snapshot files.
- **Update doc**: `design/workflows/orchestration.md` — add a `## Reset` section pinning the workflow + the envelope shape + the error paths. Cite the decision doc.

Do NOT touch any file in `src/novetest/memory/**` (that's Memory's territory).

## Acceptance criteria

- All unit tests + integration test green on Linux, macOS, Windows in CI release-matrix.
- Snapshot pin of the happy-path envelope merged; intentional drift would fail the snapshot guard, by design.
- `novetest --help` envelope now enumerates `reset` in `data.onboarding[]` (since it's an "in-place" setup-class verb — placed beside `init`). Update the registration list (search `app.py` line 92 area) so the help envelope sorts cleanly.
- `WORKLOG.md` entry per the standard format.
- Handoff at `agent-comms/handoffs/orchestration-team-2026-06-24-reset-verb.md` includes:
  - Pointer to the merged worktree.
  - "DoD bullets believed closed" list (none for this slice — post-MVP add; PM will close the bullet after both team handoffs merge).
  - Snapshot diff of the new envelope (for PM to spot-check before propagating to user-doc).

## Coordination

- Your work CAN proceed in parallel with Memory's. Unit-test against a mocked `wipe_project_store`; integration test runs after Memory's primitive merges.
- Sequence pin: do not merge until 0.1.x is tagged on `main`.
- If you find the renderer's "engine readiness" projection logic worth extracting into a shared helper, please do it cleanly (no test churn on the init side) — the extra ~10 LOC pays back the next time we add a setup-class verb. If the refactor balloons into "touching init's tests", drop it and keep the projection duplicated.

## Effort estimate (PM's read — challenge if you disagree)

- ~120 LOC across `app.py` + `reset.py` (workflow) + `reset.py` (renderer) + registry.
- ~200 LOC of unit tests + ~80 LOC of integration test.
- ~50 LOC of doc update in `orchestration.md`.
- One short cycle. If this balloons, surface via `agent-comms/questions/` before going wide.


---

## Amendment 2026-06-25 — import path correction (kick-back from Main Branch)

**Binding.** This amendment supersedes any contradictory text in the original brief above. Resolves `agent-comms/questions/main-branch-team-2026-06-25-orchestration-reset-import-path.md`.

### Cause

Orchestration's first slice attempt imported the 3 new Memory symbols via the package path:

```python
from novetest.memory import wipe_project_store, WipeReport, ProjectStoreNotFoundError
```

Memory deliberately did NOT re-export these symbols through `novetest.memory.__init__.py::__all__`. They are public **at module path only**: `from novetest.memory.project_store import ...`. The original brief §"In scope (1)" line 49 and Memory's handoff §"Public surface added" both pinned the module path; the slice did not honor it. Main Branch's pre-merge `mypy --strict` gate on the combined tree surfaced 4 `[attr-defined]` errors and kicked the slice back; the Memory primitive shipped independently at `cfffa70`.

### Fix (exactly 4 import statement changes in 2 Orchestration-owned files)

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

`src/novetest/cli/app.py:44`'s pre-existing `from novetest.memory import (...)` of long-standing public symbols (`locate_project_store`, etc.) **stays unchanged** — those ARE in `__init__.py::__all__`. Do not bundle that line into the fix.

### Worktree state — both restart options are valid

The existing worktree at `/home/yjshin/dev/aispace/novetest-reset-verb` (branch `orchestration/reset-verb`) is preserved with the original work rebased onto Memory's `cfffa70`:
- (A) **Fix in place**: edit the 4 lines directly on top of the existing rebased branch (current HEAD `d43d27a`), then re-handoff.
- (B) **Restart cleanly**: `git reset --hard main` on the worktree, re-author on top of `cfffa70`.

Either is acceptable. (B) is slightly cleaner for commit history; (A) is faster.

### Expected post-fix gates

- `env -u PYTHONPATH uv run mypy --strict src/novetest` → `Success: 114 source files` (matches original handoff prediction).
- `env -u PYTHONPATH uv run pytest -q tests/integration/cli/test_reset_e2e.py` → de-skips and passes the round-trip e2e.

### Carry-forward items from Orchestration's first handoff (NOT addressed here)

Two items in Orchestration's first handoff §"Decisions made / flagged for PM review" remain flagged for PM and should be re-raised in the new handoff:
1. `available_in_phase=7` decision on the `reset` verb metadata.
2. Test path placement under `tests/integration/cli/` vs `tests/integration/orchestration/`.

These are independent of the import-path fix and have no gate dependency.
