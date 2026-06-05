---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-03
slug: coverlet-pertestcoverage-key
related:
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - scripts/dev-host-setup.md
supersedes_open_question: 4
---

# Decision: Pin `coverlet.collector >= 6.0.2`; use `<PerTestCoverage>true</PerTestCoverage>` + `<SingleHit>false</SingleHit>` in `coverlet.runsettings`; xUnit v3 / Microsoft.Testing.Platform deferred from MVP

CEO-approved on 2026-06-03 after a PM-led specialist investigation
(dotnet-core-expert) of the Coverlet 6.x release history and the
Microsoft.Testing.Platform coverage architecture. This closes
[Open Question #4](../../design/implementation-plan/delivery-phasing.md#open-questions)
("Coverlet `PerTestCoverage` exact configuration key in the version we pin").

## Decision

The .NET / C# adapter (`src/novetest/run/adapters/dotnet_adapter.py`, to be
created at Phase 2.5 .NET cycle) MUST:

1. **Pin `coverlet.collector` to `>=6.0.2, <7.0.0`.** Floor is 6.0.2, not
   6.0.0/6.0.1, because the earlier patches had a non-Windows GUID-subdirectory
   path bug that prevented per-test output files from being surfaced to the
   VSTest data collector pipe (Coverlet GitHub issue #1780-class, fixed in
   6.0.2).

