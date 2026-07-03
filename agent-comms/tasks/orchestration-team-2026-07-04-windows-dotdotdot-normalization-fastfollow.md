---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-07-04
slug: windows-dotdotdot-normalization-fastfollow
related:
  - agent-comms/questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Task: Orchestration — fast-follow: Windows mangles go's `./...` in `normalize_target_expression`

- **Owner**: novetest-orchestration-team (owner of `anchor_resolution.py`)
- **Origin**: Main Branch kick-back at wave-2 tip — CI dispatch run
  `28671731628` at `7ddfc0f`: 7/10, windows×3 red on exactly ONE test.
- **Pattern precedent**: the 2026-07-03 windows-path-separator fast-follow
  (same failure class: contract pinned by the slice's own test, Linux-only
  pre-merge gates can't observe Win32 behavior, windows matrix catches it
  post-merge). Main is NOT rolled back.

## The bug (already triaged by Main Branch — verify, then fix)

`src/novetest/orchestration/anchor_resolution.py::normalize_target_expression`
(lines 239–245): a relative target is probed with
`(anchor / candidate).exists()` to choose "canonical subpath" vs "verbatim
pass-through". Win32 strips trailing dots from path components, so
`ws\...` resolves to `ws` itself → `.exists()` returns True → the
existing-subpath branch rewrites go's `./...` to `...`, violating the D3
contract ("engine-native patterns pass through verbatim, never mangled")
pinned by
`tests/unit/orchestration/test_anchor_resolution.py::test_normalize_engine_native_pattern_passes_through`.

Production impact: a Windows user passing `./...` (or any all-dots
component) gets a silently rewritten target expression → wrong baseline
series identity.

## In scope

1. Fix `normalize_target_expression` so engine-native all-dots components
   never reach the filesystem probe. Recommended shape (your call):
   short-circuit to verbatim pass-through when any path component consists
   solely of dots (`...`, `./...` family) BEFORE calling `.exists()`.
   A pure-lexical guard also removes the Win32-quirk dependency entirely —
   prefer that over detecting the quirk after the probe.
2. Regression test exercising the Windows quirk *shape* so the fix is
   observable on POSIX too (e.g. assert the probe is never consulted for
   all-dots components), in addition to the existing contract test going
   green on windows-latest.
3. Post-merge: dispatch CI (`gh workflow run ci.yml --ref main` — the
   2026-06-22 403 did not reproduce this cycle) and record the 10/10
   verdict per the fast-follow precedent.

## Out of scope

Any other `anchor_resolution.py` behavior; the walk-up/pin logic (green
everywhere); revisiting D3 semantics.

## Acceptance criteria

- `test_normalize_engine_native_pattern_passes_through` green on
  windows-latest ×3 (py3.11/3.12/3.13); full matrix 10/10.
- New POSIX-observable regression test merged.
- No behavior change for genuine existing-subpath targets (snapshots
  unchanged).
- `WORKLOG.md` entry; handoff per fast-follow precedent; the origin
  kick-back question
  (`main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md`)
  is retired at this cycle's close.

## Effort estimate (PM's read)

~10 LOC production, ~40 LOC tests. Fast-follow-sized; single short cycle.
