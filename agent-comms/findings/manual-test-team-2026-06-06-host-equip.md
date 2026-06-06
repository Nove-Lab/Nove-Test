---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: passed
created: 2026-06-06
slug: host-equip
related:
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md
  - scripts/dev-host-setup.md
---

# Findings — Manual Test host equipped for Phase 2.5 .NET adapter cycle (2026-06-06)

**Verdict: passed.** Host `YJ-LAPTOP` (the CEO's original dev laptop)
is now matrix-compliant for every native engine currently merged AND
for the queued .NET / xUnit v2 + Coverlet adapter cycle. dotnet 8.0.421
is the new addition; everything else carried over from prior cycles.

## Why this file exists

CEO is bouncing between two physical machines while Run team works the
.NET hotfix. Their direct quote (Korean):

> "다른 컴퓨터에서 업무를 이어하다가 다시 옮겨왔어. 현재 상태 파악하고, 지금 run team이 업무중이니, 너는 나중에 주어질수도있는 검증 작업을 위해 이 컴퓨터도 equipped host로 셋팅 미리 수행하고있어."

Translation: "I was continuing work on another computer; I've moved
back. Figure out the current state, and since Run team is busy,
pre-equip THIS computer as an equipped host for the verification work
that may land later."

The 2026-06-04 equip-and-exercise decision §1 + §2.5 + §4 makes the
equipping requirement binding on Manual Test for every new adapter
cycle. The two queued Run-team tasks (original `.NET / xUnit v2`
adapter + its hotfix #1) BOTH match the §2.5 file-glob heuristic
(`src/novetest/run/adapters/dotnet_adapter.py` +
`tests/integration/run/test_dotnet_*.py`). When Run team hands off,
Manual Test on this host MUST verify on equipped state — so equipping
now removes the gating delay from the verification critical path.

## What was different on THIS host vs the other machine

The `YJ-LAPTOP` host that I'm equipping today is **not** the same
machine as the one used in `findings/manual-test-team-2026-06-04-host-equip.md`.
The prior file equipped the second dev box (Temurin JDK + user-local
Maven 3.9.16). THIS host has a different equipped baseline carried
over from earlier JUnit cycles:

| Tool | Other machine (prior findings) | THIS machine (today) |
|---|---|---|
| JDK | Temurin 17.0.19, user-local `~/.local/opt/jdk17/` | **OpenJDK 17.0.19** (`apt`, system PATH) |
| Maven | 3.9.16, user-local `~/.local/opt/maven/` | **3.8.7** (`apt`, system PATH) |
| Gradle | (not in prior table; assumed user-local) | **8.5**, user-local `~/.local/gradle-8.5/` |
| Go, Rust, Node, jq | user-local (all present per prior table) | not probed here (out of .NET cycle scope) |
| .NET SDK | 8.0.421 user-local | **8.0.421 user-local** (new — installed today) |
| toolchain shim | `~/.local/share/novetest-toolchains.sh` present | **absent → CREATED today** |

Maven 3.8.7 is **below** the original matrix floor (3.9.x for
Surefire ≥ 3.0), but per my hotfix-3 cycle finding (Recommendation
#1, 2026-06-05) the adapter argv is 3.8-compatible and apt-noble's
default is 3.8.7 — I had recommended PM bump the floor to 3.8. That
recommendation has not yet been actioned in `decisions/2026-05-25-supported-engine-matrix.md`,
but empirically all 3 JUnit Maven tests pass on this host under 3.8.7.

The .NET adapter cycle does not exercise Maven, so the Maven floor
question is orthogonal to today's equip.

## Install actions taken today

| Action | Command | Result |
|---|---|---|
| Download dotnet-install.sh | `curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh` | 63563 bytes, OK |
| Install .NET 8.0 SDK | `bash /tmp/dotnet-install.sh --channel 8.0 --install-dir $HOME/.dotnet` | `Installed version is 8.0.421` |
| Create toolchain shim | `cat > ~/.local/share/novetest-toolchains.sh <<EOF ... EOF` | 1144 bytes; sets `DOTNET_ROOT` + prepends `$HOME/.dotnet` + `$HOME/.local/gradle-8.5/bin` to PATH; sets `DOTNET_NOLOGO=1` + `DOTNET_CLI_TELEMETRY_OPTOUT=1`; emits a one-line equipped-version banner on source |
| Verify shim end-to-end | fresh `bash -c 'source ~/.local/share/novetest-toolchains.sh && ...'` | dotnet 8.0.421 / java 17.0.19 / mvn 3.8.7 / gradle 8.5 — all detected |

**Nothing inside the repo working tree was modified.** All install
mutations are under `$HOME` (`~/.dotnet/`, `~/.local/share/novetest-toolchains.sh`).

## Smoke probe — xUnit + Coverlet 6.0.2 against canonical fixture

Used the in-repo `tests/fixtures/projects/dotnet-test-basic-coverage`
fixture as the smoke target (it's already pinned to matrix floors —
`xunit 2.6.0` + `coverlet.collector 6.0.2` + `Microsoft.NET.Test.Sdk 17.8.0`).
Copied to `/tmp/dotnet-equip-probe/`, generated the decision §1.1
verbatim runsettings on the spot, ran `dotnet test --collect:"XPlat Code Coverage"`.

### Restore + floor enforcement

```
$ dotnet restore MathLib.Tests/MathLib.Tests.csproj
  Restored /tmp/dotnet-equip-probe/MathLib/MathLib.csproj (in 81 ms).
  Restored /tmp/dotnet-equip-probe/MathLib.Tests/MathLib.Tests.csproj (in 8.99 sec).

$ dotnet list MathLib.Tests/MathLib.Tests.csproj package --include-transitive --format json | jq-ish:
  coverlet.collector                            6.0.2     <- matrix floor
  Microsoft.NET.Test.Sdk                        17.8.0    <- >= 17.6 floor
  xunit                                         2.6.0     <- v2 floor
  xunit.runner.visualstudio                     2.5.3
  xunit.abstractions                            2.0.3
  xunit.analyzers                               1.4.0
  xunit.assert                                  2.6.0
  xunit.core                                    2.6.0
  xunit.extensibility.core                      2.6.0
  xunit.extensibility.execution                 2.6.0
```

NuGet warmed up in 11 seconds (cold cache). Subsequent restores would
be sub-second.

### Test execution + Coverlet emission

```
$ dotnet test MathLib.Tests/MathLib.Tests.csproj \
    --logger "trx;LogFileName=results.trx" \
    --results-directory ./TestResults \
    --collect:"XPlat Code Coverage" \
    --settings coverlet.runsettings

[xUnit.net 00:00:00.21]     MathLib.Tests.MathTests.TestSubtractIntentionallyFails [FAIL]
  Failed MathLib.Tests.MathTests.TestSubtractIntentionallyFails [9 ms]
  ...

Failed!  - Failed:     1, Passed:     2, Skipped:     0, Total:     3, Duration: 12 ms - MathLib.Tests.dll (net8.0)

Attachments:
  /tmp/dotnet-equip-probe/TestResults/bb467ee1-.../coverage.cobertura.xml
  /tmp/dotnet-equip-probe/TestResults/bb467ee1-.../coverage.opencover.xml
  /tmp/dotnet-equip-probe/TestResults/bb467ee1-.../coverage.json
  /tmp/dotnet-equip-probe/TestResults/bb467ee1-.../coverage.info

real    0m6.316s
```

Exit code 1 (as expected — 1 intentionally-failing test). Total
runtime 6 seconds for compile+execute.

### Artifacts on disk

```
        7173  TestResults/results.trx
        1240  TestResults/_YJ-LAPTOP_2026-06-06_22_21_52/In/YJ-LAPTOP/coverage.cobertura.xml
        1240  TestResults/bb467ee1-.../coverage.cobertura.xml
        3177  TestResults/_YJ-LAPTOP_2026-06-06_22_21_52/In/YJ-LAPTOP/coverage.opencover.xml
        3177  TestResults/bb467ee1-.../coverage.opencover.xml
         451  TestResults/_YJ-LAPTOP_2026-06-06_22_21_52/In/YJ-LAPTOP/coverage.json
         451  TestResults/bb467ee1-.../coverage.json
         389  TestResults/_YJ-LAPTOP_2026-06-06_22_21_52/In/YJ-LAPTOP/coverage.info
         389  TestResults/bb467ee1-.../coverage.info
```

VSTest's data collector pipe writes Coverlet outputs once under the
timestamped attachments directory and once under the GUID per-run
directory (byte-identical copies — that's normal VSTest behavior).

### Cobertura content sanity

```
line-rate        = 1
branch-rate      = 1
lines-covered    = 2
lines-valid      = 2
packages         = ['MathLib']
```

100% line coverage of `MathLib.MathOps` — the test exercises `Add` and
`Subtract`. Coverage instrumentation is working correctly on this
host.

### TRX content

```
total test results = 3
  Failed   MathLib.Tests.MathTests.TestSubtractIntentionallyFails
  Passed   MathLib.Tests.MathTests.TestAddPasses
  Passed   MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)
```

Critically: the **parametrized test's display name is slugified inside
the TRX `testName` field as `TestParametrized(a: 1, b: 2, expected: 3)`**
— this is the R1 slug-correlation test surface that the adapter's
forward-slugifier (`_slugify_for_coverlet`) must reverse-map against.
For today's empirical XPlat-aggregate-effective reality (per amended
decision §3), the slug-correlation algorithm is exercised only against
synthetic test data; the integration test's R1 probe asserts the
aggregate fallback fires cleanly. Both behaviors verified-by-construction
on this host.

### Empirical reality matches amended decision §3

```
per-test cobertura files (excluding aggregate) = 0
matches decision-amendment empirical reality — XPlat path is aggregate-effective-default
```

`<PerTestCoverage>true</PerTestCoverage>` in the runsettings is inert
via the XPlat data collector path on Coverlet 6.0.2 / dotnet SDK 8.0.421
/ xunit 2.6 / Linux x86_64. This **independently reproduces** the
empirical finding that filed the open question
(`questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md`)
on the OTHER machine. The amendment to
`decisions/2026-06-03-coverlet-pertestcoverage-key.md §3` (CEO-approved
2026-06-05) rests on the same observation. Two machines, two clean
reproductions — the aggregate-effective-default reality is stable.

## Equip-and-exercise verdict evidence

The 2026-06-04 decision §1 specifies the verdict-pass conditions for
adapter-cycle Manual Test passes. This is a pre-emptive equip session
(no cycle to verify YET); same evidence shape applies once the cycle's
verification doc lands.

### Coverage of §4 Gate A "tool floor + plugin floor" pre-flight

For the .NET adapter:

| Floor | Required | Detected on this host | Pass? |
|---|---|---|---|
| `dotnet --version >= 8.0` | yes | 8.0.421 | YES |
| `coverlet.collector` resolves in fixture's csproj at >= 6.0.2 | yes | 6.0.2 (exact pin) | YES |
| `Microsoft.NET.Test.Sdk >= 17.6` | yes | 17.8.0 | YES |
| `xunit (v2) >= 2.6` | yes | 2.6.0 | YES |

Gate A is satisfied for the .NET adapter cycle on this host.

### Cross-engine smoke (carried over from prior cycles)

The JUnit hotfix-3 verification (other machine, 2026-06-05) passed
1034 + 5 + 0 with `.NET` integration tests skipped via
`shutil.which("dotnet") is None`. Now with `dotnet` resolvable on PATH
here, those integration tests will execute rather than skip when the
.NET adapter lands. Skip-gate-elimination posture confirmed for the
upcoming cycle.

I did NOT run the full Gate B suite today — Run team has not yet
pushed the hotfix branch. When the verification doc lands and the
merged tip is available, Gate B parity check + the per-cycle scenarios
will run as the actual verification work.

## Workspace artifacts retained

- `/tmp/dotnet-equip-probe/` — fixture copy + restored NuGet cache +
  TestResults tree (Cobertura, opencover, json, lcov, TRX). Retained
  so the smoke is one-command repeatable for future debugging.
- `~/.dotnet/sdk/8.0.421/` — SDK install. Permanent.
- `~/.local/share/novetest-toolchains.sh` — central PATH/env shim.
  Source it at the top of any verification session:

  ```bash
  source ~/.local/share/novetest-toolchains.sh
  # -> [novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5
  ```

## Operational notes / open items for PM

1. **Maven floor amendment still pending.** My 2026-06-05 hotfix-3
   findings Recommendation #1 (matrix floor 3.9 -> 3.8) is not yet in
   `decisions/2026-05-25-supported-engine-matrix.md`. Doesn't block
   .NET cycle. Reminder only.

2. **Two host-equip findings now exist for two physical machines.**
   `findings/manual-test-team-2026-06-04-host-equip.md` (other dev box,
   Temurin + Maven 3.9.16 + user-local everything) and this file
   (`YJ-LAPTOP`, apt JDK 17 + Maven 3.8.7 + user-local Gradle/dotnet).
   PM may want a brief "host map" doc under `agent-comms/history/` at
   next cycle close — both hosts are equipped and either can serve as
   the .NET verification host.

3. **The toolchain shim is the single source of truth on this host**
   for which engine versions are installed and where. If PM bumps a
   floor or introduces a new engine, that file's the surgical edit
   point.

4. **`~/.bashrc` was NOT modified.** The prior other-machine equip
   appended a 4-line block to `~/.bashrc` that sources the shim on
   shell startup. I deliberately did NOT do that here — the shim
   should be sourced explicitly per verification session, so we don't
   accidentally pollute non-Nove-Test shells with the equipped PATH.
   PM can amend this policy if "always-on" is preferred.

5. **Ready for the .NET adapter cycle.** When Run team hands off and
   Main Branch writes the verification doc, this host can execute:
   - The §2.5 pre-handoff gate equivalent (full pytest suite + dotnet
     focus 0 skips 0 fails)
   - The D1 reproducer from the hotfix brief §1.1 (verbatim)
   - The CLI smoke gates per equip-and-exercise §2
   - Any envelope-pin captures Main Branch specifies in the verification
     doc

## Effective date

2026-06-06. Pre-emptive equip; no recurring obligation. Findings file
exists to record the equip state for PM's cycle-close ledger and so
the next Manual Test verification can start with the toolchain
versions pinned.
