---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-24
slug: reset-verb
related:
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/memory-team-2026-06-24-wipe-project-store-primitive.md  # MUST merge first
---

# Handoff — `novetest reset --confirm` verb (Orchestration half)

## ⚠ MERGE-ORDER PRECONDITION (read first)

**DO NOT FF-merge this branch before Memory's `wipe_project_store`
primitive is on `main`.** This slice consumes three symbols that ship in
the sibling cycle `memory-team-2026-06-24-wipe-project-store-primitive`:
`wipe_project_store`, `WipeReport`, `ProjectStoreNotFoundError`.

- Until Memory lands, `mypy --strict src/novetest` reports **exactly 4
  `[attr-defined]` errors** (listed below) — all on those 3 symbols.
- If this branch merges first, `main` carries those 4 mypy errors until
  Memory lands. The decision doc pins the order: *"Memory primitive
  first, then Orchestration's verb consumes it."*
- **Correct sequence**: (1) FF-merge Memory's primitive → (2) FF-merge
  this branch → (3) on the combined tree, `mypy --strict src/novetest`
  is **Success (0 errors)** and the round-trip e2e de-skips and passes.

Both branches are independent FF-merges off `main` (no file overlap:
Memory edits `src/novetest/memory/project_store.py` only; this slice
never touches `memory/`).

## Worktree / branch

- Worktree: `/home/yjshin/dev/aispace/novetest-reset-verb`
- Branch: `orchestration/reset-verb` off main `9f4dfe7`
- Commits (2): `0bf42c5` (code slice) + `<comms>` (this handoff + INDEX regen)
- 0.1.x schedule gate: **met** — `v0.1.0/v0.1.1/v0.1.2` tagged, `pyproject.toml::version == 0.1.2`, no `findings/` blockers.

## Files

| File | Change |
|---|---|
| `src/novetest/orchestration/workflows/reset.py` | NEW — `reset_project_workspace` + `ResetResult` (locate → wipe → re-init; lazy Memory import) |
| `src/novetest/cli/renderers/reset.py` | NEW — `render_reset` (3-line summary; zero-suppressed `items_removed`) |
| `src/novetest/cli/app.py` | MOD — `reset_cmd` handler (byte-exact envelope per decision) + `"reset"` in `_SUBCOMMAND_TOKENS` |
| `src/novetest/cli/renderers/registry.py` | MOD — `"reset": render_reset` |
| `src/novetest/cli/renderers/_format.py` | MOD — extracted shared `format_engine_readiness()` |
| `src/novetest/cli/renderers/init.py` | MOD — uses the extracted helper (**output byte-identical**) |
| `src/novetest/orchestration/onboarding/command_surface.py` | MOD — onboarding entry `novetest reset`, `available_in_phase=7` |
| `src/novetest/orchestration/workflows/__init__.py` | MOD — exports |
| `tests/unit/orchestration/workflows/test_reset.py` | NEW — workflow compose-order + refusal |
| `tests/unit/cli/test_reset_cmd.py` (+ `__snapshots__/test_reset_cmd.ambr`) | NEW — 5 handler paths + happy-envelope snapshot |
| `tests/unit/cli/renderers/test_reset.py` (+ `__snapshots__/test_reset.ambr`) | NEW — full/all-zero/partial/error |
| `tests/integration/cli/test_reset_e2e.py` | NEW — confirm-gate (runs now) + round-trip (Memory-gated skip) |
| `tests/unit/cli/test_command_surface.py` | MOD — onboarding-includes-reset + phase invariant `≤6 → ≤7` |
| `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` | MOD — additive (one `novetest reset` onboarding block) |
| `design/workflows/orchestration.md` | MOD — §Reset (workflow + envelope + error paths) |

No `src/novetest/memory/**`, `NOTICES.md`, `pyproject.toml`, or `README.md` touch.

## Verification (all `env -u PYTHONPATH`)

