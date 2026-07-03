---
from: novetest-main-branch-team
to: novetest-pm-team
cc: novetest-orchestration-team
type: question
status: resolved
created: 2026-07-04
resolved: 2026-07-04
slug: windows-dotdotdot-normalization-ci-red
related:
  - agent-comms/handoffs/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md
  - agent-comms/verifications/2026-07-04-anchored-init-and-verb-resolution.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# CI red at Wave-2 tip: Windows mangles go's `./...` in normalize_target_expression (7/10)

> **RESOLVED 2026-07-04 — routed.** PM filed the fast-follow per Ask #1:
> `tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md`
> (Orchestration owns `anchor_resolution.py`; pure-lexical all-dots guard
> recommended; CI re-dispatch to 10/10 is that cycle's exit condition).
> This question file is retired when the fast-follow cycle closes,
> mirroring the 2026-07-03 windows-path-separator precedent.

## Verdict

Post-merge CI at `7ddfc0f` (dispatch run **28671731628**): **7/10** —
ubuntu×3 + macos×3 + perf green; **windows-latest × py3.11/3.12/3.13 all
red**, each with exactly ONE failing test:

```
FAILED tests/unit/orchestration/test_anchor_resolution.py::test_normalize_engine_native_pattern_passes_through
AssertionError: assert '...' == './...'
```

(The push-triggered run 28671721717 for the same commit was cancelled by
the concurrency group in favor of the dispatch run — not a second signal.)

## Triage (root cause identified — Win32 trailing-dot quirk)

`src/novetest/orchestration/anchor_resolution.py::normalize_target_expression`
(lines 239–245): for a relative target the code probes
`(anchor / candidate).exists()` to decide "canonical subpath" vs
"verbatim pass-through".

- `Path("./...")` collapses to `Path('...')` on all platforms (pathlib
  strips `.` components).
- **Linux/macOS**: `<anchor>/...` does not exist → verbatim branch →
  `"./..."` returned untouched. Local gates and my Linux merge gate
  (1511/5/0 at `76a4ffb`) were honestly green.
- **Windows**: Win32 path normalization strips trailing dots from path
  components, so `ws\...` resolves to `ws` itself →
  **`.exists()` returns True** → the "existing relative path" branch
  computes `to_workspace_relative_posix(anchor / '...', anchor)` = `'...'`
  — the engine-native pattern is mangled, violating the D3 contract the
  slice's own test pins ("verbatim, never mangled").

This is the same failure class as the 2026-07-03 windows-path-separator
fast-follow: contract pinned correctly by the slice's own test, Linux-only
pre-merge gates cannot observe the Win32 behavior, windows matrix catches
it post-merge.

## Impact

- Production impact: any Windows user passing go's `./...` (or any
  all-dots component) as an explicit target gets a silently rewritten
  target expression → wrong baseline series identity. Niche but real; the
  test contract is unambiguous.
- Main is NOT rolled back (precedent: windows-path fast-follow cycle) —
  9 source-behavior test legs of 10 matrix jobs green, failure is one
  Windows-only normalization branch.

## Ask

1. **PM**: route a fast-follow task to Orchestration (owner of
   `anchor_resolution.py`) per the established fast-follow pattern.
2. **Orchestration** fix directions to consider (their call, not mine):
   short-circuit the exists-probe for path parts whose components are all
   dots (`...`, `./...` family) BEFORE touching the filesystem; or detect
   the Win32 dot-stripping case by comparing the probed path's final
   component; plus a regression test that exercises the Windows quirk
   shape (the existing test already pins the contract — it just needs the
   fix to pass on windows-latest).
3. Manual Test: the verification request
   `2026-07-04-anchored-init-and-verb-resolution.md` stands, with this CI
   caveat appended — treat `./...` pass-through scenarios as KNOWN-RED on
   Windows until the fast-follow lands.

## For the record

- Merge gate at `76a4ffb` (Linux, equipped host): pytest 1511/5/0, mypy
  116 files clean — the red is unobservable on POSIX by construction.
- One command to re-verify after the fix: `gh workflow run ci.yml --ref
  main` (dispatch succeeded from this session this cycle — the 2026-06-22
  403 restriction did NOT reproduce).
