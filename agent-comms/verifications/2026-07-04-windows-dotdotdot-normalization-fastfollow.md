---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-04
slug: windows-dotdotdot-normalization-fastfollow
related:
  - agent-comms/handoffs/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md
  - agent-comms/tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md
  - agent-comms/questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md
---

# Verify: Windows `./...` normalization fast-follow — KNOWN-RED caveat LIFTED

## Merged commits

- **`fdf44d7`** — `orchestration: lexical all-dots guard in normalize_target_expression (Windows CI fix)` (the fix + 2 regression tests)
- **`0ccfe12`** — comms follow-up (handoff + INDEX); **main tip for this verification**

Source handoff consumed:
`agent-comms/handoffs/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md`
(worktree `worktree-agent-ab6b45d42ee6bcf7e`, base `04a41ac`).

Merge notes: clean rebase onto `1f85ee9` (docs-only divergence, zero
conflicts, zero file overlap) then fast-forward. No conflict resolution
performed; the diff on main is byte-identical to the handoff's.

## Merge gate (this host, POSIX, at the rebased tip = merged tree)

All `env -u PYTHONPATH`:

- `uv run pytest -q tests/unit/orchestration/test_anchor_resolution.py` → **28 passed**
- `uv run mypy` → **Success: no issues found in 116 source files**
- `uv run pytest -q tests/unit tests/integration` → **1504 passed / 13 skipped / 1 failed, 49 snapshots passed**. The 1 failure is the chronic `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral…` dotnet-absent host miss (pre-existing, `which dotnet` → not found; matches the handoff's own numbers exactly). Zero `.ambr` drift.

## CI verdict — 10/10, windows legs flipped red → green

Dispatch run **28675082033** at `0ccfe12`: **SUCCESS, 10/10**.
Per-leg: test (ubuntu-latest / py3.11, py3.12, py3.13) green ×3; test
(macos-latest / py3.11, py3.12, py3.13) green ×3; **test (windows-latest /
py3.11, py3.12, py3.13) green ×3** (all red at `7ddfc0f`, run `28671731628`,
on `test_normalize_engine_native_pattern_passes_through`); perf green.
(The push-triggered run `28675077872` was cancelled by the concurrency
group in favor of the dispatch run — not a second signal.)

**This lifts the KNOWN-RED caveat** on `./...` pass-through scenarios
(Ask #3 of the retired kick-back question; the caveat text lived in the
wave-2 verification `2026-07-04-anchored-init-and-verb-resolution.md`,
retired at cycle close — full text preserved at commit `d84edce`).

## What changed (scope for Manual Test)

`normalize_target_expression` now decides **lexically, never probing the
filesystem**, that a relative target with an all-dots component (go's
`./...` wildcard family: `...`, `./...`, `./sub/...`) passes through
verbatim. Previously Win32 trailing-dot stripping made
`(anchor / '...').exists()` answer True on Windows, rewriting `./...` to
`...` → wrong baseline series identity. `..` (genuine parent navigation)
is explicitly NOT swallowed by the guard; existing-subpath
canonicalization is unchanged. No envelope, exit-code, or schema change.

## Verification steps (all `env -u PYTHONPATH`, repo root)

1. **Regression pins (POSIX-observable — the heart of this slice):**

   ```sh
   env -u PYTHONPATH uv run pytest -q \
     "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_all_dots_component_never_probes_filesystem" \
     "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_parent_component_still_probes" \
     "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_engine_native_pattern_passes_through"
   ```

   Observed on merged main: **3 passed**. The first test spies on
   `Path.exists` and asserts the probe list stays EMPTY for `./...` /
   `...` / `./sub/...` — if the guard regresses, it fails on every
   platform, not just Windows.

2. **Direct guard observation** (observed output on merged main,
   copy-paste verbatim):

   ```sh
   env -u PYTHONPATH .venv/bin/python -c "
   from pathlib import Path
   from novetest.orchestration.anchor_resolution import normalize_target_expression
   for t in ('./...', '...', './sub/...', 'tests/test_x.py::test_a'):
       print(repr(t), '->', repr(normalize_target_expression(t, Path('/tmp'))))
   "
   ```

   ```
   './...' -> './...'
   '...' -> '...'
   './sub/...' -> './sub/...'
   'tests/test_x.py::test_a' -> 'tests/test_x.py::test_a'
   ```

3. **Real-CLI `./...` run on the gotest fixture — ONLY if `go` is on
   your host's PATH** (`which go` first). Merge host limit, documented
   honestly: this host has NO `go` (and no `dotnet`), so I could NOT
   exercise the go adapter end-to-end; the pins above + the 3 green
   windows CI legs are the merge-side evidence. If your host has go:

   ```sh
   cp -r tests/fixtures/projects/gotest-basic /tmp/nt-godots && cd /tmp/nt-godots
   env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest init
   env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest run ./...
   ```

   Expect `init` → `data.pinned_engine` = `{"ecosystem": "go",
   "engine_name": "go-test"}` (pair pinned from
   `src/novetest/run/engine_selector.py::_ENGINE_MARKER_TABLE`) and the
   run envelope to carry the target VERBATIM at
   **`data.memory_entry.run_record.target_expression` = `"./..."`**.
   (Envelope path pinned by a real run on the merged code — pytest-basic
   fixture, `novetest run ./tests` → observed
   `data.memory_entry.run_record.target_expression = 'tests'`; that same
   run also re-confirms existing-subpath canonicalization `./tests` →
   `tests` is unchanged.)

## Critical edge cases worth probing

- `..`-containing targets (e.g. `../ghost.py`) must still take the
  probe path — pinned by `test_normalize_parent_component_still_probes`;
  verify no behavioral drift if you script around it.
- Node-id form on an existing path (`tests/test_x.py::test_a`) —
  normalization of the path half, node half reattached (step 2 output).
- Existing-subpath canonicalization unchanged: `./tests` → `tests`
  (one baseline series per ask) — observed live in step 3's pin.
- Windows-side behavior is CI-verified only (3 windows-latest legs);
  no Windows host is available to Manual Test locally — do not burn time
  trying to reproduce the Win32 quirk on WSL2/POSIX, the spy test is the
  POSIX-observable proxy by design.

## Not obvious during merge

- Zero conflicts, zero snapshot drift; gate numbers reconcile with the
  handoff exactly (1516 collected pre-slice + 2 new = 1518 = 1504+13+1
  on this dotnet-less host).
- Harness note: `Write` was blocked by the worktree-isolation handshake
  (GOTCHAS.md entry 1 — this session is pinned to the wave3-doc-pass
  worktree, wrong branch for this file); used the sanctioned Bash
  heredoc fallback. No deliverable impact.