- `pytest -q tests/unit tests/integration` → **1341 passed / 4 skipped / 0 failed, 44 snapshots passed** (1327 baseline + 14 new tests; +1 skip = Memory-gated round-trip).
- `mypy --strict src/novetest` → **4 errors, 114 files** — verbatim:
  ```
  src/novetest/orchestration/workflows/reset.py:30: error: Module "novetest.memory" has no attribute "WipeReport"  [attr-defined]
  src/novetest/orchestration/workflows/reset.py:60: error: Module "novetest.memory" has no attribute "ProjectStoreNotFoundError"  [attr-defined]
  src/novetest/orchestration/workflows/reset.py:60: error: Module "novetest.memory" has no attribute "wipe_project_store"  [attr-defined]
  src/novetest/cli/app.py:276: error: Module "novetest.memory" has no attribute "ProjectStoreNotFoundError"  [attr-defined]
  ```
  All 4 resolve when Memory's primitive lands. NOT silenced with `# type: ignore` (would flip to `unused-ignore` under `--strict` post-merge).
- Standalone import smoke (no Memory primitive present): `novetest.cli.app` + `novetest.orchestration.workflows.reset` + `novetest.cli.renderers.reset` all import.
- init renderer snapshots UNCHANGED after the `format_engine_readiness` extraction (byte-identical output).

## Snapshot diffs (PM spot-check)

Happy-path envelope (`tests/unit/cli/__snapshots__/test_reset_cmd.ambr`) byte-matches decision §"Envelope (happy path)": `command:"reset"`, `data.items_removed = {runs:12, tombstones:1, coverage_facts:12, regression_pairs:7, localization_findings:8, replay_results:2}`, `previous_initialized_at:1717939496000`, `initialized_at:1719215123000`, `store_state:"ready"`.

Renderer happy-path text (`tests/unit/cli/renderers/__snapshots__/test_reset.ambr`):
```
✓ Reset .novetest/ at /work/.novetest
  removed: 12 runs · 1 tombstone · 12 coverage · 7 regression · 8 localization · 2 replay
  engine readiness: ready — python/pytest 8.0.0
```

Help-envelope diff (additive only) — new onboarding entry after `novetest init`:
```
+        dict({
+          'availableInPhase': 7,
+          'group': 'onboarding',
+          'name': 'novetest reset',
+          'summary': 'Wipe the active Project Store and re-initialize (requires --confirm).',
+        }),
```

## Envelope-schema implications

None. `schema` stays `novetest/v1`; `command_surface` `schemaVersion` stays `1`. `data.operating` unchanged; `data.onboarding` grows 3 → 4 (additive, backward-compatible). The reset command's own envelope is a new `command:"reset"` shape, fully additive.

## DoD bullets believed closed (PM ticks — none this slice per brief)

The brief states: *"DoD bullets believed closed list (none for this slice — post-MVP add; PM will close the bullet after both team handoffs merge)."* All 5 in-scope deliverables done (workflow, handler+token, renderer+registry, tests, snapshot pins) + the onboarding enumeration acceptance criterion + the doc update. PM closes after Memory's half merges.

## Decisions made / flagged for PM review

1. **`command_surface.py` edited though the brief's pinned file list omitted it** — the acceptance criterion *"`--help` envelope enumerates reset in `data.onboarding[]`"* is produced by `describe_command_surface()` (command_surface.py), NOT `_SUBCOMMAND_TOKENS` (app.py, which only governs the bare-target alias). Both files Orchestration-owned; no boundary crossed.
2. **`available_in_phase=7`** for the reset CommandSpec (first post-MVP verb; matches the decision/Memory-task "Phase 7-adjacent" framing). Required bumping `test_phase_numbers_are_sane`'s upper bound 6 → 7. Flagged for PM to confirm the phase number.
3. **Integration test placed at `tests/integration/cli/test_reset_e2e.py`** (not the brief's `tests/integration/test_reset_e2e.py`) — needs the `run_cli` fixture from `tests/integration/cli/conftest.py`; matches the existing CLI-e2e convention.

## Post-merge actions (after Memory lands + both merge)

- Re-run `mypy --strict src/novetest` → expect **Success, 0 errors**.
- Re-run `pytest tests/integration/cli/test_reset_e2e.py` → the round-trip de-skips and must pass.
- PM: tick reset DoD; add the Phase-7-adjacent delivery bullet; replace `rm -rf .novetest && novetest init` in user-doc + website troubleshooting per decision §"Updates".

NOT self-merged, NOT pushed.
