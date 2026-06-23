---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-23
slug: command-surface-licenses-enumeration
related:
  - agent-comms/tasks/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md
  - agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md  # parent cycle (#2b)
---

# Handoff — `command_surface.py` enumeration for `licenses`

## TL;DR

Atomic 1-commit fast-follow closing the discoverability gap from the
2026-06-22 `novetest licenses` verb cycle (Manual Test Nit #1 / parent
history §"Load-bearing learning #4"). The verb was operational but
absent from `novetest --help --output json`'s `data.operating`
enumeration; AI agents scanning the canonical command surface missed
it. Now enumerated at index 14 of 15.

**Ready for Main Branch FF-merge.** NOT self-merged, NOT pushed.

## Worktree / branch

- Worktree: `/home/yjshin/dev/aispace/novetest-cmdsurface-licenses`
- Branch: `orchestration/command-surface-licenses-enumeration` off main `78785cf`
- Commits (2):
  - `e55ba52` — `cli: enumerate licenses verb in top-level command surface` (code slice: command_surface.py + ambr + WORKLOG.md)
  - `<comms>` — this handoff + INDEX regen (comms slice)
- FF-mergeable: branch is a strict descendant of `78785cf`; main untouched.

## Files

| File | Change | Notes |
|---|---|---|
| `src/novetest/orchestration/onboarding/command_surface.py` | MOD | 15th `CommandSpec` appended to end of `_OPERATING` (after `novetest replay`). 4 fields verbatim per brief data contract. No reorder. |
| `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` | MOD (`--snapshot-update`) | Additive only: one new dict block after `novetest replay`; 14 pre-existing entries byte-identical. |
| `WORKLOG.md` | MOD | Cycle entry prepended (rides code slice per pre-commit hook). |
| `agent-comms/handoffs/...-command-surface-licenses-enumeration.md` | NEW | This file (comms slice). |
| `agent-comms/INDEX.md` | MOD | `regen_comms_index.py` output (comms slice). |

## DoD bullets believed closed (PM ticks)

- **#1 `CommandSpec` appended** — 15th entry at end of `_OPERATING`; `name="novetest licenses"`, `summary="List third-party components Nove Test redistributes or links to."`, `group="orchestration"`, `available_in_phase=0`. Verbatim per data contract.
- **#2 Snapshot regenerated** — exactly 1 `.ambr` modified; diff additive only (one new block, zero pre-existing entries reordered/modified).
- **#3 No new tests** — `git diff main --name-only` shows exactly 2 files (command_surface.py + test_help_envelope_no_store.ambr).
- **#4 mypy --strict GREEN** — 112 source files (baseline unchanged).
- **#5 Full suite GREEN** — 1327 passed / 3 skipped / 0 failed; 40 snapshots passed (= 2026-06-22 baseline).
- **#6 Envelope contract verified** — smoke #4 + #5 both print OK (verbatim below).
- **#7 Charter discipline held** — no `src/novetest/cli/`, `src/novetest/orchestration/licenses/`, `NOTICES.md`, `pyproject.toml`, `README.md` touch.

## Empirical proof (verbatim)

### Verification command #4 (licenses enumerated)
```
OK: licenses enumerated at index 14 of 15
```

### Verification command #5 (14 pre-existing entries unchanged)
```
OK: 14 pre-existing entries in original order
```

### `git diff main --name-only`
```
src/novetest/orchestration/onboarding/command_surface.py
tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr
```

### `git status --porcelain | grep ambr` (post-regen, pre-commit)
```
 M tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr
```

### Snapshot stability (re-run WITHOUT `--snapshot-update`)
```
1 snapshot passed.
3 passed in 0.41s
```
Passes without further regen — snapshot is stable.

### `.ambr` diff (additive only)
```
@@ -108,6 +108,12 @@
           'name': 'novetest replay',
           'summary': 'Re-execute a stored run and classify reproducibility.',
         }),
+        dict({
+          'availableInPhase': 0,
+          'group': 'orchestration',
+          'name': 'novetest licenses',
+          'summary': 'List third-party components Nove Test redistributes or links to.',
+        }),
       ]),
       'schemaVersion': 1,
     }),
```

## Envelope-schema implications

None. `schema` (`novetest/v1`) and `schemaVersion` (`1`) both unchanged.
`data.onboarding` unchanged (3 entries). `data.operating` grows 14 → 15
entries — additive, backward-compatible (an existing AI agent iterating
the list simply sees one more entry). No decision-doc bump required.

## Note for Main Branch

All verification commands were run with `env -u PYTHONPATH` to bypass
this dev host's inherited ROS2 py3.10 PYTHONPATH (which shadows the
venv numpy and otherwise crashes `uv run`). This is host pollution,
not a slice property — CI runners are clean. FF-merge has zero conflict
risk: 2-file additive diff, no overlap with any in-flight cycle (INDEX
shows all transient channels empty at cycle start).
