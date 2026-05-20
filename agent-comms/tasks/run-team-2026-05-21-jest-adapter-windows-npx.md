---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-21
slug: jest-adapter-windows-npx
related:
  - questions/release-team-2026-05-20-jest-adapter-windows-npx.md
---

# Task: fix jest adapter `npx` resolution on Windows

## Scope / Mission

The jest adapter is **unrunnable on Windows**: `novetest run` against a
jest project fails with `AdapterInvocationError: npx not found on PATH`
even when Node.js is installed and `npx.cmd` is on PATH. Fix it so jest
runs on `windows-latest`.

This is the tail slice of the 2026-05-20 cycle. CI run `26169544419`
exposed the bug; the `ci-node-win-fallback` slice masked it by disabling
Windows jest in CI (`runner.os != 'Windows'` guard). This task removes
the underlying defect so that guard can be dropped (a companion Release
task PM writes after this lands).

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-run-team.md`
2. `agent-comms/questions/release-team-2026-05-20-jest-adapter-windows-npx.md`
   — Release team's full root-cause analysis (the source of this task)
3. `src/novetest/run/adapters/jest_adapter.py` — `run_jest`, specifically
   the `argv` list (~lines 79-88: `["npx", "jest", "--ci", ...]`) and the
   `FileNotFoundError` -> `AdapterInvocationError(kind="missing-binary")`
   handler (~lines 101-112)
4. `tests/integration/run/test_jest_basic.py` — the
   `_require_node_and_local_jest()` skip guard (uses `shutil.which`)
5. The production jest engine-readiness probe in `src/novetest/run/`
   (it already uses `shutil.which` to detect `node`/`npx` — locate it;
   the readiness layer and the adapter exec must agree)

## Root cause (PINNED — from Release's analysis, verified)

Deterministic on Windows:

- The readiness probe uses `shutil.which("npx")`, which honours
  `PATHEXT` and therefore **finds `npx.cmd`** -> readiness PASSES (the
  skip guard does not skip; the engine is reported ready).
- `run_jest` then execs the **bare name** `"npx"` as `argv[0]` via
  `asyncio.create_subprocess_exec`. Windows `CreateProcess` does **not**
  apply `PATHEXT` to the executable target, so `npx` (no extension) is
  not found -> `FileNotFoundError` -> re-raised as
  `AdapterInvocationError("npx not found on PATH ...", kind="missing-binary")`.

Net effect: with Node.js genuinely installed, jest is unrunnable on
Windows AND the error message is misleading ("not found on PATH" when it
*is* on PATH, just under `npx.cmd`). `node.exe` resolves fine; only the
`npx`/`npm` `.cmd` shims are affected — and the jest adapter only execs
`npx`.

## Files to write / modify

- `src/novetest/run/adapters/jest_adapter.py` — resolve `npx` before
  exec so the guard and the exec are consistent.
- `tests/unit/run/adapters/test_jest_adapter.py` (or the existing jest
  adapter test module) — add coverage for the resolution behaviour.
  You cannot run a real Windows exec on the Linux CI box, but you CAN
  unit-test that `argv[0]` is the resolved path returned by
  `shutil.which` (mock `shutil.which` to return a `.cmd` path and a
  POSIX path; assert the constructed argv in both cases) and that a
  `None` from `shutil.which` raises the typed `missing-binary` error.

## Files NOT to touch

- `.github/workflows/ci.yml` — the `runner.os != 'Windows'` guard
  removal is a SEPARATE companion Release task. PM writes it after this
  slice lands; do not edit any workflow.
- `src/novetest/coverage/**`, `src/novetest/orchestration/**`,
  `src/novetest/cli/**`, `pyproject.toml`, `agent-comms/decisions/**`.

## Fix approach (starting hypothesis — verify before committing)

Release's suggested fix: resolve `npx` to its absolute path via
`shutil.which("npx")` and use that resolved path as `argv[0]` instead of
the bare string `"npx"`. The readiness layer already computes this —
reuse the same resolution so guard and exec never disagree again. When
`shutil.which("npx")` returns `None`, raise the existing
`AdapterInvocationError(kind="missing-binary")` **explicitly** rather
than relying on a downstream `FileNotFoundError`.

**MANDATORY subtlety — verify, do not skip.** `npx.cmd` on Windows is a
**batch script**, not a PE executable. `CreateProcess` /
`asyncio.create_subprocess_exec` may NOT run a `.cmd` directly even when
given its full path — Windows batch files historically require the
command processor (`cmd.exe /c ...`), and recent CPython security
hardening around `.bat`/`.cmd` handling in `subprocess` changed this
behaviour. So passing the resolved `npx.cmd` path may still be
insufficient. **Verify what actually works** — recruit the `debugger`
specialist and/or research current CPython Windows `.cmd` exec
behaviour. If a full path to `npx.cmd` is not directly executable, the
fix likely needs to invoke it through `cmd.exe /c` on Windows
specifically. The acceptance bar is concrete: **jest runs on
`windows-latest`** — choose whatever resolution mechanism makes that
true, and document the chosen mechanism + why in the handoff.

The non-Windows path MUST NOT regress (on POSIX, bare `npx` resolves
fine; using the resolved path uniformly is acceptable as long as POSIX
behaviour is unchanged).

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green (Node-dependent tests still skip cleanly
  on a Node-less box).
- `uv run mypy` — clean.

**Real-world verification note.** CI currently SKIPS Windows jest (the
`ci-node-win-fallback` guard). So this fix, once merged, is NOT yet
exercised on `windows-latest`. The definitive signal comes from the
companion Release task (guard removal) that PM dispatches after your
handoff — the post-guard-removal CI run on `windows-latest` confirms the
fix. In your handoff, state exactly what Windows-side reasoning/research
you did and your confidence level so PM can decide merge ordering.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code. Recruit `debugger` for the `.cmd` exec question.

## Reporting

Write `agent-comms/handoffs/run-team-2026-05-21-jest-adapter-windows-npx.md`.
Append a `WORKLOG.md` entry (touches `src/` + `tests/`), run
`python3 tools/regen_comms_index.py`, stage `WORKLOG.md` + comms +
`INDEX.md` with source.

**DoD bullets believed closed:** none — this is a defect fix, not a
`delivery-phasing.md` DoD bullet. State "none" explicitly.

In the handoff, **confirm the exact fix mechanism** (resolved-path vs
`cmd.exe /c` vs other) so PM can scope the companion Release
guard-removal task precisely.
