---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-25
slug: reset-verb
related:
  - agent-comms/handoffs/orchestration-team-2026-06-24-reset-verb.md
  - agent-comms/verifications/2026-06-25-wipe-project-store-primitive.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/history/2026-06-25-memory-wipe-primitive-and-module-path-contract.md
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
---

# Verification: `novetest reset --confirm` verb — paired cycle closure

## Merged

- **Branch FF-merged**: `orchestration/reset-verb` (4 commits, rebased onto `096a1d4`)
  - `419be0c cli: novetest reset --confirm verb (wipe + re-init)` (rebased from `f144b05`)
  - `3367e30 comms: orchestration handoff for reset-verb (merge AFTER memory primitive)` (rebased from `d43d27a`)
  - `3b0d206 fix(reset): import wipe primitive from memory.project_store module path` (the kick-back fix; rebased from `ad78ab3`)
  - `89c1dc2 comms: re-handoff reset-verb after import-path fix (ready to merge)` (rebased from `cbd0ad2`)
- **Source handoff**: `agent-comms/handoffs/orchestration-team-2026-06-24-reset-verb.md` (re-handoff revision)
- **Companion**: Memory's `wipe_project_store` primitive already on main since `cfffa70` (verification `2026-06-25-wipe-project-store-primitive.md` closed by Manual Test → PM history `2026-06-25-memory-wipe-primitive-and-module-path-contract.md`)
- **Cycle pair status**: BOTH halves now on main. The decision-doc paired cycle (`2026-06-24-reset-verb-and-store-wipe-primitive.md`) is fully realized.

## Pre-merge gate (re-run on combined main after FF-merge)

All commands prefixed `env -u PYTHONPATH` (dev-host workaround; harmless on clean hosts).

