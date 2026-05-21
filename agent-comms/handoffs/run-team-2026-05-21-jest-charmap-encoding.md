---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-21
slug: jest-charmap-encoding
related:
  - tasks/run-team-2026-05-21-jest-charmap-encoding.md
  - history/2026-05-21-phase2-3-inspect-and-jest-coverage.md
---

# Handoff: jest `charmap` UnicodeDecodeError on Windows CI — root-caused & fixed

## Worktree

- Path: `../novetest-jest-charmap`
- Branch: `run-team/jest-charmap-encoding`
- Base commit: `69c6c74` (`comms: queue CI-maintenance + jest-charmap tasks`)

## Root cause (definitive)

The warning is **not a jest bug** — the task's jest framing was a red
herring. It is the CLI-integration **test harness** decoding the
`novetest` CLI's own UTF-8 output with the wrong codec on Windows.

Evidence: Windows CI job `76994034094` (run `26172567747`,
`windows-latest / py3.11`) log lines 235-242:

```
PytestUnhandledThreadExceptionWarning: Exception in thread Thread-17 (_readerthread)
Traceback (most recent call last):
  File ".../threading.py", line 982, in run
  File ".../subprocess.py", line 1599, in _readerthread
    buffer.append(fh.read())
  File ".../encodings/cp1252.py", line 23, in decode
    return codecs.charmap_decode(input,self.errors,decoding_table)[0]
UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 297
```

Chain of facts:

1. `_readerthread` at `subprocess.py:1599` is the **stdlib `subprocess`
   module's** pipe-reader thread, used by `Popen.communicate()` in text
   mode on Windows. It is **not** `asyncio` — our `utils/asyncio_subprocess`
   captures raw bytes and never decodes, so it is correctly ruled out
   (matches PM's pre-flight finding).
2. The offending `subprocess` call is in the test harness:
   `tests/integration/cli/conftest.py`'s `run_cli` fixture (and the
   identical `tests/integration/orchestration/conftest.py` `run_cli_in`
   fixture) spawn the `novetest` CLI with
   `subprocess.run(..., capture_output=True, text=True)` and **no**
   `encoding=`.
3. `text=True` without `encoding=` makes `subprocess` decode the captured
   pipes with the **parent**'s `locale.getpreferredencoding()` — `cp1252`
   on a Windows runner, UTF-8 on Linux/macOS. That is why the warning is
   invisible on every non-Windows box.
4. The fixture sets `env["PYTHONIOENCODING"] = "utf-8"`, so the **child**
   CLI emits UTF-8. `novetest <subcmd> --help` renders a Cyclopts/rich
   help panel containing box-drawing glyphs (e.g. `┐` U+2510 → UTF-8
   `e2 94 90`). The parent then tries to decode that UTF-8 as cp1252;
   continuation byte `0x90` is undefined in cp1252 → `UnicodeDecodeError`
   inside the reader thread.
5. `subprocess` swallows the reader-thread exception; pytest's
   `threadexception` plugin records it and reports it at the next test
   boundary as a `PytestUnhandledThreadExceptionWarning` — which is why
   it is *attributed* to `test_test_subcommand_help_exits_zero` (the
   `test --help` test is the trigger; the attribution is approximate).

`PYTHONIOENCODING` was a near-miss: it sets the **child**'s stream
encoding, not how the **parent** decodes the pipe it reads back.

## Fix

Surgical — pinned `encoding="utf-8"` on the two CLI-spawning
`subprocess.run(...)` calls so the parent decodes with the same codec the
child writes. On POSIX this is byte-identical to the prior implicit
default (`locale.getpreferredencoding()` is already UTF-8 there); on
Windows it replaces cp1252 with UTF-8.

## Files modified

- `tests/integration/cli/conftest.py` — `run_cli` fixture: added
  `encoding="utf-8"` + explanatory comment.
- `tests/integration/orchestration/conftest.py` — `run_cli_in` fixture:
  added `encoding="utf-8"` + explanatory comment.
- `WORKLOG.md` — new top entry `phase2.5 / jest-charmap-encoding`.
- `agent-comms/handoffs/run-team-2026-05-21-jest-charmap-encoding.md` (this file).
- `agent-comms/INDEX.md` — regenerated.

## Territory note (for Main Branch / PM)

`tests/integration/cli/` and `tests/integration/orchestration/` are not in
Run Team's explicitly-owned set (Run owns `tests/unit/run/**` and
`tests/integration/run/**`). The fix was applied here directly because:
(a) the task is addressed to Run and PM's hypothesis #3 explicitly
anticipated a "test-harness site" fix by Run; (b) PM's "report, don't fix"
branch is scoped narrowly to `npm`/`node`/`cmd.exe` noise *outside our
control* — a conftest is firmly inside our control; (c) it is a
subprocess-encoding defect, Run's core expertise; (d) these are test-infra
files, not in any forbidden `src/` path. Flagging it so PM is aware the
diff touches Orchestration's test mirror.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **337 passed,
  3 skipped** (3 skips = Node-dependent jest integration tests, expected
  on a Node-less Linux box; no count change vs baseline — the fix is
  byte-identical on POSIX).
