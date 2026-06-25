---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-06-25
slug: novetest-reset-verb-paired-cycle-close
related:
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/history/2026-06-25-memory-wipe-primitive-and-module-path-contract.md
  - src/novetest/orchestration/workflows/reset.py
  - src/novetest/cli/renderers/reset.py
  - src/novetest/cli/app.py
---

# History: `novetest reset --confirm` verb — paired cycle closed; first post-MVP slice landed

## Summary

Both halves of the `novetest reset` cycle pinned by `2026-06-24-reset-verb-and-store-wipe-primitive.md` are now on `main`. The Memory `wipe_project_store` primitive landed yesterday at `cfffa70`; the Orchestration `novetest reset --confirm` verb landed today at `419be0c` (verb) + `3b0d206` (import-path fix per the kick-back amendment) — verified by Main Branch at `c6266e7`, found PASSED by Manual Test. CI 10/10, mypy clean (114 source files = 112 baseline + 2 new), pytest 1348 passed (+15 vs `cfffa70` baseline 1333 = +14 new reset tests + 1 de-skipped round-trip e2e).

**This is the first post-MVP slice to land cleanly end-to-end.** It also closes the two-day kick-back arc documented in `2026-06-25-memory-wipe-primitive-and-module-path-contract.md`: yesterday's 4-line wrong-import-path slice rebased the fix (`3b0d206`) onto Memory's `cfffa70`, and the FF-merge composes both halves into a fully runnable destructive verb.

## What the verb does (end-to-end on `main`)

- `novetest reset` (no flag) → exit 2, `errors[0].code = "confirm-required"`. The `_SUBCOMMAND_TOKENS` registration is the load-bearing guard against a typo silently falling through to the test-run alias.
- `novetest reset --confirm` (happy path) → exit 0, `data.store_state = "ready"`, `items_removed` with all 6 keys (`runs / tombstones / coverage_facts / regression_pairs / localization_findings / replay_results`), `previous_initialized_at` + `initialized_at` epoch-ms timestamps, full `engine_readiness` block from the re-init.
- `novetest reset --confirm` against a corrupt store → **exit 5, `errors[0].code = "store-corrupt"`, live store preserved on disk for operator inspection.** The load-bearing safety property holds end-to-end at the CLI consumer level, not just inside Memory's primitive.
- `novetest reset --confirm` on a bare workspace → exit 2, `errors[0].code = "uninitialized"`. No silent auto-init, no destructive no-op.
- `novetest --help --output json` enumerates `novetest reset` in `data.onboarding` at `availableInPhase: 7` — discoverable in the canonical command surface.
- Text-mode renderer matches the decision-doc 3-line summary: `✓ Reset .novetest/ at <path>` + `  removed: <N> run(s) ...` + `  engine readiness: <state> — <engine>/<version>`. The `engine readiness` line reuses a new shared `format_engine_readiness()` helper (`cli/renderers/_format.py`) extracted from `init`'s renderer; `init`'s output stays byte-identical (snapshot-pinned).

## Load-bearing lessons (additive to yesterday's history)

### 1. The kick-back-then-fix loop is a textbook protocol pattern, not an exception

Yesterday Main Branch caught the wrong-import-path mismatch via combined-tree `mypy --strict` BEFORE polluting main; today the one-line fix (`3b0d206`) rebased cleanly onto Memory's `cfffa70`, and the re-handoff composed against the primitive trivially. Total wall-clock recovery: under 24 hours from kick-back filing to verb-on-main. **Pattern for future cross-engine integrations**: trust the strict pre-merge gate, file the kick-back as a question to PM, preserve the worktree, fix in place. The protocol is cheap when followed.

### 2. Destructive verbs need three guards, all verified at the CLI consumer level

