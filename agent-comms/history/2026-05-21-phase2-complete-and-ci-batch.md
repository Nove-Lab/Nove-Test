---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-21
slug: phase2-complete-and-ci-batch
---

# History: Phase 2 complete (DoD #4) + CI Node-24 maintenance + the charmap red herring

The 2026-05-21 cycle dispatched 3 parallel slices. All three merged and
passed Manual Test. Headline: **Phase 2 is now 4/4 — complete.**

## Cycle summary

| Slice | Commit | Outcome |
|---|---|---|
| Coverage: NFR-COV-002 50k-location perf benchmark | `5489c7e` | passed — **Phase 2 DoD #4** |
| Release: GHA actions → Node 24 runtime majors (Slice A) | `57cdf0d` | passed — CI 9/9 green, zero deprecation warnings |
| Run: jest `charmap` UnicodeDecodeError fix | `310bc87` | passed — Windows CI cells clean |

Post-merge CI run `26209355947` (commit `7fb7366`): **9/9 cells green**,
no deprecation warnings, all 3 Windows cells free of the `charmap` /
`PytestUnhandledThreadExceptionWarning`.

## What closed

- **Phase 2 DoD #4** (NFR-COV-002 50k-location perf) — `5489c7e`. The
  benchmark times the real `compare_coverage_facts` at exactly 50,000
  covered locations/side; Manual Test observed median **0.024s** vs the
  5.0s NFR ceiling (~125x headroom, no `src/` optimization needed).
  **Phase 2 (Coverage Structuring) is now 4/4 — fully complete.** Next
  phase is Phase 3 (Regression Comparison).
- The `history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`
  "Open follow-ups" #2 (jest charmap warning) — root-caused and fixed.

## Load-bearing learnings

### 1. `subprocess` text-mode capture decodes with the PARENT's locale codec

The `charmap` `UnicodeDecodeError` on Windows CI was **not a jest bug** —
the jest framing was a red herring. Root cause: the CLI-integration test
harness (`tests/integration/cli/conftest.py`, `.../orchestration/conftest.py`)
spawned the `novetest` CLI with `subprocess.run(..., capture_output=True,
text=True)` and **no `encoding=`**. `text=True` without `encoding=` makes
`subprocess` decode the captured pipes with the **parent**'s
`locale.getpreferredencoding()` — `cp1252` on a Windows runner, UTF-8 on
Linux/macOS. The child CLI emits UTF-8 (forced via `PYTHONIOENCODING`,
and `--help` panels carry box-drawing glyphs); cp1252 cannot decode the
continuation bytes → `UnicodeDecodeError` in `subprocess`'s stdlib
`_readerthread`, surfaced by pytest's `threadexception` plugin.

**Rules for future agents:**
- Any `subprocess` text-mode capture MUST pin `encoding="utf-8"`
  explicitly. `text=True` alone is a latent bug invisible on every
  non-Windows box.
- `PYTHONIOENCODING` in the **child** env does NOT fix this — it sets the
  child's own stream encoding, not how the parent decodes the pipe.
- This is distinct from `utils/asyncio_subprocess.run_subprocess`, which
  captures **raw bytes** and never decodes — it is correctly immune.

### 2. A "merged" cycle is not closeable until the batch is PUSHED

Main Branch merged all 3 worktrees into **local** `main` and wrote
verifications, and Manual Test passed all 3 — but the batch was never
pushed to `origin`. CI runs `on: push`, so no CI run existed. Two of the
three findings explicitly named the post-merge GHA run as the
*definitive* signal; that signal cannot exist until the push. PM caught
local `main` 7 commits ahead of `origin/main` during cleanup pre-flight.
**Lesson: after a merge batch, confirm `git log origin/main..main` is
empty before treating CI-dependent findings as confirmable. The push is
a required step between merge and cycle-close.**

### 3. Pin task numbers consistently

The coverage-perf task pinned "exactly 50,000 covered locations" AND a
literal file-index delta (`0-399 common / 400-449 removed / 450-499
added`) that arithmetically yields only 45,000. The team reconciled it
via the task's own "~50k" latitude (500-file fact sets, `file_offset=50`
→ 450 common / 50 removed / 50 added, each side exactly 50,000). When a
task pins a headline number AND a worked example, the example must
satisfy the number — PM task-writers should arithmetic-check both.

## CI maintenance notes (Release territory)

- All GHA `uses:` pins are now on **Node 24 runtime majors**
  (`checkout@v6`, `setup-node@v6`, `setup-uv@v7`, `upload-artifact@v7`,
  `download-artifact@v8`, `action-gh-release@v3`); `dtolnay/rust-toolchain@stable`
  is a composite action with no JS runtime — left unchanged. This clears
  the 2026-06-02 Node 20 runtime retirement ahead of the deadline.
- `setup-uv@v7` recognizes the `python-version` input (`setup-uv@v3` did
  not — it triggered the `Unexpected input(s)` warning); the 3x3 matrix
  is kept with no separate `setup-python` step.

## Open follow-ups (PM queue)

1. **ci-perf-lane task is queued** — `tasks/release-team-2026-05-21-ci-perf-lane.md`
   (pending, awaiting CEO dispatch). Re-dispatches the deferred Slice B
   (non-blocking `tests/perf` CI lane — `tests/perf/` is now on `main`)
   and folds in a one-kwarg `encoding="utf-8"` hardening for the same
   latent pattern at `tests/release/test_install_script.py` (~line 175),
   flagged by both the Run handoff and Manual Test.
2. **`windows-latest` runner redirect** — CI run `26209355947` carried a
   GitHub infra NOTICE: `windows-latest` requests redirect to
   `windows-2025-vs2026` by **2026-06-15**. Informational, not a
   deprecation; no action needed now. A future Release slice may pin the
   Windows runner image explicitly if the redirect changes behaviour.

## Process notes

- Clean 3-slice cycle, no tail sprawl (contrast the prior cycle's 5→9
  slice Windows-defect chase). All defects were caught pre-merge or by
  the first post-merge CI run.
- The charmap fix touched `tests/integration/orchestration/conftest.py`
  (Orchestration's test mirror) from a Run-team task. Justified and
  flagged in the handoff: it is test-infra, the defect is Run's core
  subprocess-encoding expertise, and PM's hypothesis #3 anticipated a
  test-harness fix. Not a territory violation — but a reminder that
  conftest fixtures are shared infra that any team may need to touch.
