---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-04
slug: windows-dotdotdot-normalization-fastfollow
related:
  - agent-comms/tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md
  - agent-comms/questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md
  - agent-comms/handoffs/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md
---

# Handoff: Orchestration — FAST-FOLLOW: Windows mangles go's `./...` (lexical all-dots guard)

**Merge-gate fix.** Unblocks the anchored-pin wave-2 cycle close (CI 7/10 at
`7ddfc0f`, dispatch run `28671731628`: windows-latest ×3 red on exactly one
test). Merge ASAP; precedent: the 2026-07-03 windows-path-separator
fast-follow.

## Worktree

- **Path**: `/home/yjshin/dev/Nove-Test/.claude/worktrees/agent-ab6b45d42ee6bcf7e`
- **Branch**: `worktree-agent-ab6b45d42ee6bcf7e` (harness-managed isolated worktree)
- **Base**: `04a41ac` (main tip + wave-2 comms)
- **Commit**: `4505162` — `orchestration: lexical all-dots guard in normalize_target_expression (Windows CI fix)` (+ a `comms:` follow-up carrying this handoff + INDEX)
- **Status**: ready — NOT self-merged, NOT pushed.

## Files written / modified

| File | Change |
|---|---|
| `src/novetest/orchestration/anchor_resolution.py` | THE fix: NEW private helper `_has_all_dots_component(candidate)` (any `Path.parts` component consisting solely of dots, `..` excluded — genuine parent navigation; `.` never survives `Path` parsing) + one new `elif` branch in `normalize_target_expression` short-circuiting to verbatim pass-through BEFORE the `(anchor / candidate).exists()` probe. Docstring gains a bullet pinning the lexical rule + Win32 rationale. Nothing else in the module touched (walk-up/pin logic untouched per brief §Out of scope). |
| `tests/unit/orchestration/test_anchor_resolution.py` | +2 tests beside the existing contract test: `test_normalize_all_dots_component_never_probes_filesystem` (recording `Path.exists` spy; probe list must stay EMPTY across `./...` / `...` / `./sub/...` — the POSIX-observable regression pin the brief asks for) and `test_normalize_parent_component_still_probes` (`..` must NOT trigger the guard; the exists-probe path is unchanged). |
| `WORKLOG.md` | New top entry |
| `agent-comms/handoffs/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md` | This file |
| `agent-comms/INDEX.md` | Regenerated |

**The existing contract test is UNCHANGED** —
`test_normalize_engine_native_pattern_passes_through` already pins the D3
contract; the implementation violated it on Windows. Expected post-merge: the
3 `windows-latest` jobs flip red→green on that exact test.

## Root cause (verified against source, matches Main Branch triage)

Win32 strips trailing dots from path components, so `ws\...` resolves to `ws`
itself → `(anchor / '...').exists()` returns **True** → the existing-subpath
branch computed `to_workspace_relative_posix(anchor / '...', anchor)` = `'...'`
— go's `./...` mangled, wrong baseline series identity for any Windows user
passing an all-dots target. The pure-lexical guard removes the Win32-quirk
dependency entirely (the brief's preferred shape over post-probe detection):
for all-dots components the filesystem is now never consulted on ANY platform.

## Verification

All `env -u PYTHONPATH`:

1. `uv run mypy` (exact CI gate, strict) → **Success: no issues found in 116 source files**.
2. `uv run pytest -q tests/unit/orchestration/test_anchor_resolution.py` → **28 passed** (26 pre-existing incl. the CI-red contract test + 2 new).
3. `uv run pytest -q tests/unit tests/integration` → **1504 passed / 13 skipped / 1 failed, 49 snapshots passed**. The 1 failure is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral…` — `dotnet` absent from this host's PATH (chronic host-equip miss documented in the last three WORKLOG entries; `which dotnet` → not found). Count math reconciles with your equipped-host gate at `76a4ffb` (1511/5/0 = 1516 collected): 1516 + 2 new = 1518 = 1504+13+1 here. **Zero `.ambr` drift** → "no behavior change for genuine existing-subpath targets / snapshots unchanged" acceptance criterion holds.
4. **Pre-fix A/B proof** (production change stashed, tests kept): the new spy test FAILS on POSIX with all three all-dots probes recorded (`[…/ws/'...', …/ws/'...', …/ws/sub/'...'] != []`) while the contract test stays green on POSIX — the "unobservable on POSIX by construction" gap from your kick-back is now observable on every platform.

## Envelope-schema implications

None. No envelope, exit-code, or renderer change; the fix only affects which
branch computes the (string) target expression for a niche input class that
was previously mangled on Windows only. `schema: novetest/v1` untouched.

## DoD bullets believed closed (PM verifies and ticks)

1. `test_normalize_engine_native_pattern_passes_through` green on windows-latest ×3; full matrix 10/10 → **post-merge dispatch; PM cites run id** (dispatch did NOT 403 this cycle per the kick-back §For the record). ⏳
2. New POSIX-observable regression test merged (probe never consulted for all-dots components) → verification #2/#4. ✅
3. No behavior change for genuine existing-subpath targets (snapshots unchanged) → verification #3 (zero `.ambr` drift) + the `..`-guard-narrowness test. ✅
4. WORKLOG entry + this handoff → ✅. Origin kick-back question retired at cycle close → PM. ⏳

## Open items / surprises

- First draft of the regression test used a raising bomb on `Path.exists`;
  that INTERNALERRORs pytest itself when the test fails (pytest's report and
  tmpdir machinery also call `Path.exists`). Redesigned as a recording spy —
  fails cleanly pre-fix. Worth remembering for any future "never touches the
  filesystem" pin (WORKLOG Gotcha carries it).
- karpathy-guidelines Skill mandate: no Skill tool in this session's toolset
  (4th documented occurrence); principles applied manually. No deliverable
  impact.

## Merge notes for Main Branch

- Cherry-pick / FF the two commits (`4505162` fix + the comms follow-up); one
  production module + its unit-test mirror + WORKLOG/comms. Zero overlap with
  any in-flight worktree (Manual Test's three 2026-07-04 findings files are
  untracked in the shared checkout, not this worktree's concern).
- Pre-merge gate: `env -u PYTHONPATH uv run pytest -q tests/unit/orchestration/test_anchor_resolution.py` (28) + `env -u PYTHONPATH uv run mypy` (Success, 116).
- Post-merge: `gh workflow run ci.yml --ref main` → confirm **10/10** with the
  3 `windows-latest` jobs named in the verification request; that cite closes
  this fast-follow AND the parent anchored-pin wave-2 cycle, and lifts Manual
  Test's KNOWN-RED caveat on `./...` pass-through scenarios.
