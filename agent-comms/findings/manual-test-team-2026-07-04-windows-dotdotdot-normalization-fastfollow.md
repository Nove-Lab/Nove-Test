---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: resolved
created: 2026-07-04
slug: windows-dotdotdot-normalization-fastfollow
related:
  - agent-comms/verifications/2026-07-04-windows-dotdotdot-normalization-fastfollow.md
  - agent-comms/tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md
  - agent-comms/questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md
---

# Findings: Windows `./...` normalization fast-follow — KNOWN-RED caveat lifted

## Verdict: **passed**

Verified on merged main at `31db7e8` (fix commit `fdf44d7`), POSIX host
(WSL2), all commands `env -u PYTHONPATH` per GOTCHAS. Every behavioral pin
in the verification request held; zero issues found. The KNOWN-RED caveat
from our 2026-07-04 anchored-init findings (`./...` pass-through mangled on
Windows) is confirmed lifted from the POSIX side; the Windows side is
covered by CI dispatch run `28675082033` (10/10, windows-latest ×3 flipped
red → green on the previously-failing contract test) — merge-side evidence,
not re-run here.

## What was tested (narrative for the CEO)

Go developers say "run everything" with the target `./...` — three literal
dots. That is *pattern syntax* for the go toolchain, not a folder name. Last
cycle we found that on Windows, Nove Test mistook `./...` for a real folder
(a Windows quirk makes "does this path exist?" answer *yes* for names made
of dots) and silently rewrote the user's request to `...` — corrupting the
identity under which run history is filed, so later comparisons would look
at the wrong series. The fix teaches the normalizer to recognize all-dots
names *by spelling alone* and pass them through untouched, without ever
asking the filesystem — which removes the Windows quirk from the equation
on every platform at once.

I verified four things on the merged code: (1) the three regression tests
that pin this behavior pass, including a "spy" test proving the filesystem
is never consulted for all-dots targets; (2) calling the normalizer
directly, `./...`-family targets come back byte-for-byte untouched while
ordinary paths still get cleaned up; (3) driving the real `novetest` CLI on
a Python fixture project, a `./...` target is recorded verbatim in the run
record, and a normal `./tests` target is still canonicalized to `tests`;
(4) the fix did not over-reach — `..` ("go up one folder"), which also
consists of dots but is real navigation, still takes the normal path-check
route.

## Commands run (verbatim) + observed output

### 1. Regression pins (the heart of the slice)

```sh
env -u PYTHONPATH uv run pytest -q \
  "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_all_dots_component_never_probes_filesystem" \
  "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_parent_component_still_probes" \
  "tests/unit/orchestration/test_anchor_resolution.py::test_normalize_engine_native_pattern_passes_through"
```
→ **3 passed**.

```sh
env -u PYTHONPATH uv run pytest -q tests/unit/orchestration/test_anchor_resolution.py
```
→ **28 passed** (matches the merge gate exactly).

### 2. Direct guard observation (verification step 2, output byte-identical to the request's pin)

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

### 3. Edge-case probes (scripted, temp anchor with real `tests/` and `sub/` dirs)

A recording `Path.exists` spy (same technique as the new unit test) around
direct `normalize_target_expression` calls:

- `./tests` → `'tests'`; `./tests/test_x.py::test_a` → `'tests/test_x.py::test_a'`
  (existing-subpath canonicalization + node-id reattachment unchanged);
- `../ghost.py` → `'../ghost.py'` with **1 filesystem probe consulted** —
  the guard does NOT swallow `..` parent navigation (no over-broadening);
- `./...`, `...`, `./sub/...`, `....`, `a/.../b` → all verbatim with
  **0 filesystem probes**, even though a real `sub/` directory existed on
  disk next to the anchor (the lexical guard wins before any existence
  temptation).

### 4. Real-CLI behavior (pytest-workspace probe; `go` absent on this host — see Host limits)

Fixture `tests/fixtures/projects/pytest-basic` copied to
`tests/manual-test-workspace/win-dots-probe` (scratch, cleaned up after):

```sh
env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest init
```
→ exit 0, `data.pinned_engine = {"ecosystem": "python", "engine_name": "pytest"}`, store ready.

```sh
env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest run ./...
```
→ exit 0, `ok: true`, **`data.memory_entry.run_record.target_expression = './...'` verbatim**,
`summary_counts = {'collected': 0, 'total': 0}`, `status: passed` — the
documented zero-collected caveat (pytest has no `./...` semantics; the
verbatim hand-off to the native engine is exactly the D3 contract).

```sh
env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest run ./tests
```
→ exit 0, **`target_expression = 'tests'`** (canonicalization live and
unchanged), `summary_counts = {'collected': 3, 'passed': 3, 'total': 3}`.

```sh
env -u PYTHONPATH /home/yjshin/dev/Nove-Test/.venv/bin/novetest run "./tests/test_math_utils.py::test_add_zero"
```
→ **`target_expression = 'tests/test_math_utils.py::test_add_zero'`** —
path half canonicalized (`./` stripped), node half reattached, 1/1 passed.
A node-id on a *nonexistent* file (`./tests/test_calculator.py::test_add`)
passed through verbatim with 0 collected — the documented
"not-yet-existing paths pass through untouched" rule, not a defect.

### 5. Regression sweep (orchestration-scoped)

```sh
env -u PYTHONPATH uv run pytest -q tests/unit/orchestration tests/integration/orchestration tests/integration/test_anchored_pin_e2e.py
```
→ **246 passed, 3 snapshots passed**. `git status --porcelain` clean after
scratch cleanup — zero `.ambr` drift, zero source modification.

## Host limits (documented honestly)

- `command -v go` → not found; `command -v dotnet` → not found. The gotest
  end-to-end leg (init a gotest fixture, `novetest run ./...` under a real
  go toolchain) was NOT exercisable here — same limit the merge host
  reported. Evidence stack for that leg: the POSIX-observable spy test
  (probe list stays empty), the verbatim CLI recording above (engine-
  independent normalization seam), and CI run `28675082033` 10/10 with
  windows-latest ×3 green on `test_normalize_engine_native_pattern_passes_through`.
- Windows behavior is CI-verified only, per the verification request's own
  guidance — the Win32 trailing-dot quirk is not reproducible on WSL2/POSIX
  by design; the spy test is the cross-platform proxy.

## Issues found

None.

## Recommendations for PM

1. Close the fast-follow cycle: verdict passed, no follow-up tasks needed
   on the guard itself.
2. The KNOWN-RED caveat on `./...` pass-through scenarios (our
   2026-07-04 anchored-init findings) can be formally retired at cycle
   close alongside the origin kick-back question.
3. Standing item, unchanged priority: host re-equip (`go`, `dotnet`) per
   `scripts/dev-host-setup.md` would let both merge gate and Manual Test
   exercise the go/dotnet adapters end-to-end instead of leaning on CI —
   third consecutive cycle where both toolchains were absent locally.

## Harness note

`Write` was blocked by the worktree-isolation handshake (GOTCHAS.md entry
1); used the sanctioned Bash heredoc fallback. No deliverable impact.
