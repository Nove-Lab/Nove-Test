---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-25
slug: wipe-project-store-primitive
related:
  - agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md
---

# Verification: Memory `wipe_project_store()` primitive @ `cfffa70`

## Merged

- **Commit**: `cfffa70 feat(memory): wipe_project_store primitive for reset verb`
- **Source handoff**: `agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md`
- **Slice scope** (FF-merge, 6 files, +359 / -1):
  - `src/novetest/memory/project_store.py` MOD (+107)
  - `tests/unit/memory/test_project_store.py` MOD (+137; 6 new test cases)
  - `design/interace-contract/memory.md` MOD (+23; new §3 "Store wipe primitive")
  - `WORKLOG.md` MOD (top entry)
  - `agent-comms/INDEX.md` MOD (regen)
  - `agent-comms/handoffs/memory-team-2026-06-24-wipe-project-store-primitive.md` NEW

## Pre-merge gate (re-run on main HEAD `cfffa70`)

All commands prefixed with `env -u PYTHONPATH` per the dev-host workaround (ROS2 py3.10 PYTHONPATH shadows the venv numpy on this machine; mandatory on Linux dev hosts that have ROS2 sourced, harmless on clean hosts).

- `env -u PYTHONPATH uv run mypy --strict src/novetest` → **Success: 112 source files** (baseline pre-merge was 112; primitive added zero typing surface drift).
- `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` with the 3 host-pollution jest tests deselected (Node 12.22.9 vs jest-cli 29.7.0 from 2026-06-22 cycle baseline — not caused by this slice) → **1333 passed / 3 deselected / 0 failed; 40 snapshots passed**. Δ = +6 vs prior baseline 1327, exactly matching the 6 new wipe test cases.

## ⚠ Companion slice NOT on main

The decision doc (`agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md`) pairs this Memory primitive with an Orchestration verb (`novetest reset --confirm`). **Only the Memory half is on main as of `cfffa70`.** Orchestration's worktree exists (`/home/yjshin/dev/aispace/novetest-reset-verb`, branch `orchestration/reset-verb`) but failed integration: their imports use `from novetest.memory import ...` instead of `from novetest.memory.project_store import ...` (the path the task brief pinned and Memory's handoff §"Public surface added" promised). Kicked back via `agent-comms/questions/main-branch-team-2026-06-25-orchestration-reset-import-path.md`. **Until that lands, `novetest reset` is NOT runnable end-to-end** — but the Memory primitive itself ships independently and is purely additive (no existing call site, no behavior change). This verification scope is the primitive ONLY.

## What the primitive guarantees (decision-doc atomicity sequence)

Per `agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md` §"Atomicity guarantee", `wipe_project_store(store_path: Path) -> WipeReport` must:

1. Reject when `store.json` missing → `ProjectStoreNotFoundError`.
2. Reject when `store.json` unreadable (no auto-wipe) → `ProjectStoreCorruptError`.
3. Count terminal artifacts pre-mutation (keys: `runs`, `tombstones`, `coverage_facts`, `regression_pairs`, `localization_findings`, `replay_results`).
4. Compute `staging = store_path.parent / f".novetest.deleting.<ulid>"`.
5. POSIX-atomic `Path.rename(store_path, staging)` (single `rename(2)` syscall on same FS).
6. `shutil.rmtree(staging)`; on failure the live store is already detached (recoverable via fresh `init`).

The primitive does NOT re-init — the future Orchestration `reset` workflow composes `wipe` + `create_project_store` + `assess_engine_readiness`.

## Scenarios for Manual Test (all `env -u PYTHONPATH`)

### A. Public surface import — module path that the brief + handoff pinned

```bash
env -u PYTHONPATH uv run python3 -c "
from novetest.memory.project_store import wipe_project_store, WipeReport, ProjectStoreNotFoundError
import inspect
print('sig:', inspect.signature(wipe_project_store))
print('WipeReport fields:', list(WipeReport.__dataclass_fields__))
print('WipeReport frozen+slots:', WipeReport.__dataclass_params__.frozen, '__slots__' in WipeReport.__dict__)
print('Error MRO:', [c.__name__ for c in ProjectStoreNotFoundError.__mro__][:4])
"
```

Expected verbatim:
```
sig: (store_path: 'Path') -> 'WipeReport'
WipeReport fields: ['store_path', 'previous_initialized_at', 'items_removed']
WipeReport frozen+slots: True True
Error MRO: ['ProjectStoreNotFoundError', 'RuntimeError', 'Exception', 'BaseException']
```

### B. Public surface import — package path is INTENTIONALLY not re-exported

This codifies the Orchestration kick-back. The 3 new symbols are NOT in `novetest/memory/__init__.py::__all__`; importing from the package raises `ImportError`. This is the contract Memory delivered; Orchestration must use the module path.

```bash
env -u PYTHONPATH uv run python3 -c "
try:
    from novetest.memory import wipe_project_store
    print('UNEXPECTED: package-path import succeeded')
except ImportError as e:
    print('package-path correctly rejects:', str(e)[:80])
"
```

Expected:
```
package-path correctly rejects: cannot import name 'wipe_project_store' from 'novetest.memory' ...
```

