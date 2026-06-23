---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-23
slug: command-surface-licenses-enumeration
related:
  - agent-comms/tasks/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md
  - agent-comms/handoffs/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md
  - agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md  # parent cycle (#2b)
  - agent-comms/verifications/2026-06-22-novetest-licenses-cli-verb.md  # parent verification
---

# Verification — `command_surface.py` enumeration for `licenses`

## TL;DR

Atomic 1-commit fast-follow closing the discoverability gap from the
2026-06-22 `novetest licenses` verb cycle (Manual Test Nit #1). The
verb was already operational but absent from `novetest --help --output
json`'s `data.operating` list; AI agents scanning the canonical
command surface programmatically missed it. After this slice, the
verb appears at `data.operating[14]` of a 15-entry list — additive,
backward-compatible, snapshot-stable.

## Merged commit

- **Main HEAD:** `bc1a8bc` (FF-merge of `orchestration/command-surface-licenses-enumeration` onto `78785cf`)
- **Source slice commit:** `e55ba52 cli: enumerate licenses verb in top-level command surface`
- **Comms slice commit:** `bc1a8bc comms: orchestration handoff for command-surface-licenses-enumeration`

## Source handoff consumed

- `agent-comms/handoffs/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md`

## Scope (verified surgical)

`git diff 78785cf..HEAD --name-only`:

```
WORKLOG.md
agent-comms/handoffs/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md
src/novetest/orchestration/onboarding/command_surface.py
tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr
```

Exactly 2 src/tests files (+ 2 comms files). Both src/tests changes are
**additive only** — no pre-existing `_OPERATING` entry was reordered or
modified.

## Empirical anchors (pinned verbatim — copy-paste-safe)

### 1. Envelope top-level shape

```
top-level keys: ['command', 'data', 'errors', 'ok', 'schema', 'warnings']
schema: novetest/v1
command: help
ok: True
errors: []
warnings: []
data keys: ['onboarding', 'operating', 'schemaVersion']
schemaVersion: 1
onboarding count: 3
operating count: 15
```

### 2. The new entry (verbatim from the live envelope)

`data.operating[14]` (the 15th and last entry):

```json
{
  "availableInPhase": 0,
  "group": "orchestration",
  "name": "novetest licenses",
  "summary": "List third-party components Nove Test redistributes or links to."
}
```

### 3. The 14 pre-existing operating entries (order pinned)

In this exact order at `data.operating[0..13]`:

| Index | name |
|---:|---|
| 0 | `novetest test` |
| 1 | `novetest run` |
| 2 | `novetest memory list` |
| 3 | `novetest memory show` |
| 4 | `novetest memory delete` |
| 5 | `novetest inspect` |
| 6 | `novetest status` |
| 7 | `novetest coverage show` |
| 8 | `novetest coverage diff` |
| 9 | `novetest regression compare` |
| 10 | `novetest regression latest` |
| 11 | `novetest compare` |
| 12 | `novetest localization` |
| 13 | `novetest replay` |
| **14** | **`novetest licenses`** ← new |

`data.onboarding` unchanged (3 entries: `--version`, `--help`, `init`).

### 4. Gate measurements (Main Branch re-run post-merge)

- `mypy --strict src/novetest`: **Success: no issues found in 112 source files** (baseline unchanged)
- `pytest -q tests/unit tests/integration`: **1327 passed, 3 deselected, 0 failed; 40 snapshots passed** (baseline unchanged)
- `pytest tests/integration/cli/test_help_envelope_no_store.py` (snapshot stability, no `--snapshot-update`): **3 passed, 1 snapshot passed**

The 3 deselected items are the host-pollution `jest_*` tests from the
2026-06-22 cycle (Node 12.22.9 vs jest-cli 29.7.0); zero causal nexus
to this slice — same exoneration as 2026-06-22 verification §"Critical
edge cases #3". CI on Ubuntu runners with modern Node is the binding
gate.

## Verification scenarios for Manual Test

All scenarios run from the main worktree (`/home/yjshin/dev/aispace/Nove-Test`)
on the merged HEAD `bc1a8bc`. Prefix all `uv run` invocations with
`env -u PYTHONPATH` if your shell has the dev-host ROS2 py3.10 path
pollution (otherwise omit).

### Scenario A — JSON envelope: licenses appears in `data.operating`

```bash
env -u PYTHONPATH uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
op = e['data']['operating']
print('operating count:', len(op))
print('last entry:', op[-1])
"
```

Expected:
```
operating count: 15
last entry: {'availableInPhase': 0, 'group': 'orchestration', 'name': 'novetest licenses', 'summary': 'List third-party components Nove Test redistributes or links to.'}
```

### Scenario B — Existing entries byte-identical

```bash
env -u PYTHONPATH uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
op = e['data']['operating']
expected = ['novetest test', 'novetest run', 'novetest memory list',
            'novetest memory show', 'novetest memory delete',
            'novetest inspect', 'novetest status', 'novetest coverage show',
            'novetest coverage diff', 'novetest regression compare',
            'novetest regression latest', 'novetest compare',
            'novetest localization', 'novetest replay']
got = [c['name'] for c in op[:14]]
assert got == expected, f'Reordered! got {got}'
print('OK: 14 pre-existing entries in original order')
"
```

Expected:
```
OK: 14 pre-existing entries in original order
```

### Scenario C — Envelope schema unchanged

```bash
env -u PYTHONPATH uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['schema'] == 'novetest/v1'
assert e['data']['schemaVersion'] == 1
assert e['ok'] is True
assert e['errors'] == []
assert e['warnings'] == []
assert len(e['data']['onboarding']) == 3
print('OK: schema/schemaVersion/ok/errors/warnings/onboarding all unchanged')
"
```

Expected:
```
OK: schema/schemaVersion/ok/errors/warnings/onboarding all unchanged
```

### Scenario D — `novetest licenses` verb still operational (regression guard for parent cycle)

```bash
env -u PYTHONPATH uv run novetest licenses --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['command'] == 'licenses'
assert e['ok'] is True
assert e['data']['summary']['totalPackages'] == 5
print('OK: licenses verb still returns 5-package envelope, schema=', e['schema'])
"
```

Expected:
```
OK: licenses verb still returns 5-package envelope, schema= novetest/v1
```

### Scenario E — Text help output unchanged (no regression to human surface)

```bash
env -u PYTHONPATH uv run novetest --help 2>&1 | head -30
```

Expected: Cyclopts-rendered help that includes `licenses` as a
discoverable command (the text renderer auto-derives from the same
Cyclopts app graph, independent of `_OPERATING`). If `licenses` is
absent or any of the 14 pre-existing verbs is gone/renamed, regression.

### Scenario F — Snapshot stability under `--snapshot-update`

Drift sanity check: running pytest with `--snapshot-update` should NOT
re-write the snapshot (no diff produced).

```bash
env -u PYTHONPATH uv run pytest tests/integration/cli/test_help_envelope_no_store.py --snapshot-update 2>&1 | tail -5
git status --porcelain | grep ambr
```

Expected:
```
3 passed in ...s
```
And `git status` line should be **empty** (no .ambr files modified by
the re-snapshot). If you see ` M tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`,
the envelope is non-deterministic — regression.

(After confirming, run `git checkout -- tests/integration/cli/__snapshots__/` if anything was unexpectedly touched.)

### Scenario G — `command_surface.py` source: exactly 15 `_OPERATING` entries

```bash
python3 -c "
from novetest.orchestration.onboarding.command_surface import _OPERATING, _ONBOARDING
print('operating count:', len(_OPERATING))
print('onboarding count:', len(_ONBOARDING))
print('last operating:', _OPERATING[-1].name, '|', _OPERATING[-1].group, '| phase', _OPERATING[-1].available_in_phase)
"
```

Expected:
```
operating count: 15
onboarding count: 3
last operating: novetest licenses | orchestration | phase 0
```

## Critical edge cases worth probing

### #1 `availableInPhase: 0` semantics

The new entry has `availableInPhase: 0`, matching `--version` and
`--help` (the only other phase-0 entries). The rationale: `licenses`
requires NO `.novetest/` Project Store — it works on any clean
working directory. Verify by running `novetest licenses` from a
directory with no `.novetest/`:

```bash
mkdir -p /tmp/novetest-no-store && cd /tmp/novetest-no-store \
  && env -u PYTHONPATH uv --project /home/yjshin/dev/aispace/Nove-Test run novetest licenses --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['ok'] is True
print('OK: licenses works without .novetest/ — phase 0 claim holds')
"
```

Expected:
```
OK: licenses works without .novetest/ — phase 0 claim holds
```

### #2 `group: "orchestration"` consistency

Both `licenses` and the parent verbs (`test`, `inspect`, `status`,
`compare`) sit under `group: "orchestration"`. Existing groups:
`onboarding`, `run`, `memory`, `orchestration`, `coverage`,
`regression`, `localization`, `replay`. Verify no NEW group was
introduced (would break group-based filters downstream):

```bash
env -u PYTHONPATH uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
groups = sorted({c['group'] for c in e['data']['onboarding'] + e['data']['operating']})
expected = ['coverage', 'localization', 'memory', 'onboarding', 'orchestration', 'regression', 'replay', 'run']
assert groups == expected, f'Group set changed! got {groups}'
print('OK: group set unchanged =', groups)
"
```

Expected:
```
OK: group set unchanged = ['coverage', 'localization', 'memory', 'onboarding', 'orchestration', 'regression', 'replay', 'run']
```

### #3 Snapshot diff additivity (forensic verification)

If you want to manually inspect the `.ambr` diff against pre-merge
main, the entire change is a single 6-line additive block. Confirm by:

```bash
git diff 78785cf..bc1a8bc -- tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr
```

Expected: exactly one `@@` hunk with **6 added lines** (the new
`dict({...})` block for `novetest licenses`), zero removed lines, zero
modified lines.

### #4 Host pollution baseline (not a regression)

3 jest tests deselected during the Main Branch gate run remain
deselected. Cause: same Node 12.22.9 vs jest-cli 29.7.0 incompatibility
documented in the 2026-06-22 verification. This slice does NOT touch
`src/novetest/run/adapters/jest_adapter.py` or any jest infrastructure
— zero causal nexus. Binding gate: CI on Ubuntu runners (auto-triggered
on push of `bc1a8bc`).

## Resolved during merge

Nothing to resolve. The branch was a strict descendant of `78785cf`
with zero conflict surface; FF-merge completed in one step. Post-merge
test gate matched pre-merge handoff measurements byte-identically (1327
passed / 40 snapshots / 0 failed).

## Out of scope (carried by other teams)

- **CI verdict** for the run that the push of `bc1a8bc` triggers →
  not Main Branch responsibility to wait for; CEO/PM track via
  `gh run view`.
- **README / NOTICES.md / pyproject.toml** — all frozen per task brief.
- **Decision doc** — none needed; additive change, no contract semantics
  shift, no `schemaVersion` bump.

## DoD bullets (PM ticks at cycle close per task brief)

All 7 bullets believed closed by the originating team:

- #1 `CommandSpec` appended — 15th entry, 4 fields verbatim. (diff inspection)
- #2 Snapshot regenerated — 1 `.ambr` modified, additive only. (diff inspection)
- #3 No new tests — 2-file src/tests diff. (`git diff --name-only`)
- #4 mypy --strict GREEN — 112 source files. (re-run)
- #5 Full suite GREEN — 1327 passed. (re-run)
- #6 Envelope contract verified — both smoke commands print OK. (re-run)
- #7 Charter discipline held — no `cli/`, `orchestration/licenses/`, `NOTICES.md`, `pyproject.toml`, `README.md` touch. (diff inspection)
