---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-03
slug: windows-path-separator-fastfollow
related:
  - agent-comms/handoffs/run-team-2026-07-03-windows-path-separator-fastfollow.md
  - agent-comms/tasks/run-team-2026-07-03-windows-path-separator-fastfollow.md
  - agent-comms/findings/manual-test-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
---

# Verification request: Run FAST-FOLLOW — dotnet glob evidence POSIX separators (Windows CI fix)

## Merged

- **Commits**: `886dc09` (the one-line fix + docstring) + `0168119`
  (WORKLOG correction) + `ccdad1a` (handoff) — pure FF off main `d28012f`.
- **Source handoff**: `run-team-2026-07-03-windows-path-separator-fastfollow.md`.
- **What it fixes**: CI run `28633288553` at batch HEAD `b982fad` was RED on
  the 3 `windows-latest` jobs (py3.11/3.12/3.13) —
  `test_detect_dotnet_one_level_csproj_evidence_is_root_relative` failed
  because `str(match.relative_to(root))` emits `\` on Windows while the
  test (correctly) pins POSIX form. Fix:
  `match.relative_to(root).as_posix()` in
  `src/novetest/run/engine_selector.py::_marker_evidence`. ZERO test
  changes; footprint = 1 source file + WORKLOG + handoff (verified
  name-only).
- **Process note (team-disclosed, verified)**: the team's first instinct
  was amend+force-push on the already-pushed branch; the harness blocked
  it and the correction landed as normal commit `0168119`. No history
  rewrite occurred.

## Gate (on the merged tree, Linux host)

- `env -u PYTHONPATH uv run mypy` → Success, 114 source files.
- `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration`
  (3 jest host-issue deselects) → **1418 passed / 47 snapshots** — count
  unchanged vs batch HEAD, as expected: on POSIX hosts `str()` and
  `.as_posix()` coincide, so the Linux gate CANNOT distinguish pre/post
  fix. **The binding acceptance gate is the post-merge Windows CI matrix.**

## Live smoke (observed on the merged tree)

```python
from pathlib import PureWindowsPath
p = PureWindowsPath("MyLib.Tests") / "MyLib.Tests.csproj"
str(p)         # 'MyLib.Tests\\MyLib.Tests.csproj'  <- the CI-red form
p.as_posix()   # 'MyLib.Tests/MyLib.Tests.csproj'   <- the pinned contract

from novetest.run import detect_engine_candidates
# tmp ws with MyLib/MyLib.csproj + MyLib.Tests/MyLib.Tests.csproj:
# observed candidate: dotnet/xunit,
#   evidence == ('MyLib.Tests/MyLib.Tests.csproj', 'MyLib/MyLib.csproj')
#   (sorted, root-relative, POSIX)
```

## Verification steps for Manual Test

1. **The binding cite**: post-merge CI run on the merge push must be
   **10/10**, with the 3 `windows-latest` jobs explicitly green (they are
   the whole point; ubuntu/macos/perf were already green). Main Branch
   records the run id below; PM cites it at cycle close — closing BOTH
   this fast-follow AND the parent pin-driven-dispatch cycle, unblocking
   Wave 2 (Orchestration anchored-pin).
2. Re-run the finding's repro (dotnet one-level csproj workspace →
   `detect_engine_candidates` / readiness envelope) and confirm evidence
   strings carry `/` — on this host trivially true; the Windows leg rides
   on CI.
3. Spot-check that NO other envelope surface changed: 47 snapshots
   untouched, zero `.ambr` drift.

## Critical edge cases / notes

1. **Out-of-scope kept out (verified)**: the 4 pre-existing
   `str(x.relative_to(y))` sites (`cargo_adapter.py:367`,
   `junit_adapter.py:898`, `dotnet_adapter.py:571`, `dotnet_adapter.py:1233`)
   are untouched per brief — artifact-log keys, green on Windows today.
   Optional hygiene audit = separate conversation.
2. **Gotcha worth codifying (PM)**: `str(Path.relative_to(...))` is a
   Windows-portability trap for any envelope-bound string — `.as_posix()`
   whenever the value leaves the process. Pre-merge Linux gates cannot
   catch it. Manual Test's recommendation #3 (pre-merge `windows-latest`
   spot-run via `workflow_dispatch` when a diff touches
   `relative_to`/`glob`/`os.sep`) was attempted this cycle but hit
   **HTTP 403** — the session gh identity is dispatch-restricted. PM
   decision wanted on who owns pre-merge spot-run rights.
3. The team branch was pushed to origin solely for the (403-blocked)
   spot-run attempt; Main Branch deletes it post-merge as part of cleanup.

## Post-merge CI verdict (the binding cite — recorded by Main Branch)

- **Run `28643184018`** on merge push `12e0d0a`: **conclusion SUCCESS, 10/10 jobs** —
  `test (windows-latest / py3.11)`: success,
  `test (windows-latest / py3.12)`: success,
  `test (windows-latest / py3.13)`: success
  (the 3 jobs red at `b982fad`, run `28633288553`), plus
  ubuntu×3 / macos×3 / perf all success.
- Acceptance criterion "Full CI matrix 10/10 at the merge commit" is MET.
  PM may cite this run id to close the fast-follow AND the parent
  pin-driven-dispatch cycle, unblocking Wave 2.
