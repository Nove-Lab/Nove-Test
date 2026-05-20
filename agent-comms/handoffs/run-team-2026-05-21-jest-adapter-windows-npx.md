---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-21
slug: jest-adapter-windows-npx
related:
  - tasks/run-team-2026-05-21-jest-adapter-windows-npx.md
  - questions/release-team-2026-05-20-jest-adapter-windows-npx.md
---

# Handoff: fix jest adapter `npx` resolution on Windows

## Summary

The jest adapter was unrunnable on `windows-latest`: `run_jest` exec'd the
bare name `"npx"`, and Windows `CreateProcess` only appends `.exe` (never
`.cmd`/`.bat`) to a bare name — so `npx` (which exists only as `npx.cmd`)
was not found, even with Node.js installed. Fixed.

## Worktree

- **Path:** `/home/yjshin/dev/novetest-jest-windows-npx`
- **Branch:** `worktree-run-team-jest-adapter-windows-npx`
- **Base commit:** `ab1ef44` (main)

## Files written / modified

### Modified
- `src/novetest/run/adapters/jest_adapter.py` — `run_jest` resolves `npx`
  via `shutil.which("npx")` up front (`None` → explicit typed
  `missing-binary` error); new pure helper `_npx_launcher(npx_path, *,
  windows)` builds the launcher prefix; the `except FileNotFoundError`
  handler kept as a narrow fallback with an updated message.
- `tests/unit/run/adapters/test_jest_adapter.py` — `_stub_npx_on_path`
  autouse fixture (stubs `shutil.which` so the up-front resolution
  succeeds on a Node-less box); `test_argv_includes_target_expression`
  updated; old `test_missing_npx_binary_raises_typed_error` split into
  `test_unresolvable_npx_raises_typed_error` +
  `test_launcher_exec_failure_falls_back_to_missing_binary`; new
  `test_npx_launcher_posix_uses_resolved_path` +
  `test_npx_launcher_windows_wraps_in_cmd`.

## Exact fix mechanism (for PM — scopes the companion Release task)

- **POSIX:** unchanged behaviour. Launcher = `[<resolved abs path to npx>]`,
  exec'd directly. (Previously the bare name `"npx"`; `execvp` resolved it
  to the same file, so this is functionally identical.)
- **Windows:** launcher = `["cmd", "/c", "npx"]`. The `.cmd` batch shim is
  run **through `cmd.exe`** — NOT exec'd directly. This is mandatory:
  `CreateProcess` (what `asyncio.create_subprocess_exec` uses) cannot
  execute `.cmd`/`.bat` files at all (raises `WinError 193`); only
  `cmd.exe` interprets batch files. The **bare** name `npx` is handed to
  `cmd` (not the resolved `.cmd` path) so `cmd`'s `PATHEXT` resolution
  applies and `cmd /c`'s leading-quote-stripping rule is sidestepped.

So: the companion Release task can drop the `runner.os != 'Windows'`
guard in `ci.yml` — jest on Windows now invokes `cmd /c npx jest ...`.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **337 passed, 3 skipped**
  (the 3 skips are the Node-dependent jest integration tests; +3 net unit
  tests from this slice).
- `uv run mypy` → **clean** (52 source files, `--strict`).
- **NOT verified on a real `windows-latest` box.** CI currently skips
  Windows jest (the `ci-node-win-fallback` guard). The definitive signal
  is the post-guard-removal CI run from the companion Release task.

## Confidence

**High.** The fix rests on two long-standing, documented Windows facts:
(1) `CreateProcess` cannot launch batch files — only `cmd.exe` interprets
them; (2) `cmd /c` strips the leading+trailing quote of the whole line
when the first token is quoted, so a bare first token is required. No
live `windows-latest` run was possible from this Linux dev box; that
verification is intentionally gated behind the Release guard-removal task.

## Worklog entry

Appended to `WORKLOG.md` top — `2026-05-21 — phase2.5 / jest-adapter-windows-npx`.

## DoD bullets believed closed

**None.** This is a defect fix, not a `delivery-phasing.md` DoD bullet.

## Open items / surprises

- Merge ordering: this slice should merge **before** the companion
  Release guard-removal task, so the guard is only dropped once the
  adapter fix is on `main`.
- No `src/` files outside `run/adapters/jest_adapter.py` touched;
  `readiness.py` already used `shutil.which` and needs no change (the
  adapter now matches its resolution).
