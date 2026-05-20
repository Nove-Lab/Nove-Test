---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-21
slug: jest-adapter-unit-test-windows
related:
  - questions/release-team-2026-05-21-jest-adapter-unit-test-windows.md
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
---

# Task: make `test_argv_includes_target_expression` OS-aware (CI red on Windows)

## Scope / Mission

CI is **red on all 3 `windows-latest` cells** — `1 failed, 339 passed`.
The lone failure is a stale POSIX-only unit test left behind by the npx
fix (`0e9ab71`). Fix it so CI goes **9/9 green**.

This is the final step of the 2026-05-20 cycle. The jest runtime is
proven good: the 3 jest *integration* tests now run and pass on real
`windows-latest` runners. Only one *unit* test carries a hardcoded POSIX
assumption.

## The failure (pinned)

```
FAILED tests/unit/run/adapters/test_jest_adapter.py::test_argv_includes_target_expression
  - AssertionError: assert 'cmd' == '/usr/bin/npx'
  tests\unit\run\adapters\test_jest_adapter.py:253
```

The npx fix made `run_jest` build argv per-OS via `_npx_launcher`:
- **POSIX:** `[<resolved abs path to npx>, "jest", ...]`
- **Windows:** `["cmd", "/c", "npx", "jest", ...]`

`test_argv_includes_target_expression` still asserts the first argv
element equals `/usr/bin/npx` unconditionally. When the test *runs on a
Windows runner*, `argv[0]` is `cmd`, so it fails. The test was not made
OS-aware when the `cmd /c` branch was added. It was already red on
`windows-latest` from the moment `0e9ab71` merged (CI run `26172567747`)
— the `ci-node-win-fallback` guard never gated it (the guard only gated
the Node-dependent *integration* tests; this unit test needs no Node).

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-run-team.md`
2. `agent-comms/questions/release-team-2026-05-21-jest-adapter-unit-test-windows.md`
3. `src/novetest/run/adapters/jest_adapter.py` — `_npx_launcher`
   (~lines 223-246) and how `run_jest` assembles `argv`
4. `tests/unit/run/adapters/test_jest_adapter.py` — the failing test
   `test_argv_includes_target_expression` (~line 253), and the existing
   per-OS launcher tests `test_npx_launcher_posix_uses_resolved_path` +
   `test_npx_launcher_windows_wraps_in_cmd` you added in the npx slice

## Files to write / modify

- `tests/unit/run/adapters/test_jest_adapter.py` — make
  `test_argv_includes_target_expression` OS-aware. Scan the whole file
  for any other test carrying the same POSIX-only `argv[0]` /
  `/usr/bin/npx` assumption and fix those too, so this does not recur on
  the next Windows CI run.

## Files NOT to touch

- `src/**` — the adapter runtime is correct and proven on real Windows;
  this task is a TEST-only fix. Do not change `jest_adapter.py`.
- `.github/workflows/**`, `pyproject.toml`, `agent-comms/decisions/**`.

## Fix approach

`test_argv_includes_target_expression` exists to verify the **target
expression is appended to argv** — that concern is OS-invariant. Assert
on the OS-invariant part: e.g. that the target expression is the last
argv element, and/or that `"jest"` is present in argv — rather than
pinning `argv[0]`. The per-OS launcher *prefix* is already covered
separately by `test_npx_launcher_posix_uses_resolved_path` and
`test_npx_launcher_windows_wraps_in_cmd`, so this test should NOT
re-assert the prefix. If you do need to assert the prefix anywhere,
branch on the OS the same way `_npx_launcher` does.

The test must pass whether collected on a POSIX or a Windows runner
(it picks up the actual runner OS unless it stubs it).

## Out of scope — tracked separately, do NOT bundle

The Windows CI log also shows a non-fatal `UnicodeDecodeError: 'charmap'
codec` warning in a subprocess reader thread (jest still passed). That is
a real but **non-blocking** robustness item; PM is tracking it as a
separate future Run slice. Do NOT pull it into this task — this task's
sole job is to turn CI 9/9 green with a minimal test-only change.

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green on this (POSIX) box.
- `uv run mypy` — clean.
- Real signal: post-merge GHA — expect **9/9 green**, all 3
  `windows-latest` cells at `337 passed` (or equivalent, no failures).

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
editing the test.

## Reporting

Write `agent-comms/handoffs/run-team-2026-05-21-jest-adapter-unit-test-windows.md`.
This slice touches `tests/` -> append a `WORKLOG.md` entry. Run
`python3 tools/regen_comms_index.py`, stage `WORKLOG.md` + comms +
`INDEX.md` with the test change.

**DoD bullets believed closed:** none — defect fix, not a
`delivery-phasing.md` DoD bullet. State "none" explicitly.