### C. Happy path — wipe a real store with seeded terminal artifacts

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import tempfile, pathlib
from novetest.memory.project_store import create_project_store, wipe_project_store
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    store = create_project_store(workspace)
    sp = store.path
    # Seed terminal artifacts per Memory engine layout
    for sub in [
        'memory/runs/run-fake-1', 'memory/runs/run-fake-2',
        'coverage/facts/fake1', 'regression/pairs/fake1',
        'localization/findings/fake1', 'replay/results/fake1',
    ]:
        (sp / sub).mkdir(parents=True, exist_ok=True)
    (sp / 'memory/runs/run-fake-1/record.json').write_text('{}')
    (sp / 'memory/runs/run-fake-2/record.json').write_text('{}')
    report = wipe_project_store(sp)
    assert sp.exists() is False, 'live store should be gone'
    assert list(workspace.glob('.novetest.deleting.*')) == [], 'staging orphan must be cleaned'
    assert report.previous_initialized_at > 0, 'ms-epoch timestamp preserved'
    assert report.store_path == sp, 'WipeReport.store_path echoes original'
    assert sorted(report.items_removed.keys()) == [
        'coverage_facts', 'localization_findings',
        'regression_pairs', 'replay_results', 'runs', 'tombstones',
    ]
    assert report.items_removed['runs'] == 2
    print('OK')
PY
```

Expected: `OK`. Empirically reproduced at `cfffa70` during this verification.

### D. Refusal — store missing

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import tempfile, pathlib
from novetest.memory.project_store import wipe_project_store, ProjectStoreNotFoundError
with tempfile.TemporaryDirectory() as td:
    bogus = pathlib.Path(td) / 'nope'
    try:
        wipe_project_store(bogus)
        raise SystemExit('UNEXPECTED: no exception')
    except ProjectStoreNotFoundError as e:
        print('refused:', type(e).__name__)
PY
```

Expected: `refused: ProjectStoreNotFoundError`. Empirically reproduced.

### E. Refusal — corrupt store NOT auto-wiped (load-bearing safety property)

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import tempfile, pathlib
from novetest.memory.project_store import create_project_store, wipe_project_store, ProjectStoreCorruptError
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    store = create_project_store(workspace)
    sp = store.path
    (sp / 'store.json').write_text('{not valid json')
    try:
        wipe_project_store(sp)
        raise SystemExit('UNEXPECTED: corrupt store was wiped')
    except ProjectStoreCorruptError as e:
        # Live store path MUST still exist - corrupt state is for operator inspection, not auto-cleanup
        assert sp.exists(), 'corrupt store auto-wiped; safety property violated'
        print('corrupt refused, store preserved:', type(e).__name__)
PY
```

Expected: `corrupt refused, store preserved: ProjectStoreCorruptError`. Decision doc §"Error paths" pins this as the load-bearing safety property.

### F. Round-trip — wipe then re-init succeeds (post-wipe leaves no residual state)

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import tempfile, pathlib
from novetest.memory.project_store import create_project_store, wipe_project_store
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    store1 = create_project_store(workspace)
    wipe_project_store(store1.path)
    store2 = create_project_store(workspace)
    assert store2.path == store1.path
    assert (store2.path / 'store.json').exists()
    print('round-trip OK')
PY
```

Expected: `round-trip OK`. This is the contract the future `reset` verb composes against.

### G. Targeted test module re-run

```bash
env -u PYTHONPATH uv run pytest -q tests/unit/memory/test_project_store.py
```

Expected: **22 passed** (16 pre-existing + 6 new wipe cases). 0 failures, 0 skipped.

## Critical edge cases worth probing

1. **Staging-orphan on rmtree failure** (decision-doc safety property): if `shutil.rmtree(staging)` fails (e.g., permission, EBUSY), the LIVE store path must be gone but the staging orphan retains the data. Unit test #5 covers this via monkeypatch; an FS-level reproduction would need a real permission lockout. Out of scope for this verification (unit test suffices).

2. **`previous_initialized_at` epoch unit**: per `WipeReport`, this is milliseconds-since-epoch (matches the rest of Memory's timestamp surface). Manual Test should sanity-check the order of magnitude (13-digit value, > 1.7x10^12 for 2024+).

3. **Cross-filesystem `Path.rename`**: when `store_path.parent` is on a different mount than the staging target, `Path.rename` silently degrades from atomic-rename to copy-then-delete on some platforms. The handoff §"Test coverage gaps surfaced" flagged this as a deliberate gap for the cross-OS release-matrix to catch. Not actionable for Manual Test on Linux dev hosts.

4. **`novetest reset --confirm` CLI is NOT runnable yet** — the consumer slice is kicked back. Probing the CLI for "reset" will exit with "unknown command" or fall through to the run-target alias. This is expected until Orchestration's fix lands.

## Notes for Manual Test

- The primitive is a Python-level surface only — no CLI exposure yet (deliberate: Orchestration owns the verb).
- All scenarios run in isolated `tempfile.TemporaryDirectory()` workspaces; no persistent Project Store side effects.
- If you want to spot-check Memory's 6 new unit tests directly, they're at `tests/unit/memory/test_project_store.py` (lines added by `cfffa70`).
- Companion slice tracker: orchestration's worktree at `/home/yjshin/dev/aispace/novetest-reset-verb` (branch `orchestration/reset-verb`) is preserved on this host pending their fix. Do not exercise `novetest reset` until that lands on main and a follow-up verification doc is filed.