2. **Generate `coverlet.runsettings` on the fly** with the per-test coverage
   block exactly as:

   ```xml
   <RunSettings>
     <DataCollectionRunSettings>
       <DataCollectors>
         <DataCollector friendlyName="XPlat code coverage">
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

3. **Glob output files**:
   - **Aggregate (v1 effective default)**: `TestResults/**/coverage.cobertura.xml` — single file per test run.
   - **Per-test (deferred, forward-compat retained)**: `TestResults/**/coverage.*.cobertura.xml` — one file per test method named `coverage.<test-display-name>.cobertura.xml` where `<test-display-name>` is a slugified form of the test method's display name.

   The adapter MUST attempt the per-test glob first and fall back to aggregate when the per-test glob returns 0 files.

   > **Amendment 2026-06-05 (CEO-approved):** Empirical verification on the Phase 2.5 .NET adapter cycle (Coverlet 6.0.2 AND 6.0.4 / dotnet SDK 8.0.421 / xunit 2.6 / Linux x86_64) demonstrates that `<PerTestCoverage>true</PerTestCoverage>` is **inert** via the `coverlet.collector` XPlat data collector path — only the aggregate `coverage.cobertura.xml` is produced regardless of the runsettings element. VSTest `--diag` log confirms the config reaches Coverlet's `CoverletInProcDataCollector`; Coverlet does NOT split per-test under this path. Per-test coverage on .NET is achievable only via the `coverlet.msbuild` MSBuild integration which requires user csproj modification, violating Nove Test's non-modification contract. **Adapter ships aggregate-effective-default for v1.** The adapter retains `<PerTestCoverage>true</PerTestCoverage>` in its runsettings template for forward-compatibility with a future Coverlet release that fixes the XPlat path. The per-test-glob-with-aggregate-fallback strategy auto-degrades today (100% to aggregate); zero adapter change required if a future Coverlet release flips the behavior. See `agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md` (resolved by this amendment, queued for archive at cycle close).

4. **Detect the user's resolved Coverlet version via `dotnet list <project>
   package --include-transitive`** so transitive references through
   `xunit.runner.visualstudio` are visible. Prefer `--format json` when the
   user's SDK supports it (dotnet SDK 7.0+); fall back to tabular parsing
   otherwise. If the resolved version is below 6.0.2, degrade per §5.

5. **Fallback** when `coverlet.collector` is absent OR below 6.0.2: omit the
   `<PerTestCoverage>` element from the generated runsettings, emit
   `mapping_granularity: aggregate` on the resulting CoverageFact, and surface
   a structured `warnings` entry of kind `engine-misconfigured` with install
   guidance ("upgrade coverlet.collector to >= 6.0.2 for per-test coverage").

6. **xUnit v3 / Microsoft.Testing.Platform coverage path is DEFERRED from
   MVP.** Detection signal (`<PackageReference Include="xunit" Version="3.*" />`
   in the project file) MUST land in the adapter. When detected, the adapter
   MUST emit a `warnings` entry of kind `xunit-v3-coverage-deferred` with the
   message "xUnit v3 / Microsoft.Testing.Platform coverage is not yet supported
   by novetest; falling back to test execution without coverage" and proceed
   to run tests without coverage collection. A post-MVP slice will add the
   MTP coverage extension path.

## Rationale

### Why 6.0.2 floor (not 6.0.0)

`PerTestCoverage` was introduced in `coverlet.collector` 6.0.0 (December 2023),
but 6.0.0 and 6.0.1 had a defect where the per-test output files were written
but the GUID subdirectory paths were not surfaced correctly to the VSTest data
collector pipe on non-Windows hosts. The fix landed in 6.0.2; the key has
been stable in shape and location since then. There is no value in advertising
support for a version that produces undetectable output files on the project's
primary Linux/macOS dev hosts.

### Why `<SingleHit>false</SingleHit>` is mandatory

Without an explicit `<SingleHit>false</SingleHit>`, Coverlet defaults to
`SingleHit=true` in aggregate mode, which records only the first hit per line.
In per-test mode this produces misleading zero-hit lines when tests share
coverage paths, because the "first hit" is consumed by the first test in the
batch. The Localization engine's SBFL formulas depend on accurate per-test
hit counts; misleading zeros would corrupt the spectrum matrix. Setting it
explicitly to `false` matches Coverlet's recommended per-test configuration.

### Why the glob pattern changes from aggregate

In aggregate mode Coverlet writes a single `coverage.cobertura.xml`. In
per-test mode it writes `coverage.<slug>.cobertura.xml` per test method. The
existing design-doc glob `TestResults/**/coverage.cobertura.xml` matches the
former but not the latter; for per-test mode we MUST use
`coverage.*.cobertura.xml`. This also means the adapter's filename-to-test-
identity correlation logic is load-bearing — see Risk R1 below.

### Why xUnit v3 / MTP is deferred from MVP

xUnit v3 runs natively on Microsoft.Testing.Platform (MTP), which does not
use VSTest data collectors. The `--collect:"XPlat Code Coverage"` flag and
the `coverlet.collector` NuGet package are VSTest mechanisms; both are inert
on the MTP path. Coverage on MTP requires a different integration
(`Microsoft.Testing.Extensions.CodeCoverage` extension OR a `coverlet.msbuild`
build-side hook). The msbuild hook would require modifying the user's
`.csproj`, which violates Nove Test's non-modification contract. The MTP
extension path is a separate adapter slice with its own discovery, command
line, and parser; bundling it into the Phase 2.5 .NET cycle would double the
scope and risk shipping neither path cleanly.

The xUnit v3 deferred-slice will be scoped after the v2 / VSTest / Coverlet
path is in production and we have real user data on v2 vs v3 adoption.

### Why no separate `MstestAdapter` / `NunitAdapter`

xUnit + Coverlet is the canonical .NET CLI test stack and the one Microsoft's
own templates default to. MSTest and NUnit users can be added in additive
slices later without breaking this decision (their test runners also route
through VSTest in the v2 path, and the runsettings format is shared).

## Risks (carried into the .NET adapter cycle brief)

The .NET adapter cycle's DoD MUST include bullets addressing R1 and R2.

- **R1 (medium)** — Parametrized xUnit tests have display names that include
  `[`, `]`, `(`, `)`, `,`, and Unicode. Coverlet's slugification of these
  characters is inconsistent across OS path-safety rules. The adapter's
  filename→test-identity correlation must be probed against a parametrized
  fixture before the algorithm is committed. Expect 1–2 days of probe time.
  Mitigation: the .NET cycle brief includes a fixture-probe DoD bullet and
  the adapter degrades to aggregate granularity when correlation fails.

- **R2 (medium, MVP-affecting)** — Per-test mode writes one Cobertura XML
  file per test method. A suite with 10,000 tests produces 10,000 files.
  `NFR-COV-002` (50k locations parsed in <5s) was measured against a single
  aggregate file. Per-test mode performance on large suites must be validated
  against a >=5k-test fixture before shipping. Mitigation: if NFR-COV-002 is
  violated, expose a `--coverage-granularity=aggregate` opt-down flag and
  default large suites to aggregate; this is a recoverable scope adjustment.

- **R3 (low)** — `dotnet list package --include-transitive` produces tabular
  text output; parsing must tolerate the line-wrapping that appears on narrow
  terminals and Windows line endings. The adapter MUST set `--format json`
  (supported as of dotnet SDK 7.0) when the SDK version allows; otherwise
  fall back to tabular parsing.

- **R4 (medium, MVP-affecting) — added 2026-06-05 amendment** — Phase 4 Localization SBFL across .NET projects operates at **aggregate granularity** (not per-test) because per-test coverage is empirically inert on the Coverlet XPlat path (see §3 amendment). Per `decisions/2026-05-30-localization-outcome-envelope-shape.md` and Phase 4's three-mode design, .NET projects route to **`failure_proximity` mode** (file-edit-distance heuristic on test failures), NOT full SBFL with per-test spectrum matrix (Ochiai / Op2 / DStar / Tarantula). This is a **degraded but well-defined** user experience — `novetest localization` CLI still returns ranked candidates, just with reduced precision compared to per-test SBFL. The 3-mode design absorbs this without breaking the user contract. Future cycle pathways to restore per-test on .NET: (a) opt-in `coverlet.msbuild` mode via a flag that explicitly modifies user's csproj (with prominent user-consent prompt — opt-in violation of non-modification contract is acceptable when explicit), OR (b) a future Coverlet XPlat path fix from upstream.

## Supported-engine matrix amendment

Adds to `decisions/2026-05-25-supported-engine-matrix.md`:

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| .NET SDK | 8.0 (LTS) | TBD (.NET 9 STS, after CI cell) | xUnit v2 + Coverlet path; xUnit v3 / MTP coverage deferred |
| coverlet.collector | 6.0.2 | 6.0.x | floor pinned by this decision; sibling `<SingleHit>false</SingleHit>` required |
| xunit (v2) | 2.6 | 2.9.x | v3 detected and routed to `xunit-v3-coverage-deferred` warning |
| Microsoft.NET.Test.Sdk | 17.6 | 17.x | bundled with .NET 8 SDK; absence surfaces as `engine-misconfigured` |

PM updates the matrix decision in the same commit as this decision.

## Dev host setup amendment

`scripts/dev-host-setup.md` §6 (currently a placeholder) is filled in this
same commit with concrete `apt-get install dotnet-sdk-8.0` / `brew install
--cask dotnet-sdk` recipes and a Coverlet-floor smoke probe (`dotnet new
xunit && dotnet add package coverlet.collector --version 6.0.2 && dotnet
test`).

## Implementation notes for the .NET adapter task brief

When PM writes the .NET adapter task brief, it MUST:

1. Pin §1's runsettings XML verbatim as a binding contract.
2. Include the §6 xUnit v3 detection + `xunit-v3-coverage-deferred` warning
   as a DoD bullet.
3. Include the R1 parametrized-fixture probe + R2 >=5k-test performance
   validation as separate DoD bullets. (R1 is **resolved 2026-06-05** by the §3
   amendment: per-test coverage on the XPlat path is empirically inert, so the
   slug-correlation algorithm only exercises against synthetic test data and
   the aggregate-fallback path covers the runtime reality.)
4. Reference the supported-engine matrix amendment for floor versions.
5. Reference the dev-host-setup .NET section so Manual Test can equip the
   host before E2E verification (per 2026-05-29 polyglot-host-parity contract).

## Effective date

2026-06-03.

## Supersedes

Open Question #4 in `delivery-phasing.md`. The "Coverlet 6.x minor drift"
note in `engine-adapters.md` §6 is corrected in the same commit (drift was
in the 5.x→6.x transition + a pre-release `EnablePerTestCoverage` name;
there is no drift within shipped 6.x).
