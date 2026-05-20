---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-21
slug: jest-adapter-unit-test-windows
related:
  - handoffs/run-team-2026-05-21-jest-adapter-unit-test-windows.md
  - questions/release-team-2026-05-21-jest-adapter-unit-test-windows.md
  - verifications/2026-05-21-restore-windows-jest-ci.md
---

# Verification: make `test_argv_includes_target_expression` OS-aware (no Manual Test action)

Test-only follow-up slice. **No Manual Test verification surface** — one
unit-test assertion edit, no `src/` change. Recorded for PM bookkeeping.

## Merged commit

- `16e4984` — `test(run): make test_argv_includes_target_expression OS-aware`

main HEAD after merge: `16e4984`. Fast-forward, base was current main
(`deb8404`) — no rebase, no conflict.

## Source handoff consumed

- `handoffs/run-team-2026-05-21-jest-adapter-unit-test-windows.md`

## Why this follow-up exists

After `restore-windows-jest-ci` lifted the Windows guard, CI went red on
all 3 `windows-latest` cells (`1 failed, 339 passed`). The lone failure
was a **stale POSIX-only unit test**, not a product defect:
`test_argv_includes_target_expression` pinned `captured_argv[0] ==
<npx>`, but the npx fix (`0e9ab71`) made `run_jest` build argv as
`["cmd", "/c", "npx", "jest", ...]` on Windows — so `argv[0]` is `cmd`
there. The jest adapter runtime itself is correct: the 3 jest
integration tests pass on real `windows-latest`.

## What changed

`tests/unit/run/adapters/test_jest_adapter.py` only (+ WORKLOG.md):
`test_argv_includes_target_expression` dropped its OS-specific
`argv[0]`/`argv[1]` prefix pins and now asserts only its OS-invariant
concern — `"jest"` is in argv, the canonical flags are present, and the
target expression is the last argv element. **No `src/` change** — the
adapter runtime was already correct.

## Verification

- Post-merge full gate: `uv run pytest -q tests/unit tests/integration`
  -> **337 passed, 3 skipped** (no count change — assertion edit only);
  `uv run mypy` -> **clean, 52 source files**.
- The real signal is **GHA observation** — expect **9/9 green**, all 3
  `windows-latest` cells with no failures. This closes the Windows jest
  CI saga (npx adapter fix `0e9ab71` + guard restore + this test fix).

## Manual Test action

**None.** Unit-test assertion edit only; no CLI/envelope/`src` surface.

## Open follow-up (PM tracking, NOT in this slice)

A non-fatal `UnicodeDecodeError: 'charmap' codec` warning was seen in a
subprocess reader thread in the Windows CI log — jest still passed. Run
team flagged it as a future robustness slice; out of scope here.

## Reporting

No findings file required.