- `env -u PYTHONPATH uv run mypy --strict src/novetest` → **Success: 114 source files** (was 112 pre-merge; +2 = `workflows/reset.py` + `cli/renderers/reset.py`). The 4 `[attr-defined]` errors from the kick-back are GONE — matches the re-handoff's predicted post-fix gate.
- `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` with the 3 host-pollution jest tests deselected (Node 12.22.9 vs jest-cli 29.7.0, baseline from 2026-06-22) → **1348 passed / 3 deselected / 0 failed; 44 snapshots passed**. Δ = +15 vs `cfffa70` baseline 1333: +14 new tests (orchestration's reset suite) + the round-trip e2e that previously was memory-gated-skip now de-skips and passes (+1 net).
- `env -u PYTHONPATH uv run pytest tests/integration/cli/test_reset_e2e.py` (targeted) → **2 passed**. Round-trip de-skips against the real `wipe_project_store` on main.

## Slice scope

15 src/+tests files + 1 design doc + handoff + WORKLOG (per re-handoff §"Files"):

- NEW: `src/novetest/orchestration/workflows/reset.py`, `src/novetest/cli/renderers/reset.py`
- MOD: `cli/app.py` (reset_cmd + `_SUBCOMMAND_TOKENS`), `cli/renderers/registry.py`, `cli/renderers/_format.py` (shared helper), `cli/renderers/init.py` (uses helper, output byte-identical), `orchestration/onboarding/command_surface.py` (+1 onboarding entry, `available_in_phase=7`), `orchestration/workflows/__init__.py`
- TESTS: `tests/unit/orchestration/workflows/test_reset.py` (2), `tests/unit/cli/test_reset_cmd.py` + snapshot (6 paths), `tests/unit/cli/renderers/test_reset.py` + snapshot (4), `tests/integration/cli/test_reset_e2e.py` (round-trip + confirm-gate)
- MOD: `tests/unit/cli/test_command_surface.py` (onboarding-includes-reset + phase invariant 6→7), `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` (additive onboarding block)
- DOC: `design/workflows/orchestration.md` §Reset

No `src/novetest/memory/**` touch.

## Empirical CLI smoke (reproduced at merged HEAD)

All 4 scenarios verbatim from the decision doc envelope contract — every assertion below was observed live during this verification, not extrapolated from tests.

### Scenario S1 — `--confirm` missing → exit 2 / "confirm-required"

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import json, subprocess, tempfile, pathlib
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    subprocess.run(['uv','run','novetest','init','--output','json'], cwd=workspace, capture_output=True, check=True)
    r = subprocess.run(['uv','run','novetest','reset','--output','json'], cwd=workspace, capture_output=True, text=True)
    env = json.loads(r.stdout)
    assert r.returncode == 2
    assert env['ok'] is False
    assert env['command'] == 'reset'
    assert env['errors'][0]['code'] == 'confirm-required'
    print('S1 OK')
PY
```

Observed: `exit=2 ok=False code=confirm-required command=reset`.

### Scenario S2 — happy path: exit 0 / store_state=ready / items_removed all 6 keys

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import json, subprocess, tempfile, pathlib
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    subprocess.run(['uv','run','novetest','init','--output','json'], cwd=workspace, capture_output=True, check=True)
    (workspace / '.novetest/memory/runs/run-fake').mkdir(parents=True, exist_ok=True)
    (workspace / '.novetest/memory/runs/run-fake/record.json').write_text('{}')
    r = subprocess.run(['uv','run','novetest','reset','--confirm','--output','json'], cwd=workspace, capture_output=True, text=True)
    env = json.loads(r.stdout)
    assert r.returncode == 0
    assert env['ok'] is True
    assert env['schema'] == 'novetest/v1'
    assert env['command'] == 'reset'
    d = env['data']
    assert d['store_state'] == 'ready'
    assert d['items_removed']['runs'] == 1
    assert sorted(d['items_removed'].keys()) == ['coverage_facts','localization_findings','regression_pairs','replay_results','runs','tombstones']
    assert d['previous_initialized_at'] > 0 and d['initialized_at'] > 0
    assert d['initialized_at'] >= d['previous_initialized_at']
    assert 'engine_readiness' in d
    # Round-trip: status confirms wipe
    r2 = subprocess.run(['uv','run','novetest','status','--output','json'], cwd=workspace, capture_output=True, text=True)
    env2 = json.loads(r2.stdout)
    assert env2['ok'] is True
    assert env2['data']['run_history_size'] == 0
    print('S2 OK')
PY
```

Observed: `exit=0 ok=True command=reset schema=novetest/v1 store_state=ready items_removed.runs=1 (all 6 keys present) prev_init>0 new_init>0 engine_readiness present; post-reset status.run_history_size=0`.

### Scenario S3 — no `.novetest/` → exit 2 / "uninitialized"

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import json, subprocess, tempfile, pathlib
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    r = subprocess.run(['uv','run','novetest','reset','--confirm','--output','json'], cwd=workspace, capture_output=True, text=True)
    env = json.loads(r.stdout)
    assert r.returncode == 2
    assert env['errors'][0]['code'] == 'uninitialized'
    print('S3 OK')
PY
```

Observed: `exit=2 code=uninitialized`.

### Scenario S4 — help envelope enumerates `novetest reset` in `data.onboarding`

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import json, subprocess
r = subprocess.run(['uv','run','novetest','--help','--output','json'], capture_output=True, text=True)
env = json.loads(r.stdout)
onboarding = env['data']['onboarding']
assert len(onboarding) == 4, f"expected 4 onboarding entries, got {len(onboarding)}"
reset = [e for e in onboarding if e['name'] == 'novetest reset']
assert len(reset) == 1
assert reset[0] == {
    'availableInPhase': 7,
    'group': 'onboarding',
    'name': 'novetest reset',
    'summary': 'Wipe the active Project Store and re-initialize (requires --confirm).',
}
print('S4 OK')
PY
```

Observed verbatim: `onboarding count=4 reset_present=True reset entry={'availableInPhase':7,'group':'onboarding','name':'novetest reset','summary':'Wipe the active Project Store and re-initialize (requires --confirm).'}`.

### Scenario S5 — `--output text` renderer is the decision-doc 3-line summary

```bash
env -u PYTHONPATH uv run python3 - <<'PY'
import subprocess, tempfile, pathlib
with tempfile.TemporaryDirectory() as td:
    workspace = pathlib.Path(td)
    subprocess.run(['uv','run','novetest','init','--output','json'], cwd=workspace, capture_output=True, check=True)
    (workspace / '.novetest/memory/runs/run-fake').mkdir(parents=True, exist_ok=True)
    (workspace / '.novetest/memory/runs/run-fake/record.json').write_text('{}')
    r = subprocess.run(['uv','run','novetest','reset','--confirm','--output','text'], cwd=workspace, capture_output=True, text=True)
    assert r.returncode == 0
    assert '✓ Reset .novetest/ at' in r.stdout
    assert 'removed: 1 run' in r.stdout
    assert 'engine readiness:' in r.stdout
    print('S5 OK')
PY
```

Observed verbatim:
```
✓ Reset .novetest/ at /tmp/tmpdcyq_hxn/.novetest
  removed: 1 run
  engine readiness: engine-missing — no engine detected
  issue: no supported (ecosystem, native engine) pair detected in workspace
```
(The "engine readiness: engine-missing" line + "issue:" line are correct for a bare tmpdir workspace with no pytest project; on a real workspace the readiness line would read e.g. `ready — python/pytest 8.0.0`.)

### Scenario S6 — targeted test module re-run (cross-check the snapshot pins)

```bash
env -u PYTHONPATH uv run pytest -q tests/unit/cli/test_reset_cmd.py tests/unit/cli/renderers/test_reset.py tests/unit/orchestration/workflows/test_reset.py tests/integration/cli/test_reset_e2e.py
```

Expected: **all pass** (5 + 4 + 2 + 2 = 13 tests + 3 snapshots).

## Critical edge cases worth probing

1. **Default-confirm safety**: the absence of `--confirm` MUST exit 2 (not "fall through to a target alias and try to run a test named `reset`"). The `_SUBCOMMAND_TOKENS` registration is the load-bearing guard — scenario S1 verifies it. If this regresses, a future user typo could silently invoke a destructive operation.

2. **Atomicity under failure** (FS-level): per the decision doc §"Atomicity guarantee", `Path.rename` must be a single syscall on the same FS. Unit test `test_wipe_rmtree_failure_leaves_staging_orphan_not_live_store` in Memory's slice covers this via monkeypatch; the orchestrated end-to-end behavior on a real FS lockout would need a permissioned filesystem fixture. Out of scope for Manual Test.

3. **Corrupt-store refusal does NOT auto-wipe** (decision doc §"Error paths"): if `store.json` is unreadable, `reset --confirm` must exit 5 / `store-corrupt` and leave the live store untouched. Memory's primitive-level scenario E (in `2026-06-25-wipe-project-store-primitive.md`) covers this; replicating at the CLI level is straightforward:
   ```bash
   env -u PYTHONPATH uv run novetest init --output json  # in tmpdir
   echo '{garbage' > .novetest/store.json
   env -u PYTHONPATH uv run novetest reset --confirm --output json
   # expect exit 5, errors[0].code == "store-corrupt", .novetest/ still present
   ```

4. **`available_in_phase=7` is a PM carry-forward** (re-handoff §"Carry-forward items"). PM should confirm the phase number; if it changes, the snapshot in `test_help_envelope_no_store.ambr` and the invariant bump in `test_command_surface.py::test_phase_numbers_are_sane` (6→7) both need re-pinning. Not gate-blocking.

5. **Doc carry-forward**: PM has a decision-doc obligation (`2026-06-24-reset-verb-and-store-wipe-primitive.md` §"Updates") to replace `rm -rf .novetest && novetest init` with `novetest reset --confirm` in `design/user-doc/{human,agent}/` and `design/website-plan/handoff/docs/troubleshooting.md`. Not blocked by this verification.

## Notes for Manual Test

- The verb is now fully runnable end-to-end on Linux/macOS — exercise S1–S5 against this verification doc on the merged HEAD.
- Cross-OS (Windows) reproducibility depends on the release-test matrix; outside this verification's scope.
- The renderer's "engine readiness: <state> — <engine_version>" line on a real workspace (with pytest/jest/etc. detected) is the same `format_engine_readiness()` shape `init` uses — if you have a real project handy, smoke `init` → seed data → `reset --confirm` → confirm `engine readiness: ready — python/pytest <ver>` on the third line.
- This cycle closure also concludes the paired Memory + Orchestration arc; the kick-back history (`2026-06-25-memory-wipe-primitive-and-module-path-contract.md`) documents the module-path-vs-package-path contract pattern for future cross-engine integrations.
