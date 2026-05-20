---
from: novetest-release-team
to: novetest-pm-team
type: question
status: open
created: 2026-05-21
slug: jest-adapter-unit-test-windows
related:
  - handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md
  - handoffs/release-team-2026-05-21-restore-windows-jest-ci.md
---

# Run-team unit test `test_argv_includes_target_expression` is POSIX-only — fails on `windows-latest`

## Context

The `restore-windows-jest-ci` slice lifted the temporary
`runner.os != 'Windows'` guard so jest runs on all 9 CI cells. CI run
**26172964986** (origin/main `3f30aae`) result:

| Cells | Result |
|---|---|
| 6× Linux + macOS | green |
| 3× `windows-latest` | **red** — `1 failed, 339 passed` |

**The restore itself succeeded.** Before this slice the Windows cells
reported `336 passed, 3 skipped` (jest integration tests skipped); now
`339 passed` with no skips — the 3 jest integration tests **run and pass**
on `windows-latest` via the `cmd /c npx` adapter path. The Run npx fix
(`0e9ab71`) is verified end-to-end on a real Windows runner.

## The lone remaining failure — a Run-team unit test, not a CI-config bug

```
FAILED tests/unit/run/adapters/test_jest_adapter.py::test_argv_includes_target_expression
  - AssertionError: assert 'cmd' == '/usr/bin/npx'
tests\unit\run\adapters\test_jest_adapter.py:253: AssertionError
```

The Run npx fix made `run_jest` build the argv as `["cmd", "/c", "npx",
"jest", ...]` on Windows (and `["/usr/bin/npx", "jest", ...]` on POSIX).
But the unit test `test_argv_includes_target_expression` still asserts the
first argv element equals `/usr/bin/npx` unconditionally — a POSIX-only
assumption. On Windows `argv[0]` is now `cmd`, so the test fails.

The adapter *runtime* fix is correct and proven; only its companion
*unit test* was not updated to be OS-aware when the `cmd /c` branch was
added. This is in Run-team territory:
`tests/unit/run/adapters/test_jest_adapter.py` — Release team cannot
touch `tests/**`.

## Secondary observation (lower priority, also Run-team)

The same Windows job log shows a non-fatal warning:

```
PytestUnhandledThreadExceptionWarning: Exception in thread Thread-17 (_readerthread)
  UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 297
```

A subprocess reader thread decoded jest output with the Windows default
`charmap` codec instead of UTF-8. It is currently only a *warning* (jest
still passed), but it suggests the adapter's subprocess stream reading
should pin `encoding="utf-8"` on Windows to be safe. Worth Run team
assessing alongside the unit-test fix.

## Ask for PM

Route to Run team:
1. **(blocking — CI is red)** Make `test_argv_includes_target_expression`
   OS-aware: assert the `cmd /c` prefix on Windows and the resolved `npx`
   path on POSIX (or assert on the tail of argv, which is OS-invariant).
2. **(non-blocking)** Assess pinning `encoding="utf-8"` on the adapter's
   Windows subprocess stream reading to remove the `charmap`
   `UnicodeDecodeError` warning.

## Release-team position

Release team will NOT re-add the `runner.os != 'Windows'` guard — that
would mask a now-passing integration suite to hide an unrelated unit-test
defect. The restore slice stays as merged. Once Run team fixes the unit
test, CI goes 9/9 green with jest a real gate on every cell. Tracked in
handoff `release-team-2026-05-21-restore-windows-jest-ci.md`.
