---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-21
slug: jest-adapter-unit-test-windows
related:
  - tasks/run-team-2026-05-21-jest-adapter-unit-test-windows.md
  - questions/release-team-2026-05-21-jest-adapter-unit-test-windows.md
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
---

# Handoff: make `test_argv_includes_target_expression` OS-aware

## Summary

CI was red on all 3 `windows-latest` cells (`1 failed, 339 passed`). The
lone failure was a stale POSIX-only unit test left behind by the npx fix
(`0e9ab71`): `test_argv_includes_target_expression` pinned
`captured_argv[0] == _FAKE_NPX`, but on Windows `run_jest` builds argv as
`["cmd", "/c", "npx", "jest", ...]` so `argv[0]` is `cmd`. Fixed — the
test now asserts only its OS-invariant concern. **Test-only change.**

## Worktree

- **Path:** `/home/yjshin/dev/novetest-jest-unit-test-windows`
- **Branch:** `worktree-run-team-jest-adapter-unit-test-windows`
- **Base commit:** `deb8404` (main)

## Files written / modified

### Modified
- `tests/unit/run/adapters/test_jest_adapter.py` —
  `test_argv_includes_target_expression`: dropped the OS-specific
  `argv[0]`/`argv[1]` prefix pins; now asserts `"jest"` is in argv, the
  canonical flags are present, and the target expression is the last
  argv element. Full-file scan confirmed no other test carried the same
  POSIX-only assumption.
- `WORKLOG.md`, `agent-comms/handoffs/...` (this file).

### NOT touched
- `src/**` — the adapter runtime is correct and proven on real Windows
  (the 3 jest integration tests pass on `windows-latest`). This is a
  test-only fix, per the task.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **337 passed, 3 skipped**
  (no count change — assertion edit only; the 3 skips are the
  Node-dependent jest integration tests).
- `uv run mypy` → **clean** (52 source files, `--strict`).
- Real signal: post-merge GHA — expect **9/9 green**, all 3
  `windows-latest` cells with no failures.

## Worklog entry

Appended to `WORKLOG.md` top — `2026-05-21 — phase2.5 / jest-adapter-unit-test-windows`.

## DoD bullets believed closed

**None.** Test-only defect fix, not a `delivery-phasing.md` DoD bullet.

## Open items / surprises

- Out of scope, NOT bundled (PM tracking separately): the non-fatal
  `UnicodeDecodeError: 'charmap' codec` warning seen in a subprocess
  reader thread on the Windows CI log — jest still passed; a future Run
  robustness slice.
- Low merge-conflict risk — a single assertion block in one test file.
