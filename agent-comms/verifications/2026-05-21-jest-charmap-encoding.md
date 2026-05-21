---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-05-21
slug: jest-charmap-encoding
source-handoffs:
  - handoffs/run-team-2026-05-21-jest-charmap-encoding.md
---

# Verification: jest `charmap` UnicodeDecodeError test-harness fix

## Merged commit

- `310bc87` — `fix(run): pin encoding=utf-8 on CLI test-harness subprocess capture`
- Merged fast-forward onto `main` (was `69c6c74`). No conflict for this slice.

## Source handoff consumed

- `handoffs/run-team-2026-05-21-jest-charmap-encoding.md` (Run team, status `ready`).

## What changed

`encoding="utf-8"` pinned on the two CLI-spawning `subprocess.run(...)` calls
in the integration test harness:

- `tests/integration/cli/conftest.py` — `run_cli` fixture.
- `tests/integration/orchestration/conftest.py` — `run_cli_in` fixture.

Root cause: `text=True` without `encoding=` makes `subprocess` decode the
captured pipes with the *parent*'s locale codec — `cp1252` on a Windows
runner — while the child CLI is forced to UTF-8. UTF-8 box-drawing glyphs in
a Cyclopts `--help` panel then fail to decode -> `UnicodeDecodeError` in
`subprocess`'s reader thread -> `PytestUnhandledThreadExceptionWarning`.

## Verification steps for Manual Test

This is a **Windows-only** defect — it is *not reproducible on Linux/macOS*
(their locale codec is already UTF-8, so the pinned `encoding=` is
byte-identical to the prior implicit default). Local verification can only
confirm no regression; the definitive signal is the post-merge CI run.

1. No-regression check (any OS):
   ```
   uv run pytest -q tests/integration/cli tests/integration/orchestration
   ```
   Expect: all green, **no `PytestUnhandledThreadExceptionWarning`** in the
   output.

2. Full gate sanity:
   ```
   uv run pytest -q tests/unit tests/integration
   ```
   Expect: `337 passed, 3 skipped` (the 3 skips are the Node-dependent jest
   integration tests on a Node-less box).

3. **Definitive signal — post-merge GHA `test` workflow:** inspect any
   `windows-latest` cell's log. Before this fix it carried
   `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90` inside a
   `_readerthread` traceback, surfaced as a `PytestUnhandledThreadExceptionWarning`.
   After this fix that warning must be **absent** from all 3 Windows cells.

## Critical edge cases worth probing

- Confirm the warning is gone specifically around the `test --help` /
  `<subcmd> --help` integration tests — the Cyclopts/rich help panel with
  box-drawing glyphs is the trigger.
- This slice adds **no regression test** (the fix is one kwarg on a pytest
  fixture; a unit test asserting it would be a brittle implementation-detail
  test). The integration suite itself + the Windows CI observation are the
  guard.

## Notes from the merge

- Clean fast-forward, no conflict for this slice.
- Territory note carried from the handoff: the fix touches
  `tests/integration/orchestration/conftest.py`, which is Orchestration's
  test mirror rather than Run's strictly-owned tree. Run applied it directly
  because the task anticipated a test-harness-site fix and conftest files
  are test-infra (no `src/` path). Flagged here for awareness.
- Out of scope (flagged to PM, not touched): `tests/release/test_install_script.py:175`
  carries the same `text=True`-without-`encoding=` pattern but runs on
  POSIX-only Release CI cells — not implicated in the Windows warning.
