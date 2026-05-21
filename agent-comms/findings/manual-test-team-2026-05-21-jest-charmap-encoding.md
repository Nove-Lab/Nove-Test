---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
created: 2026-05-21
slug: jest-charmap-encoding
verifies: verifications/2026-05-21-jest-charmap-encoding.md
verdict: passed
---

# Findings: jest `charmap` UnicodeDecodeError test-harness fix

## Verdict: passed (local no-regression confirmed; Windows CI signal pending)

## What was tested (plain language for the CEO)

On Windows CI runners, our test harness was emitting a noisy (non-fatal)
`UnicodeDecodeError: 'charmap' codec` warning. The cause: when a test launches
the `novetest` CLI as a subprocess and captures its output, Python decodes
that output using the *parent's* system encoding — which on Windows is the
legacy `cp1252` codec, not UTF-8. The CLI itself emits UTF-8 text (including
the box-drawing characters in a `--help` panel), so `cp1252` choked on it. The
Run team fixed it by explicitly pinning `encoding="utf-8"` on the two
output-capturing calls in the test harness, so the parent decodes exactly what
the child writes.

This is a **Windows-only** defect — it cannot be reproduced on Linux or macOS,
because their system encoding is already UTF-8 (so the pinned `encoding=` is
byte-identical to the prior default). Local verification can therefore only
confirm "no regression": the change must not break the integration suite. It
does not — the affected suites pass cleanly, including with warnings promoted
to hard errors. The definitive confirmation that the original warning is gone
can only come from a post-merge Windows CI run, which Manual Test cannot
observe.

## Commands run + observed output

1. **No-regression check on the affected suites** —
   `uv run pytest -q tests/integration/cli tests/integration/orchestration`:
   ```
   44 passed in 11.12s
   ```
   Run with `-W error::Warning` (every warning promoted to a hard failure) —
   still **44 passed**. No `PytestUnhandledThreadExceptionWarning`, no
   `UnicodeDecodeError`. A separate `-rw` warnings-summary scan returned
   nothing.

2. **Full gate sanity** — `uv run pytest -q tests/unit tests/integration`:
   ```
   337 passed, 3 skipped in 12.82s
   ```
   Matches the expected baseline exactly. (The 3 skips are the Node-dependent
   jest integration tests, expected on this Node-less box.)

3. **Type-check sanity** — `uv run mypy` → `Success: no issues found in 52
   source files` (the fix is a test-harness `conftest.py` kwarg; no `src/`
   change).

## Issues found

**None.** The fix is a one-keyword addition to two pytest fixtures; it
introduces no regression on this platform and the affected `--help`-panel
integration tests pass cleanly even under `-W error`.

## Recommendations for PM

- **Tick the jest-charmap-encoding slice as verified-passed** for the
  locally-checkable scope (no regression on Linux/macOS).
- **Definitive signal still pending — Windows CI.** The verification request
  is explicit that the original `UnicodeDecodeError: 'charmap' codec can't
  decode byte 0x90` warning is only observable on a `windows-latest` runner.
  PM (or CI-access holder) should inspect a post-merge Windows cell log for
  commits `310bc87`/`ec5c891` and confirm the
  `PytestUnhandledThreadExceptionWarning` is **absent** from all 3 Windows
  cells before fully closing. This also closes follow-up #2 of
  `history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`.
- **No DoD bullet closes** — this is a robustness/test-harness defect fix, not
  a `delivery-phasing.md` deliverable.
- **Pre-existing follow-up worth tracking:** the merge note (and the Run team
  handoff) flag that `tests/release/test_install_script.py:175` carries the
  same `text=True`-without-`encoding=` pattern. It runs only on POSIX Release
  CI cells so it is not implicated in the Windows warning, but it is the same
  latent bug — consider a small Release task to pin `encoding="utf-8"` there
  too, pre-emptively.
