---
from: novetest-run-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-06
slug: dotnet-equip-blocker
related:
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - scripts/dev-host-setup.md
  - .claude/settings.json
---

# Question — .NET equip blocker on this checkout's host (§2.5 cannot self-satisfy)

## TL;DR

The .NET adapter hotfix #1 slice's diff matches the
equip-and-exercise §2.5 binding heuristic (modifies both
`src/novetest/run/adapters/dotnet_adapter.py` AND
`tests/integration/run/test_dotnet_coverage.py`). §2.5 binds Run
team's pre-handoff gate to an equipped host with
`dotnet --version >= 8.0` resolvable and 0 skips on
`tests/integration/run/test_dotnet_*.py`.

**This checkout's host (`yjshin@<new-machine>`) is NOT equipped
for .NET:**
- `~/.local/share/novetest-toolchains.sh` — missing
- `~/.dotnet/dotnet` — missing
- `~/.nuget/packages/coverlet.collector` — missing
- `dotnet` — not on PATH

Run team attempted two installation paths and was blocked on both:

1. **`dotnet-install.sh` (the dev-host-setup §6 primary path)** —
   Claude Code auto-mode classifier denied with reason:
   *"Downloading and executing dotnet-install.sh from dot.net — not
   on the Toolchain Bootstrap allowlist and no explicit user
   authorization to install a .NET toolchain."*
   This matches the pattern from JUnit hotfix-3 cycle's
   prior cycle (Maven/Gradle downloads blocked by classifier).

2. **`sudo apt-get install -y dotnet-sdk-8.0` (Ubuntu noble main
   has 8.0.127, matrix-floor-compliant)** — sudo prompted for
   password; this session has no tty for password entry. Even if
   a tty were available, `.claude/settings.json` only pre-authorizes
   `openjdk-17-jdk*` and `maven*` apt installs (set up for the JUnit
   cycle); `dotnet-sdk-8.0` is NOT pre-authorized.

Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
§2.5.3:

> "If Run team's local environment cannot be equipped (license
> restriction, container limitation, missing distro package), the
> work pauses and the team files a `questions/` entry to PM rather
> than handing off an un-exercised diff. PM either dispatches the
> equipping step itself or hands the slice to a host that can equip
> (Manual Test's host is the default fallback)."

This is the formal pause. Run team has shipped the source + test
work locally (1139 passed + 11 skipped + 0 failed on un-equipped
host; mypy strict clean on 91 source files) but has NOT handed off
to Main Branch yet pending PM disposition.

## What is complete

- F1a (pre-restore before probe) — implemented in
  `src/novetest/run/adapters/dotnet_adapter.py`
- F1b (Run-team-scope metadata surface; see companion question
  `envelope-warnings-projection.md` for cross-team disposition)
- F1c (`test_coverage_run_on_fresh_fixture_with_no_prior_restore`
  integration test) — added to
  `tests/integration/run/test_dotnet_coverage.py`; skip-gates on
  `shutil.which("dotnet")`, so it stays no-op on unequipped hosts
- 10 new unit tests (`TestPreRestore` x6, `TestEnvelopeSafetyNet`
  x4) — all green via stubbed subprocess
- Full local suite green (1139+11+0); mypy strict clean

## What is blocked

§2.5 mandate: Run team's pre-handoff gate must show
`uv run pytest -v tests/integration/run/test_dotnet_*.py` →
**N passed, 0 skipped, 0 failed**. On this host:
6 SKIPPED, 0 failed — fails the gate.

The new F1c test specifically pins the D1 reproducer; it is the
most critical assertion in the slice (proves the F1a fix closes
the user-visible defect end-to-end). Without an equipped host
this test cannot execute.

## Options for PM disposition

### Option 1 — CEO authorizes `sudo apt-get install -y dotnet-sdk-8.0` on this host

Add `Bash(sudo apt-get install -y dotnet-sdk-8.0*)` to
`.claude/settings.json::permissions.allow` (mirroring the existing
`openjdk-17-jdk*` and `maven*` entries). Re-dispatch the slice;
Run team installs the SDK + runs the §2.5 gate + writes the
handoff.

Estimated time: ~5 min install + ~30s integration gate + ~10 min
handoff/commit. Single round-trip.

### Option 2 — CEO authorizes `dotnet-install.sh` on this host

Add an authorization to `.claude/settings.json` (or a one-off
permission grant) for the `dotnet-install.sh` user-local path.
This is the dev-host-setup §6 primary recommendation. No sudo
needed. User-local install under `~/.dotnet/`.

Estimated time: same as Option 1.

### Option 3 — Hand off as-is to Manual Test's equipped host

The slice's source + test work is complete and locally green.
Manual Test's host (per `findings/manual-test-team-2026-06-05-...`)
IS equipped (`dotnet 8.0.421`). PM dispatches Manual Test as
"the §2.5 gate runner for this slice" instead of (or in addition
to) the Verdict gate.

Slight policy deviation: §2.5 is Run team's gate; using Manual
Test for it splits responsibility. But §2.5.3 explicitly names
Manual Test as "the default fallback" when Run team can't equip.

### Option 4 — Hand off via the OTHER equipped host (the one used for JUnit + .NET cycles)

`yjshin@<original-machine>` per the original .NET adapter handoff
has the full toolchain (`dotnet 8.0.421` + `coverlet.collector
6.0.2` cached + `~/.local/share/novetest-toolchains.sh` shim).
PM directs Run team to move the worktree branch to that host and
run the §2.5 gate there.

User's recent direct quote ("다른 컴퓨터에서 작업을 이어 하다가
다시 이 컴퓨터로 옮겨왔어") confirms the bouncing between hosts is
ongoing operationally; CEO may want to (re-)pin which host is the
canonical Run-team host for §2.5 purposes.

## Recommended disposition

Run team's recommendation: **Option 1 or 2** — single round-trip,
single host, cleanest §2.5 closure. PM/CEO picks whichever is
easier to authorize.

If Options 1 + 2 are both undesirable, **Option 4** keeps the
slice in Run-team's hands at the cost of host switching.

**Option 3** works but couples Manual Test's verdict role to
Run team's pre-gate role — process-clean but slightly
responsibility-muddling.

## What ships in this commit regardless of PM disposition

- F1a + F1b + F1c source/test changes
- This question doc
- The companion `envelope-warnings-projection.md` question doc
- WORKLOG entry (drafted; PM-disposition-conditional)
- A handoff doc marked **PAUSED — §2.5 gate not satisfied; PM
  disposition required**

The commit is on the worktree branch
(`run-team/dotnet-adapter-hotfix-1`), base `1f9486a`. No Main
Branch FF-merge dispatched until §2.5 is satisfied (by whichever
of the four options above PM chooses).

## Effective date

Filed 2026-06-06 during the dotnet hotfix #1 implementation.
Resolution expected before Main Branch FF-merge.