Per this cycle:
1. **Explicit acknowledgment** — `--confirm` flag is mandatory; absence returns `confirm-required` exit 2.
2. **Refuse-on-corruption** — a corrupt store is preserved for operator inspection; the destructive path will NOT auto-wipe what it cannot read.
3. **Atomicity** — single-syscall rename to `.novetest.deleting.<ulid>/` followed by rmtree; an interrupted rmtree leaves the live store detached (not partially destroyed), recoverable via fresh `init`.

All three are codified as decision-doc invariants, primitive-level unit tests (Memory), AND CLI-level smoke scenarios (Manual Test S1, edge case #3, edge case discussion in verification doc). Future destructive verbs (e.g. a `novetest memory wipe` batch mode, a future `vacuum` GC verb) should follow the same triple-guard pattern.

### 3. Shared-helper extraction without test churn is achievable

Orchestration extracted `format_engine_readiness()` from `init`'s renderer into `cli/renderers/_format.py`. `init`'s text output stayed byte-identical (snapshot-pinned), so the extraction shipped with zero regression. **Pattern**: when adding a second consumer of a per-engine projection, extract the helper THEN consume it from both — never just duplicate. The snapshot pin is your safety net.

### 4. `availableInPhase: 7` is the conventional marker for post-MVP verbs

The `delivery-phasing.md` formal Phase 7 section is reserved for MCP transport. The conventional usage adopted here: `availableInPhase: 7` on the `reset` verb means "first post-MVP slice"; future post-MVP verbs (e.g. `--reruns` flag, eventual `vacuum`) continue with `7` until/unless `delivery-phasing.md` introduces a numbered Phase 8+. This usage was not formally pinned in advance and is recorded here as the precedent. PM may revisit if the convention proves brittle.

## Doc carry-forward folded into existing PM task

Decision doc §"Updates" lists the substitution of `rm -rf .novetest && novetest init` with `novetest reset --confirm` in:

- `design/user-doc/human/troubleshooting.md` + `after-test.md`
- `design/user-doc/agent/troubleshooting.md` + `after-test.md`
- `design/website-plan/handoff/docs/troubleshooting.md`

These edits **share the same 9-file surface** as the already-queued `pm-team-2026-06-25-user-doc-taxonomy-realignment.md` task. PM will perform both substitutions (category-name realignment + rm-rf→reset substitution) in a single PM-only cycle when the user-doc realignment task is picked up. No separate task needed.

## Test count + gate deltas (verbatim from findings)

- mypy: 112 → **114** files clean (+2 = `workflows/reset.py` + `cli/renderers/reset.py`).
- pytest: 1333 → **1348** passed (+15 = +14 new reset tests + 1 de-skipped round-trip e2e).
- snapshots: 40 → **44** passed (+4 reset).
- CI matrix: **10/10 SUCCESS** on HEAD `c6266e7` (`gh run 28147801448`, 5m1s) — 3 OS × 3 Py + 1 perf job.

## Standing recommendations carried forward

- **Dev-host Node 12 pollution**: 3 jest integration tests fail locally on the dev box with Node 12.22.9 vs jest-cli 29.7.0. Same baseline carried from 2026-06-22, 2026-06-23, 2026-06-25-wipe-primitive cycles. CI Ubuntu (Node 20+) is the binding gate. Not actionable per cycle.
- **`availableInPhase: 7` convention** — recorded here as precedent; future post-MVP verb decisions inherit unless `delivery-phasing.md` introduces a numbered Phase 8.
- **Cosmetic verification-doc typo** (S6 "13 tests + 3 snapshots" vs actual "14 tests + 4 snapshots") — verification file is deleted as part of this cycle close; no fix needed.

## Cycle artifacts (deleted on close)

- `agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md` (with the 2026-06-25 amendment)
- `agent-comms/handoffs/orchestration-team-2026-06-24-reset-verb.md` (re-handoff revision)
- `agent-comms/verifications/2026-06-25-reset-verb.md`
- `agent-comms/findings/manual-test-team-2026-06-25-reset-verb.md`
