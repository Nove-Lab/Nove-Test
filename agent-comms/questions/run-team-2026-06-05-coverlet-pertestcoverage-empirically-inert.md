---
from: novetest-run-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-05
slug: coverlet-pertestcoverage-empirically-inert
related:
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - design/implementation-plan/engine-adapters.md
---

# Question — `<PerTestCoverage>true</PerTestCoverage>` empirically inert in Coverlet 6.0.x via the XPlat data collector path

## TL;DR

The 2026-06-03 decision pinned `<PerTestCoverage>true</PerTestCoverage>` as
the per-test trigger and Coverlet 6.0.2 as the floor (because 6.0.0/6.0.1
"had a non-Windows GUID-subdirectory path bug that prevented per-test
output files from being surfaced to the VSTest data collector pipe").
Empirically on the equipped host (SDK 8.0.421 / Coverlet 6.0.2 AND 6.0.4
/ xunit 2.6 / Linux), `<PerTestCoverage>true</PerTestCoverage>` in the
runsettings is **inert via the XPlat data collector path** — only the
aggregate `coverage.cobertura.xml` is emitted (1 file per test run,
NOT 1 file per test method).

VSTest does receive and pass the configuration to Coverlet (visible in
`--diag` log: the runsettings XML reaches `CoverletInProcDataCollector`
with `PerTestCoverage=true`). But no per-test cobertura files appear
under `TestResults/<guid>/coverage.*.cobertura.xml` — the only files
are the aggregate `coverage.cobertura.xml` + `coverage.opencover.xml`
+ `coverage.json` + `coverage.info` (lcov).

Brief §4.3 + §6.1 anticipated this might happen and authorized
aggregate-only fallback. This question asks PM to confirm the v1
disposition AND amend the decision document if needed.

## Empirical evidence (on equipped host /tmp/dotnet-probe-v2)

**Toolchain**: dotnet SDK 8.0.421 (user-local install), Coverlet
6.0.2 and 6.0.4 (both tried), xUnit 2.6.0, Microsoft.NET.Test.Sdk
17.8.0, Linux x86_64.

**Fixture shape**: canonical library + test project split.
- `MathLib/MathLib.csproj` (classlib) — contains `MathOps.Add`, `MathOps.Subtract`
- `MathLib.Tests/MathLib.Tests.csproj` (xunit) — references MathLib;
  contains 3 tests: 2 pass + 1 intentional fail + 1 `[Theory]` with `[InlineData(1,2,3)]`

**Runsettings used** (decision §1.1 verbatim):

```xml
<?xml version="1.0" encoding="utf-8"?>
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat Code Coverage">
        <Configuration>
          <Format>cobertura,opencover,json,lcov</Format>
          <PerTestCoverage>true</PerTestCoverage>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
```

**Command**: `dotnet test --logger "trx;LogFileName=results.trx" --results-directory TestResults --collect:"XPlat Code Coverage" --settings coverlet.runsettings`

**TestResults tree**:

```
TestResults/_yjshin_2026-06-05_10_50_13/In/yjshin/coverage.cobertura.xml   <- aggregate
TestResults/_yjshin_2026-06-05_10_50_13/In/yjshin/coverage.opencover.xml
TestResults/09dbabb3-e2fd-4eeb-8e47-e2a2e55758c0/coverage.cobertura.xml    <- aggregate (same content)
TestResults/09dbabb3-e2fd-4eeb-8e47-e2a2e55758c0/coverage.opencover.xml
TestResults/results.trx
```

No `coverage.<slug>.cobertura.xml` files anywhere — the per-test glob
pattern `coverage.*.cobertura.xml` matches **zero files** post-run.

**Aggregate file content** (proves Coverlet IS instrumenting; just not
splitting per-test):

```xml
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1" branch-rate="1" version="1.9" timestamp="1780624177" lines-covered="2" lines-valid="2" ...>
  <sources>...</sources>
  <packages>
    <package name="MathLib" line-rate="1" ...>
      ...MathLib.MathOps.Add + Subtract lines...
    </package>
  </packages>
</coverage>
```

**VSTest `--diag` log excerpt** (shows the config reaches Coverlet
correctly):

```
DataCollectionRequestSender.SendBeforeTestRunStartAndGetResult:
  Send BeforeTestRunStart message with settingsXml
  <RunSettings>
    <DataCollectionRunSettings>
      <DataCollectors>
        <DataCollector friendlyName="XPlat code coverage" enabled="True">
          <Configuration>
            <Format>cobertura</Format>
            <PerTestCoverage>true</PerTestCoverage>    <-- present, enabled
            <SingleHit>false</SingleHit>
            ...
```

So VSTest IS handing `PerTestCoverage=true` to
`CoverletInProcDataCollector` (codebase: `coverlet.collector.dll`
6.0.4). Coverlet's behavior is to silently NOT emit per-test files
under this path.

## Likely root cause (informed hypothesis)

`<PerTestCoverage>` is documented in Coverlet's MSBuild integration
(`coverlet.msbuild` package, `<EnablePerTestCoverage>true</EnablePerTestCoverage>`
in csproj) — that path DOES emit per-test files. The XPlat data
collector path (`coverlet.collector` package + `--collect:"XPlat Code
Coverage"`) shares the runsettings XML namespace but does NOT honor
the `<PerTestCoverage>` key in the same way (or at all) — possibly
because the XPlat collector runs as an **in-process data collector**
under VSTest while the msbuild path runs at **build time** with full
PDB instrumentation hooks per test method.

The decision document's claim of "6.0.0/6.0.1 had a non-Windows
GUID-subdirectory path bug" suggests this was investigated at the
documentation level, but the actual Coverlet 6.x XPlat code collector
does not expose per-test output as a working feature regardless of
that gate.

## What the adapter does today (this slice)

Pending PM's decision, the adapter implements the SAFEST behavior:

1. **runsettings template** keeps decision §1.1 verbatim (including
   `<PerTestCoverage>true</PerTestCoverage>`) so a future Coverlet
   version that DOES start honoring the gate produces per-test files
   without any adapter change.
2. **Coverage glob** prefers per-test (`coverage.*.cobertura.xml`) but
   falls back to aggregate (`coverage.cobertura.xml`) when the per-test
   glob returns 0 files. Today this fallback fires 100% of the time on
   SDK 8.0 / Coverlet 6.0.x; if PM amends the decision OR a future
   Coverlet release fixes the path, the fallback automatically yields
   per-test files.
3. **`mapping_granularity` derivation** dispatches on the glob's
   actual result count: 0 per-test files → `aggregate`; >0 → `per-test`.
4. **R1 probe in integration test** asserts EITHER per-test glob
   returns ≥1 file with slug-correlation passing OR aggregate fallback
   returns exactly 1 file with valid coverage content. This way the
   test pins the empirical reality on the equipped host while not
   over-constraining a future config.

## Question to PM

1. **Confirm**: ship v1 with aggregate-as-effective-default, document
   the empirical finding, defer per-test to a future cycle (e.g. a
   `coverlet.msbuild`-based path that would require user csproj
   modification — which violates the non-modification contract — OR a
   future Coverlet release that fixes the XPlat path)?

2. **Amend** `decisions/2026-06-03-coverlet-pertestcoverage-key.md`?
   The decision currently asserts per-test is achievable via the
   XPlat path with `PerTestCoverage=true`; the empirical evidence
   contradicts that. Suggested amendment shape:
   - §3 update: "Glob `TestResults/**/coverage.cobertura.xml`
     (aggregate). Per-test mode via the XPlat data collector path
     is **empirically inert in Coverlet 6.0.x** — see
     `questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md`.
     The runsettings template retains `<PerTestCoverage>true</PerTestCoverage>`
     for forward-compatibility with a future Coverlet fix."
   - Add a §"R1 closure (2026-06-05)" subsection documenting the
     empirical finding and the closure of R1 via the aggregate path
     for v1.
   - Add a new R4 risk noting per-test coverage is deferred and
     Localization Phase 4's per-test granularity for .NET is
     reduced to aggregate.

3. **Manual Test re-pass expectation**: Manual Test will need to
   re-verify on the same equipped host or a different one. The empirical
   finding has been validated on this host (SDK 8.0.421); a different
   minor SDK or Coverlet version COULD theoretically behave differently
   (unlikely but possible).

## Recommended disposition

Run team's recommendation: **proceed with aggregate-effective-default**
+ amend the decision per option 2 above. Per-test xUnit coverage is
deferred to a follow-up slice. Phase 4 Localization's SBFL across
.NET projects will operate at aggregate granularity at v1; users with
per-test xUnit coverage requirements file a feature request and we
revisit (likely with a `coverlet.msbuild` opt-in flag that explicitly
modifies the user's csproj with a clear "this is required" prompt — a
breaks-the-non-mod-contract feature is opt-in, not default).

This question does NOT block adapter delivery — the adapter ships
with the safest behavior described above. PM's response amends docs
+ tests if needed.

## Effective date

Filed 2026-06-05 as part of the Phase 2.5 .NET adapter cycle. Resolution
expected within the cycle (PM has time before Manual Test re-pass).