- `uv run mypy` → **clean**, `--strict`, 52 source files.
- Definitive signal: the **post-merge `windows-latest` CI run** must show
  the `charmap` / `PytestUnhandledThreadExceptionWarning` is gone. Not
  reproducible on Linux.

## No regression test added — rationale

The fix is one kwarg on a pytest **fixture** in `conftest.py`, not
production code. A unit test asserting "the fixture passes
`encoding='utf-8'` to `subprocess.run`" would be a brittle
implementation-detail test. The real regression guard is the existing
integration suite itself plus the post-merge Windows CI observation.
Pinning a unit test here would violate the task's "surgical, no premature
abstraction" guardrail.

## Open items

- `tests/release/test_install_script.py:175` carries the **same**
  `text=True`-without-`encoding=` pattern, but it runs `sh install.sh` and
  the release tests are POSIX-only CI cells — not implicated in the
  Windows warning, and Release territory. **Not touched.** PM may route a
  trivial hardening follow-up to Release if desired; it is not a live
  defect.

## DoD bullets believed closed

None. This is a robustness defect fix, not a `delivery-phasing.md` DoD
bullet — stated explicitly per the task.

## Worklog entry (pasted)

## 2026-05-21 — phase2.5 / jest-charmap-encoding

- Landed: pinned `encoding="utf-8"` on the CLI-spawning `subprocess.run(...)` calls in `tests/integration/cli/conftest.py` (`run_cli` fixture) and `tests/integration/orchestration/conftest.py` (`run_cli_in` fixture). Root cause of the non-fatal `UnicodeDecodeError: 'charmap' codec` warning seen on `windows-latest` CI: these fixtures spawn the `novetest` CLI with `capture_output=True, text=True` but **no** `encoding=`. `text=True` makes `subprocess` decode the captured pipes with the *parent*'s locale codec — cp1252 on a Windows runner. The child is forced to UTF-8 (`env["PYTHONIOENCODING"]="utf-8"`), so it emits multi-byte UTF-8 (e.g. the box-drawing glyphs in a Cyclopts `--help` panel); cp1252 has no mapping for continuation byte `0x90`, so the decode raises `UnicodeDecodeError` inside `subprocess`'s `_readerthread` (stdlib `subprocess.py:1599`, the `communicate()` reader thread — NOT asyncio). The thread exception is swallowed by `subprocess` and surfaced by pytest's `threadexception` plugin as a `PytestUnhandledThreadExceptionWarning`, attributed to whatever test was at the next boundary (`test_test_subcommand_help_exits_zero`). Not a jest bug at all — the jest framing was a red herring; `npx jest` output is captured as raw bytes by `utils/asyncio_subprocess` and never decoded. `PYTHONIOENCODING` was a near-miss: it governs the *child*'s streams, not how the *parent* decodes the pipe it reads. Pinning the parent's decode to `encoding="utf-8"` matches what the child writes.
- Verified: `uv run pytest -q tests/unit tests/integration` → 337 passed + 3 skipped (the 3 skips are the Node-dependent jest integration tests; no count change — `encoding="utf-8"` is byte-identical to the implicit default on a POSIX dev box where `locale.getpreferredencoding()` is already UTF-8). `uv run mypy` → clean (52 source files, `--strict`). Definitive signal is the post-merge `windows-latest` CI run showing the `charmap` warning gone — not reproducible locally on Linux.
- Left open: **No `delivery-phasing.md` DoD bullet closes** — robustness defect fix, not a DoD bullet. `tests/release/test_install_script.py:175` has the same `text=True`-without-`encoding=` pattern but runs `sh install.sh` on a POSIX-only Release CI cell; not implicated in the Windows warning and Release territory — flagged to PM, not touched.
- Gotcha: the charmap warning is not from our `run_subprocess` helper — that captures raw bytes and never decodes. It is from the *test harness* invoking the CLI via stdlib `subprocess.run(text=True)`. Any `subprocess` text-mode capture must pin `encoding=` explicitly: `text=True` alone decodes with the parent's locale codec (cp1252 on Windows, UTF-8 on Linux/macOS) — so the bug is invisible on every non-Windows box. `PYTHONIOENCODING` in the child env does NOT fix this; it only sets the child's own stream encoding.
- Next: post-merge `windows-latest` CI confirms the warning is gone, closing `history/2026-05-21-phase2-3-inspect-and-jest-coverage.md` "Open follow-ups" #2. If a future test harness or source site captures subprocess output in text mode, pin `encoding="utf-8"` from the start.
</content>
</invoke>
