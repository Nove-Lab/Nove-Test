---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-21
slug: jest-charmap-encoding
related:
  - history/2026-05-21-phase2-3-inspect-and-jest-coverage.md
---

# Task: diagnose & resolve the jest `charmap` UnicodeDecodeError on Windows CI

This is a **diagnose-first** task with a deliberately low ceiling. The
acceptable outcome may be a small code fix **or** a documented "this is
third-party log noise, no source change" finding. Do not force a code
change if the root cause is not in our source.

## Why this task exists

During the 2026-05-20/05-21 jest cycle, the post-merge GitHub Actions run
on a real `windows-latest` runner surfaced a **non-fatal**
`UnicodeDecodeError: 'charmap' codec` warning, observed (per
`WORKLOG.md`'s 2026-05-21 `jest-adapter-unit-test-windows` entry) "in a
subprocess reader thread on the Windows CI log". **jest still passed** —
the warning did not fail any test or gate CI. It is logged here as a Run
robustness follow-up (`history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`,
"Open follow-ups" #2).

`charmap` is the codec name for Windows' legacy locale code page
(typically cp1252). A `charmap` `UnicodeDecodeError` means **something
opened a stream/file in text mode using the OS-locale default codec
instead of UTF-8**, and hit a byte that codec cannot decode.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-run-team.md`
2. `WORKLOG.md` — the 2026-05-21 `jest-adapter-unit-test-windows` and
   `jest-adapter-windows-npx` entries (the `cmd /c npx` Windows launch
   path is the relevant context)
3. `src/novetest/run/adapters/jest_adapter.py`
4. `src/novetest/utils/asyncio_subprocess.py`
5. `src/novetest/run/readiness.py`

## PM's pre-flight finding (read before you start)

PM already scanned the obvious sites. **Every `read_text(...)` call in
`src/novetest/run/` already pins `encoding="utf-8"` explicitly** — the
jest adapter's report read, its `node_modules/jest/package.json` version
read, and `readiness.py`'s `package.json` / `pyproject.toml` reads. And
`utils/asyncio_subprocess.py` captures stdout/stderr as **raw bytes**
(`proc.stdout.read()`), never decoding. So the `charmap` site is **not**
an obvious source-file text read.

That makes three hypotheses worth checking, roughly in order:

1. **It is not our code at all** — `npm install` (the CI fixture-install
   step) or `npx` / `node` / `cmd.exe` itself emitting the warning into
   the CI log. If so, the fix is *not* a source change — it is either a
   CI-env fix (out of your scope — report it to PM for a Release task) or
   a documented "won't fix, third-party noise" finding.
2. **A non-`run/` source site** decodes with the locale default — e.g.
   anywhere a subprocess result, artifact, or log file is later re-read
   in text mode without `encoding=`, or `subprocess`/`asyncio` is used
   with `text=True`/`encoding=` unset elsewhere in `src/`.
3. **A test-harness / fixture site** reads jest output text-mode without
   `encoding=`.

## Mission

1. **Root-cause it.** Use the Windows CI run logs as the primary
   evidence — find which step/thread emits the `charmap` traceback and
   what file/stream it was decoding. (You may need to read recent
   `windows-latest` CI logs via `gh run view` / the Actions UI.)
2. **Then, depending on the root cause:**
   - **If it is our source code:** apply the surgical fix — pin
     `encoding="utf-8"` on the offending read, or set the subprocess
     child env / `PYTHONUTF8` / `PYTHONIOENCODING` if it is our subprocess
     invocation that inherits a non-UTF-8 locale. Add or adjust a unit
     test that pins the intent (an OS-invariant assertion — see WORKLOG's
     lesson #4 about OS-aware tests).
   - **If it is `npm`/`node`/`cmd.exe` log noise outside our control:**
     do NOT change source. Write the diagnosis as the handoff's finding
     and recommend either a Release CI-env follow-up or "accept as benign
     noise". PM routes from there.

## Scope guardrails

- Surgical changes only. This is a non-fatal warning — do not refactor
  the subprocess helper or the adapter around it.
- Do NOT touch `pyproject.toml` (Run/Release shared, but not needed here)
  or `.github/workflows/**` (Release territory — if the fix is CI-env,
  report it, do not edit the workflow).
- POSIX behaviour must be byte-identical after this task.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before any
code change.

## Verification

- If a source fix lands: `uv run pytest -q tests/unit tests/integration`
  green, `uv run mypy` clean. The definitive signal is the **post-merge
  `windows-latest` CI run showing the `charmap` warning is gone**.
- If no source change: no verification commands — the handoff is a
  written diagnosis only.

## Reporting

Write `agent-comms/handoffs/run-team-2026-05-21-jest-charmap-encoding.md`.

- **If you changed `src/` or `tests/`:** append a `WORKLOG.md` entry per
  its format, run `python3 tools/regen_comms_index.py`, stage `WORKLOG.md`
  + the new `agent-comms/` files + `INDEX.md` alongside source.
- **If you changed nothing (diagnosis-only):** no `WORKLOG.md` entry; the
  handoff carries the full root-cause analysis and a routing
  recommendation for PM. Still run `regen_comms_index.py`.

**DoD bullets believed closed:** none — this is a robustness defect fix,
not a `delivery-phasing.md` DoD bullet. State that explicitly. Report the
root cause you found, definitively, in the handoff.
