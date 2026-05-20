---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-21
slug: jest-adapter-windows-npx
verdict: partial
related:
  - verifications/2026-05-21-jest-adapter-windows-npx.md
  - verifications/2026-05-20-ci-node-win-fallback.md
---

# Findings: jest adapter `npx` resolution on Windows

## Verdict: `partial`

- **POSIX path (Linux/macOS)** — confirmed **not regressed**. Verified via
  the merged CLI and the dedicated unit suite.
- **Windows `cmd /c npx` path** — **cannot be verified on a Linux box**.
  Deferred to the Release team's GHA observation once the
  `if: runner.os != 'Windows'` CI guard is dropped.

This `partial` verdict is the expected and sanctioned outcome — the
verification request itself states a Windows-deferred `partial` is
acceptable. No issues filed.

## What was tested (plain-language narrative)

A defect was found in how Nove Test launches jest on **Windows**. On
Windows, `npx` does not exist as a normal program file — it exists only
as `npx.cmd`, a batch script. Windows' low-level process launcher
(`CreateProcess`) will auto-complete a bare name like `npx` to `npx.exe`
but never to `npx.cmd`. So the old code, which checked "is npx
available?" (a check that *does* see `npx.cmd`) and then tried to launch
the bare name `npx`, passed the check but failed at launch. Result: all
three Windows CI cells went red (GHA run 26169544419, `3 failed`).

The fix routes the Windows launch through `cmd.exe` (`cmd /c npx`), which
*does* understand `.cmd` scripts, and leaves the Linux/macOS behaviour
untouched. It also upgrades the "npx not found" failure from a raw
`FileNotFoundError` to a clean, typed `missing-binary` error.

Our job: confirm the Linux/macOS path was not collaterally damaged, and
confirm the new error-handling behaves. The actual Windows fix can only
be proven on a real Windows runner — that is CI's job, not a Linux dev
box's.

## Commands run (verbatim) + observed output

### 1. POSIX behaviour unchanged — jest workspace, no Node.js

This dev box has no `node` on PATH (matching the merge-team box). A plain
`novetest run` against the `jest-basic` fixture short-circuits at the
engine-readiness probe, exactly as in prior cycles — proving the adapter
change did not alter the no-Node path:

```sh
cp -r tests/fixtures/projects/jest-basic/. /tmp/nv-jestnpx/
cd /tmp/nv-jestnpx
novetest init
novetest run .
```

Result: `ok false`, structured envelope (no traceback):
- `engine_readiness.state == "engine-missing"`
- `engine_readiness.issues[0]` = "Node.js (`node`/`npx`) not found on
  PATH; install Node.js >=18 and ensure both `node` and `npx` are on
  PATH"
- error `code == "engine-engine-missing"`

Unchanged from prior cycles. The adapter's new `npx` resolution lives
*downstream* of this readiness gate, so with no Node the gate fires
first — the full jest exec path cannot be reached locally.

### 2. Unit suite — the four `npx`-launcher tests (all PASS)

The Windows-specific logic and the new error path are covered by
dedicated unit tests in `tests/unit/run/adapters/test_jest_adapter.py`.
All four pass on the merged tree:

```
test_unresolvable_npx_raises_typed_error ............... PASSED
test_launcher_exec_failure_falls_back_to_missing_binary  PASSED
test_npx_launcher_posix_uses_resolved_path ............. PASSED
test_npx_launcher_windows_wraps_in_cmd ................. PASSED
```

These map directly onto the verification request's two critical edge
cases:
- **Unresolvable `npx` → typed `missing-binary`** —
  `test_unresolvable_npx_raises_typed_error` confirms a structured typed
  error (not a raw `FileNotFoundError`).
- **POSIX byte-identical launcher** —
  `test_npx_launcher_posix_uses_resolved_path` confirms the POSIX
  launcher resolves to the same absolute `npx` path the old bare-name
  `execvp` would have used.
- `test_npx_launcher_windows_wraps_in_cmd` confirms the Windows launcher
  is `["cmd", "/c", "npx"]` — but this is a unit-level assertion on the
  helper's output, NOT proof that a real Windows runner executes jest
  correctly. That remains a CI signal.

Full jest adapter unit slice: **27 passed**.

### 3. Full test suite gate

`uv run pytest -q tests/unit tests/integration` on merged HEAD `2e81071`:
**337 passed, 3 skipped** in ~20s — an exact match to the figure in the
verification request. The 3 skips are the Node-dependent jest
integration tests (no Node.js on this box). `1 snapshot passed`. This
slice's documented +3 net unit tests are present and green.

## Issues found

None.

## What remains unverified (by design)

The **actual Windows fix** — that `cmd /c npx` successfully launches jest
on a real `windows-latest` runner — is **not** provable on a Linux dev
box. The definitive signal is the CI run that the Release follow-up will
produce once it drops the `if: runner.os != 'Windows'` guard from
`ci.yml` (added by the `ci-node-win-fallback` slice). Until then, the
unit test `test_npx_launcher_windows_wraps_in_cmd` is the only Windows
evidence, and it only checks the helper's *output shape*, not real
process execution.

## Recommendations for PM

1. **Hold this slice's closure on the Release guard-removal CI run.**
   This `partial` can only become a full `passed` once a real
   `windows-latest` CI cell runs the jest integration tests green. Track
   that as the closing condition.
2. **Sequence the guard removal explicitly.** The fix is now on `main`
   (`0e9ab71`), so the Release follow-up to drop `if: runner.os !=
   'Windows'` from `ci.yml` is unblocked. Recommend PM dispatch that
   follow-up task so Windows jest coverage is restored and this slice
   can be verified end-to-end — otherwise the fix ships unproven.
3. **Local Node.js on the Manual Test box** (carried over from this
   cycle's jest-coverage findings) would let Manual Test at least confirm
   the POSIX jest exec path for real, instead of only the readiness-gate
   short-circuit. The Windows leg would still need CI regardless.

## Note on `ci-node-win-fallback` verification (no Manual Test surface)

`verifications/2026-05-20-ci-node-win-fallback.md` explicitly states that
slice (commit `c350e5c`, `ci.yml` only — adds the
`if: runner.os != 'Windows'` guard) has **no Manual Test action**. We
acknowledge it here: nothing was run for it; no separate findings file is
required, per that request. It is the temporary mitigation that this
`jest-adapter-windows-npx` fix now makes removable — see recommendation 2.
