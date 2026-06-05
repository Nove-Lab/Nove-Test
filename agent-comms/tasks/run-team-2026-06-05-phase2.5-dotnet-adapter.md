---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-05
slug: phase2.5-dotnet-adapter
status: pending
related:
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md
  - agent-comms/history/2026-06-05-cargo-cli-orchestration-defect-and-second-equip-exercise-validation.md
  - design/implementation-plan/engine-adapters.md
  - scripts/dev-host-setup.md
---

# Phase 2.5 — .NET / xUnit v2 + Coverlet adapter (the 6th and last native engine)

## TL;DR

| Item | Value |
|---|---|
| Scope | 1 cycle, monolithic; NEW `src/novetest/run/adapters/dotnet_adapter.py` + 2 fixtures + unit & integration tests |
| Closes | Phase 2.5 native engine work (5/6 → 6/6 production-ready) |
| Equip-and-exercise | **§2.5 IN FORCE** — Run team's pre-handoff gate runs on equipped host with `dotnet >= 8.0` + `coverlet.collector >= 6.0.2` resolvable |
| Pre-conditions | NONE for `.claude/settings.json` (both equipped hosts use user-local `~/.dotnet/dotnet`, NOT apt). dev-host-setup.md §6 already populated. |
| Estimated LOC | ~700-900 src + ~600-800 tests + 2 fixtures |
| Estimated time | 1-2 days (monolithic, but R1 slug-correlation probe + Coverlet runsettings/version detection are the hard parts) |

This brief is informed by the JUnit cycle's 3-hotfix arc (1.5 days
saved here by pre-flagging the landmines) and the cargo CLI orchestration
cycle's clean single-pass close (template for §2.5 compliance + native
exit code forensics). Both histories are required pre-flight reading.

## ✅ Why now

JUnit + cargo cycles closed cleanly. All preconditions present:
- Coverlet `PerTestCoverage` key decision filed 2026-06-03
- xUnit v3 deferral decision filed 2026-06-03
- .NET 8.0 / coverlet 6.0.2 / xunit 2.6 / Microsoft.NET.Test.Sdk 17.6 matrix floors pinned 2026-06-03
- dev-host-setup §6 .NET section populated 2026-06-03
- Equip-and-exercise §2.5 binding validated across two adapter cycles in a row

Closing this slice brings **6/6 native engines production-ready**, which
unblocks Phase 3's formal "all six adapters finalized" entry condition.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — project-wide rules
2. `.claude/agents/novetest-run-team.md` — your charter
3. **`agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md`** — the binding contract for this cycle (runsettings XML, version floor, v3 deferral). Treat §1-6 + Risks R1-R3 as load-bearing.
4. **`agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`** §1 (Manual Test on equipped host) + §2 (CLI smoke template) + §2.5 (Run team's own pre-handoff gate on equipped host when adapter+test files in diff). §2.5 binds this slice.
5. `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` rows: `.NET SDK`, `coverlet.collector`, `xunit (v2)`, `Microsoft.NET.Test.Sdk`
6. `agent-comms/decisions/2026-05-30-native-result-metadata-slot.md` — typed metadata for native_exit_code
7. **`agent-comms/history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md`** — the JUnit 3-hotfix arc; LL #1 (skip-gate masking), #2 (argv assertions necessary but not sufficient), #3 (build-tool task-graph behavior under test failure), #5 (envelope path consistency), #8 (Maven floor). All apply here in parallel form.
8. **`agent-comms/history/2026-06-05-cargo-cli-orchestration-defect-and-second-equip-exercise-validation.md`** — LL #1 (native exit code as forensics), #3 (audit-trail preservation), #4 (`adapter-unparseable-output` umbrella overload — 4 sub-kinds now, watch for accidental 5th).
9. `design/implementation-plan/engine-adapters.md` §6 (.NET section, full) + "Adapter Implementation Pattern" (lines 521-557) + "Doctor pass / engine readiness" (lines 559-571)
10. `src/novetest/run/adapters/junit_adapter.py` — the most recent build-tool-driven adapter (pattern source for: project detection from manifest, per-run hermetic config generation, build tool failure→XML semantic, store.path-relative coverage_xml emission)
11. `src/novetest/run/adapters/cargo_adapter.py` — pattern source for: CLI smoke shape (`tests/integration/run/test_cargo_basic.py::test_cli_smoke_run_dot_emits_envelope`), audit-trail preservation, native_exit_code metadata typing
12. `src/novetest/run/engine_selector.py` — where the `dotnet → xunit` mapping lands (see §3.1 below)
13. `src/novetest/run/normalizer.py` — `_aggregate_junit_status` (lines ~736-757) — same pattern needed for `_aggregate_xunit_status` from TRX outcomes
14. `src/novetest/orchestration/workflows/run.py` lines 32-46 (`RunOutcome.memory_entry`) + lines 85-88 (`.relative_to(store.path)` invariant — LANDMINE per JUnit hotfix-3)
15. `src/novetest/cli/app.py` lines 269-281 — `data = {"memory_entry": entry.to_dict()}` envelope shape (LANDMINE: `data.memory_entry.run_record.{...}` NOT `data.run_record.{...}`)
16. `src/novetest/cli/output.py:12-17` — exit codes; CLI smoke assertion is `(0, 3)` (NOT `(0, 1)`)
17. `scripts/dev-host-setup.md` §6 — recipe to confirm Run team's pre-handoff host is equipped (and update §6 wording if outdated; see §10 below)

---

## 1. Decision-bound design constraints (DO NOT deviate)

Five constraints pinned by `decisions/2026-06-03-coverlet-pertestcoverage-key.md`:

### 1.1 Coverlet runsettings (verbatim)

The adapter MUST generate exactly this XML structure at
`<artifact_dir>/native/coverlet.runsettings` per run (hermetic, NOT
shared across runs):

```xml
<?xml version="1.0" encoding="utf-8"?>
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

The `<SingleHit>false</SingleHit>` sibling is mandatory (decision §"Why
`<SingleHit>false</SingleHit>` is mandatory") — without it, Coverlet
defaults to SingleHit=true and produces misleading zero-hit lines.

### 1.2 Coverlet version floor (>= 6.0.2)

`coverlet.collector` 6.0.0/6.0.1 had a non-Windows GUID-subdirectory path
bug that prevented per-test files from being surfaced. Adapter MUST:

- **Detect** the user's resolved Coverlet version via
  `dotnet list <project_csproj> package --include-transitive --format json`
  (preferred — dotnet SDK >= 7.0)
- **Fallback** to tabular text parse on SDK < 7.0 (R3-low; tolerate line-wrapping)
- If resolved < 6.0.2 OR Coverlet absent → emit `engine-misconfigured`
  warning + aggregate fallback (drop `<PerTestCoverage>` from runsettings,
  glob aggregate `coverage.cobertura.xml`)

### 1.3 xUnit v3 detection + deferral

- **Detect** v3 from `.csproj`: any `<PackageReference Include="xunit"` element with `Version="3.*"`, `Version="3.0.0"`, etc.
- v3 detected → emit `warnings` entry of kind `xunit-v3-coverage-deferred` with message:
  > "xUnit v3 / Microsoft.Testing.Platform coverage is not yet supported by novetest; falling back to test execution without coverage"
- Run tests **without** coverage collection (omit `--collect:"XPlat Code Coverage"` and `--settings` flags)
- v3 tests still execute + produce TRX → normal status derivation works

### 1.4 Per-test Cobertura file glob

- **Per-test mode (Coverlet >= 6.0.2 + PerTestCoverage true)**:
  glob `TestResults/**/coverage.*.cobertura.xml`
- **Aggregate mode (degraded)**:
  glob `TestResults/**/coverage.cobertura.xml`

Adapter dispatches glob based on chosen mode (which depends on detected version + v3 detection branch).

### 1.5 No NUnit / MSTest path

Out of scope per decision §"Why no separate `MstestAdapter` / `NunitAdapter`". Future additive slice if user demand surfaces.

---

## 2. Anti-patterns to avoid (from JUnit + cargo cycle histories)

### 2.1 Skip-gate masking class of defects (LL #1 from JUnit history)

- **Hotfix-1 D4**: CLI smoke assertion `(0, 1)` — never evaluated because smoke skipped on JDK-less host
- **Hotfix-2 F1**: envelope path `data["run_record"]` (wrong) — dereference never evaluated because smoke skipped
- **Hotfix-2 F2**: Gradle `--continue` not running `:jacocoTestReport` — semantic never exercised because integration test skipped

**Mitigation in this cycle**: equip-and-exercise §2.5 binds Run team's
own pre-handoff gate. Diff modifies BOTH `src/novetest/run/adapters/dotnet_adapter.py`
AND `tests/integration/run/test_dotnet_*.py` → §2.5 IN FORCE. Run team
MUST run the gate on an equipped host (this checkout's host or equivalent;
both equipped hosts have `~/.dotnet/dotnet` user-local). **0 skips on
dotnet integration cases is non-negotiable**.

### 2.2 CLI smoke assertion is `(0, 3)`, NOT `(0, 1)` (JUnit hotfix-1 D4)

```python
# CORRECT:
assert run_result.returncode in (0, 3), (
    f"unexpected cli-error: returncode={run_result.returncode} stderr={run_result.stderr!r}"
)

# WRONG (the JUnit hotfix-1 landmine):
assert run_result.returncode in (0, 1), ...
```

`EXIT_OK = 0` (all tests passed) + `EXIT_USER_TESTS_FAILED = 3` (some tests
failed by design). The canonical fixture has 1 intentionally-failing test,
so the dot/bare smoke returns 3.

### 2.3 Envelope path: `data.memory_entry.run_record.{...}` (JUnit hotfix-2 F1)

```python
# CORRECT:
rr = e['data']['memory_entry']['run_record']
assert rr['engine_name'] == 'xunit'

# WRONG (the JUnit hotfix-2 landmine):
rr = e['data']['run_record']
```

Sourcing pin: `src/novetest/orchestration/workflows/run.py:32-46`
(`RunOutcome.memory_entry`) → `src/novetest/cli/app.py:269-281`
(`data = {"memory_entry": entry.to_dict()}`).

### 2.4 Coverage MUST be emitted even when tests fail (JUnit hotfix-2 F2 + hotfix-3 Fix-D)

`dotnet test` exits non-zero when ≥1 test fails. The XPlat Code Coverage
data collector runs **during the test execution** as a sidecar to VSTest,
NOT as a post-step. This means: per-test Cobertura XML files SHOULD be
written even when tests fail, because the collector flushes on each
test method completion (pass or fail).

**Verify this empirically** during adapter dev:
1. Use the canonical fixture (1 intentionally-failing test).
2. Run `dotnet test --collect:"XPlat Code Coverage" --settings <runsettings>`.
3. Confirm exit ≠ 0 AND `TestResults/<guid>/coverage.<slug>.cobertura.xml`
   files are present.

If empirically Coverlet skips coverage on test failure (unlikely but
not impossible — depends on VSTest's data collector lifecycle), the
adapter must compensate. See §6 below for hypotheses.

### 2.5 `.relative_to(store.path)` invariant on coverage_xml (JUnit hotfix-3 F1)

`src/novetest/orchestration/workflows/run.py:85-88` strips `store.path`
prefix from artifact paths before persisting. Coverage XML paths MUST be
emitted ABSOLUTE (under `<artifact_dir>/native/...`) and the orchestration
layer rewrites them. Do NOT pre-relativize in the adapter.

### 2.6 Audit-trail preservation under adapter-local normalization (cargo LL #3)

Whatever the adapter does to compose the `dotnet test` invocation (e.g.
runsettings injection, test filter normalization), the `RunRecord` MUST
still carry the user's verbatim `target_expression` + `target_type`.
Replay/Regression downstream depends on it.

Concrete case: if the adapter selects a specific test project from a
solution (.sln) workspace, the `target_expression` stays whatever the
user typed; only the argv differs.

### 2.7 Native exit code as forensic surface (cargo LL #1)

`metadata.native_exit_code` is a load-bearing forensic surface. For
`dotnet test`:
- `0` — all tests passed
- `1` — at least one test failed (or build failure pre-test-execution)
- `2` — usage error (rare)

Adapter MUST populate `metadata.native_exit_code` with the exact
`dotnet test` subprocess exit code, even when status derives from TRX
content rather than exit code. This is the forensic surface for future
"is the fix at the right layer" questions.

### 2.8 `adapter-unparseable-output` umbrella overload (cargo LL #4)

Cumulative sub-kinds (4 currently — compile-failure / env-var-missing /
llvm-cov-missing / no-tests-match). If you encounter a new genuinely-
distinct .NET-side condition (e.g. "dotnet SDK present but VSTest
runner missing"), consider whether the umbrella split is justified.
Per cargo brief §10: umbrella split requires `agent-comms/questions/`
entry first. Default to reusing `unparseable-output` with disambiguated
message text.

---

## 3. Scope (files to add / modify)

### 3.1 Source files

#### NEW: `src/novetest/run/adapters/dotnet_adapter.py` (~700-900 LOC)

The adapter. Module-level constants + canonical adapter shape per
`engine-adapters.md` "Adapter Implementation Pattern":

```python
ENGINE_NAME: Final[str] = "xunit"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 600.0
COVERLET_FLOOR_VERSION: Final[tuple[int, int, int]] = (6, 0, 2)
XUNIT_V3_DETECTED_WARNING_KIND: Final[str] = "xunit-v3-coverage-deferred"

# The decision-§1.1 verbatim runsettings string template — pinned.
_COVERLET_RUNSETTINGS_TEMPLATE: Final[str] = """<?xml version="1.0" encoding="utf-8"?>
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
"""

# Aggregate variant — drop <PerTestCoverage> when Coverlet < 6.0.2
_COVERLET_AGGREGATE_RUNSETTINGS_TEMPLATE: Final[str] = """<?xml version="1.0" encoding="utf-8"?>
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat code coverage">
        <Configuration>
          <Format>cobertura,opencover,json,lcov</Format>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
"""
```

Adapter responsibilities (mirror `junit_adapter.py` structure):

1. **Project detection** — scan workspace for `*.csproj` (single-project
   path for v1; if multiple `.csproj` OR a `.sln` is present alongside,
   emit `ambiguous-project-layout` warning and pick first `.csproj`
   alphabetically — Maven-style precedent from JUnit cycle).
2. **xUnit version detection** — parse `.csproj`, find `PackageReference Include="xunit"` element, read `Version` attribute. Match `^3\.` → v3 branch; otherwise v2.
3. **Coverlet version detection** — invoke `dotnet list <csproj> package --include-transitive --format json` (SDK ≥ 7.0); fallback to tabular text on `--format json` unsupported.
4. **runsettings generation** — `<artifact_dir>/native/coverlet.runsettings` per-run hermetic. Use `_COVERLET_RUNSETTINGS_TEMPLATE` (per-test) OR `_COVERLET_AGGREGATE_RUNSETTINGS_TEMPLATE` (aggregate).
5. **argv composition**:
   - Base: `dotnet test <csproj> --logger "trx;LogFileName=results.trx" --results-directory <artifact_dir>/native/TestResults`
   - Coverage on (v2 + Coverlet ≥ 6.0.2): `+ --collect:"XPlat Code Coverage" --settings <runsettings_path>`
   - v3 detected: NO coverage flags (per §1.3)
   - Coverlet absent or < 6.0.2: NO coverage flags + emit warning
6. **Subprocess invocation** — `run_subprocess(argv, cwd=workspace_path, timeout=_DEFAULT_TIMEOUT_SECONDS)`. Capture stdout.log + stderr.log under `<artifact_dir>/native/`.
7. **TRX parsing** — ElementTree-based; extract `<UnitTestResult>` elements; map outcomes:
   - `outcome="Passed"` → `"passed"`
   - `outcome="Failed"` → `"failed"`
   - `outcome="NotExecuted"` / `outcome="Skipped"` → `"skipped"`
   - duration from `duration` attribute (TimeSpan string parse)
8. **Failure detail capture** — per-test failure logs under `<artifact_dir>/native/failures/<test_slug>.log` containing `<ErrorInfo><Message/><StackTrace/></ErrorInfo>` content. `failure_reference` paths use `<test_slug>.log` (slug = sanitized test fully-qualified name).
9. **Per-test Cobertura correlation** — for each `coverage.<slug>.cobertura.xml`, correlate `<slug>` back to the TRX test identity. **R1 is here** — see §4 below for the probe.
10. **coverage_xml artifact** — emit a list of per-test Cobertura paths under artifact key `coverage_xml` (consistent with JUnit's `coverage_xml`). Absolute paths; orchestration layer relativizes.
11. **status aggregation** — derive from TRX content via a new `_aggregate_xunit_status` helper in `src/novetest/run/normalizer.py` (mirror `_aggregate_junit_status`).
12. **NativeResult assembly** — populate engine_name="xunit", engine_version (from `dotnet --version`), summary_counts, test_results, status, metadata (with `native_exit_code` per §2.7).

#### MOD: `src/novetest/run/engine_selector.py`

Add `"dotnet": "xunit"` to `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE`. Update the
docstring's "remaining two pairs" wording — only xunit remains
unimplemented before this slice, and after this slice all 6 ship.

#### MOD: `src/novetest/run/normalizer.py`

Add `_aggregate_xunit_status` helper mirroring `_aggregate_junit_status`
(lines ~736-757). Source pin: TRX `<UnitTestResult>` outcome enums.

#### MOD: `src/novetest/run/__init__.py`

Re-export `dotnet_adapter` symbols if needed (check existing pattern from
junit/cargo).

#### MOD (POTENTIALLY): `src/novetest/run/readiness.py`

If `assess_engine_readiness` has per-adapter doctor dispatch, add the
dotnet branch. Otherwise the adapter's own readiness probe is sufficient.

### 3.2 Fixtures (NEW)

#### `tests/fixtures/projects/dotnet-test-basic/`

xUnit v2 project. Generated from `dotnet new xunit -n dotnet_test_basic`
+ trimmed for fixture use (no `bin/` or `obj/` committed; add `.gitignore`).
Canonical contract: **2 passed + 1 failed = 3 total**. Mirror the
canonical-fixture shape used by pytest-basic / jest-basic / gotest-basic /
junit-maven-basic / cargo-test-basic.

Required test cases:
- `Tests.MathTests.TestAddPasses` (passes)
- `Tests.MathTests.TestSubtractIntentionallyFails` (fails by design)
- **`Tests.MathTests.TestParametrized` with `[InlineData(1, 2, 3)]`**
  (passes; this is the R1 slug-correlation probe — see §4 below).

Pin: matrix floors. .csproj must reference `xunit Version="2.6.0"` or
later (not 3.x).

#### `tests/fixtures/projects/dotnet-test-basic-coverage/`

Same project shape + explicit `<PackageReference Include="coverlet.collector" Version="6.0.2" />`
in csproj. Used by the coverage integration test. The runsettings is
NOT committed to the fixture (the adapter generates it per-run); the
fixture only carries the test sources + csproj.

### 3.3 Tests

#### NEW: `tests/unit/run/adapters/test_dotnet_adapter.py` (~30-50 tests)

Pattern mirror: `tests/unit/run/adapters/test_junit_adapter.py`. Test
classes:

- `TestProjectDetection` — single-csproj / multi-csproj+sln-warning / no-csproj-error
- `TestXunitVersionDetection` — v2 (Version="2.6.0", "2.9.x"), v3 (Version="3.*", "3.0.0"), edge cases (Version unset; SDK-style PackageReference)
- `TestCoverletVersionDetection` — `--format json` parse, tabular fallback parse, version-tuple compare (6.0.1 < floor, 6.0.2 = floor, 7.0.0 above ceiling)
- `TestRunsettingsGeneration` — per-test variant (assert XML content byte-equal to `_COVERLET_RUNSETTINGS_TEMPLATE`); aggregate variant; written to correct path
- `TestArgvComposition` — v2 + coverlet present: full argv; v2 + coverlet absent: argv without coverage flags + warning; v3 detected: argv without coverage flags + warning
- `TestTrxParsing` — Passed/Failed/Skipped/NotExecuted outcome map; duration parse; failure detail extraction
- `TestCobertúraCorrelation` — slug → test identity mapping; parametrized test slug includes data variant; correlation degrades gracefully when slug unparseable (drop per-test entry, log warning, no exception)
- `TestStatusAggregation` — `_aggregate_xunit_status` against synthetic TRX content (all-pass / mixed / all-fail / empty)
- `TestMetadataPopulation` — native_exit_code, dotnet_version
- `TestEngineMisconfiguredWarnings` — coverlet absent, coverlet < 6.0.2, dotnet missing
- `TestXunitV3DeferralWarning` — v3 detected → warning emitted; argv has no coverage flags

#### NEW: `tests/integration/run/test_dotnet_basic.py`

Real `dotnet test` invocation against `dotnet-test-basic/` (no coverage).
Skip-gate on `shutil.which("dotnet")`. Assert NativeResult shape:
- summary_counts == {passed: 2, failed: 1, skipped: 0, total: 3}
- status == "failed"
- engine_name == "xunit"
- engine_version matches `dotnet --version`
- metadata.native_exit_code == 1 (dotnet test's exit code when ≥1 test fails)

#### NEW: `tests/integration/run/test_dotnet_coverage.py`

Real `dotnet test --collect "XPlat Code Coverage" --settings <runsettings>`
against `dotnet-test-basic-coverage/`. Skip-gate on dotnet AND coverlet
floor presence. Assert:
- Same summary as basic + status
- artifact_paths.coverage_xml is a list of per-test Cobertura paths
- At least N per-test Cobertura files written (N = number of executed tests with coverage; varies by parametrization)
- **R1 probe**: parametrized test's slug correlates back to the TRX test identity (`Tests.MathTests.TestParametrized(a=1, b=2, expected=3)` or whatever the parametrization produces) — assert at least 1 per-test cobertura file's correlation succeeds for the parametrized case
- coverage_xml paths are absolute as emitted; orchestration layer relativizes

#### NEW: 2 CLI smokes IN `test_dotnet_basic.py` (per equip-and-exercise §2)

```python
def test_cli_smoke_run_dot_emits_envelope(cli_smoke_workspace: Path) -> None:
    """`novetest run .` against dotnet-test-basic emits the canonical envelope."""
    if shutil.which("dotnet") is None:
        pytest.skip("dotnet not installed")
    run_result = subprocess.run(
        ["uv", "run", "novetest", "run", "."],
        cwd=cli_smoke_workspace,
        capture_output=True,
        text=True,
    )
    assert run_result.returncode in (0, 3), (
        f"unexpected cli-error: returncode={run_result.returncode} stderr={run_result.stderr!r}"
    )
    envelope = json.loads(run_result.stdout)
    assert envelope["ok"] is True
    rr = envelope["data"]["memory_entry"]["run_record"]
    assert rr["engine_name"] == "xunit"
    assert rr["target_expression"] == "."
    assert rr["summary_counts"]["total"] == 3
    # ... etc

def test_cli_smoke_run_bare_emits_envelope(cli_smoke_workspace: Path) -> None:
    """Bare `novetest run` matches the dot-case execution semantics."""
    # Identical structure, asserts target_expression == "" + target_type == "workspace"
```

The `cli_smoke_workspace` fixture copies `dotnet-test-basic/` to a tmp
directory + runs `novetest init` (mirroring `test_cargo_basic.py`'s
`cli_smoke_workspace` fixture — copy literally and adapt the fixture name).

### 3.4 Design doc updates

#### MOD: `design/implementation-plan/engine-adapters.md` §6

Update if Run team discovers any decision deviation during adapter dev
(e.g. TRX outcome enum names not matching the doc; .NET 8.0 SDK runtime
behavior differing from doc). Otherwise no change required.

#### MOD (LIKELY): `scripts/dev-host-setup.md` §6

Current §6 prescribes Ubuntu 22.04 + Microsoft package feed. Both
equipped hosts use **user-local install via `dotnet-install.sh`**
(`~/.dotnet/dotnet`). At handoff time, Run team SHOULD amend §6 to:

- Note that both equipped hosts use user-local install (not apt)
- Document the `dotnet-install.sh` recipe as the primary path:
  ```sh
  curl -fsSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0 --install-dir ~/.dotnet
  ```
- Keep the apt path as alternative for system-wide installs

This is a doc-only amendment; no source impact. Bundled in the same
handoff commit per `scripts/dev-host-setup.md`'s PM policy (new adapter
task briefs MUST add/update §X at handoff time).

### 3.5 WORKLOG entry

Run team appends the standard top-of-file entry. Format per `WORKLOG.md`
preamble (Landed / Verified / Left open / Gotcha / Next).

---

## 4. R1 — Per-test Cobertura slug correlation (probe in fixture)

The decision §"Risks R1": parametrized xUnit tests have display names
including `[`, `]`, `(`, `)`, `,`, and Unicode. Coverlet's slugification
of these is inconsistent across OS path-safety rules.

### 4.1 Probe approach

Add `Tests.MathTests.TestParametrized` to the `dotnet-test-basic` fixture
with `[InlineData(1, 2, 3)]` (1 data point — keeps probe minimal). After
running `dotnet test --collect:"XPlat Code Coverage" --settings <runsettings>`:

1. Enumerate `TestResults/<guid>/coverage.*.cobertura.xml`
2. For each file, extract `<slug>` from filename
3. For each TRX `<UnitTestResult testName="...">`, compute the expected slug
4. Assert at least 1 match for the parametrized case (i.e. correlation algorithm doesn't fail catastrophically on `(`/`)`/`=`/`,`)

### 4.2 Correlation algorithm (recommended starting point)

Coverlet's slugifier roughly:
- Replace path-unsafe chars (`<>:"|?*` on Windows; `/` on Unix) with `_`
- Collapse runs of `_` to single `_`
- Truncate to OS path length limit

Recommendation: implement a forward slugifier in the adapter
(`_slugify_for_coverlet`) that takes a TRX `testName` and produces the
expected filename suffix. Match files by reverse lookup. If a `.cobertura.xml`
filename has no matching TRX entry, emit a `warnings` entry of kind
`coverlet-slug-unmapped` with the unmapped filename + drop that
per-test coverage entry from the result (do NOT raise).

### 4.3 If R1 is materially harder than expected

If the slugifier turns out to need OS-conditional logic that takes
> 1 day, raise an `agent-comms/questions/` entry and consider falling
back to aggregate-only for v1. The brief recommends per-test as the
target, but aggregate-only is acceptable if R1 blocks shipping.

---

## 5. R2 — Large-suite performance (DEFERRED)

Per-test mode writes one Cobertura XML per test method. A suite with
10,000 tests produces 10,000 files. `NFR-COV-002` (50k locations
parsed in < 5s) was measured against a single aggregate file.

**Defer to follow-up cycle.** This slice does NOT include a >= 5k-test
fixture. If empirical NFR-COV-002 violation surfaces during normal
testing (Run team's gate, Main Branch's gate, Manual Test re-pass),
file an `agent-comms/questions/` entry. The mitigation if needed:
expose `--coverage-granularity=aggregate` opt-down + default large
suites to aggregate. That's a separate cycle.

---

## 6. Empirical questions to answer during adapter dev

These aren't decisions; they're observations that should be confirmed
on the equipped host during R1 probe / coverage integration test:

### 6.1 Does Coverlet emit per-test Cobertura on test failure?

Decision-implied answer: **yes** (collector runs during test execution).
But verify empirically with the 1-fail canonical fixture. If no,
investigate VSTest data-collector lifecycle and consider a `--blame-hang`
or `--logger` flag adjustment.

### 6.2 Are TRX outcome values exactly `"Passed"` / `"Failed"` / `"NotExecuted"`?

ElementTree XPath examples in design doc suggest yes. Verify against
actual TRX from `dotnet-test-basic` run. Other observed enums (Inconclusive,
Aborted, Timeout, Error) — map to `"skipped"` if observed (NotExecuted-like)
or `"failed"` (Aborted/Error/Timeout-like) per the safer-default rule.

### 6.3 What's the `dotnet test` exit code when 1 test fails (others pass)?

Expected: `1`. Verify on canonical fixture. Pin in metadata.native_exit_code
test.

### 6.4 Does `dotnet list package --format json` exist on SDK 8.0?

Expected: yes (SDK >= 7.0 supports it). Verify on equipped host.

---

## 7. DoD bullets (14)

PM verifies + ticks each at cycle close.

| # | Bullet | Evidence form expected |
|---|---|---|
| 1 | `dotnet_adapter.py` created, `ENGINE_NAME = "xunit"`, follows canonical adapter pattern (detect / doctor / build_argv / parse_artifacts / coverage_artifact_paths) | `src/novetest/run/adapters/dotnet_adapter.py` exists; module-level `ENGINE_NAME` matches |
| 2 | `engine_selector.py` `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE["dotnet"] = "xunit"` | grep for the literal |
| 3 | xUnit v2 detection from `.csproj` PackageReference; v3 detection triggers `xunit-v3-coverage-deferred` warning + no coverage argv | `TestXunitV3DeferralWarning` unit test class |
| 4 | Coverlet version detection via `dotnet list package --include-transitive --format json` (SDK ≥ 7.0); tabular fallback for SDK < 7.0 | `TestCoverletVersionDetection` unit tests pass both paths |
| 5 | < 6.0.2 OR absent → `engine-misconfigured` warning + aggregate fallback runsettings | `TestEngineMisconfiguredWarnings` unit tests |
| 6 | `coverlet.runsettings` generated per-run at `<artifact_dir>/native/coverlet.runsettings`; XML matches decision §1.1 verbatim (per-test) OR §1.1 minus PerTestCoverage (aggregate) | `TestRunsettingsGeneration` byte-equal assertion |
| 7 | TRX parser produces normalized test outcomes (passed/failed/skipped) + duration + failure_reference | `TestTrxParsing` unit tests |
| 8 | Per-test Cobertura → test identity correlation works for parametrized fixture (R1 probe) | `test_dotnet_coverage.py::test_per_test_cobertura_correlates_parametrized` (integration) |
| 9 | `coverage_xml` artifact paths emitted ABSOLUTE; orchestration relativizes via `.relative_to(store.path)` | integration test asserts post-orchestration `RunRecord.artifact_paths.coverage_xml[0]` starts with `.novetest/` (NOT `/`) |
| 10 | `summary_counts` + `status` + `metadata.native_exit_code` populated correctly on canonical fixture | `test_dotnet_basic.py::test_basic_run_emits_native_result` |
| 11 | `tests/unit/run/adapters/test_dotnet_adapter.py` + `tests/integration/run/test_dotnet_basic.py` + `tests/integration/run/test_dotnet_coverage.py` all green | `uv run pytest -v` output |
| 12 | CLI smokes: `test_cli_smoke_run_dot_emits_envelope` + `test_cli_smoke_run_bare_emits_envelope`; assertion `returncode in (0, 3)`; skip-gate on `shutil.which("dotnet")` | `test_dotnet_basic.py` contains both literal function names |
| 13 | `uv run mypy --strict src` clean (source count grows 90 → 91 with new adapter file) | mypy output |
| 14 | Pre-handoff gate green on equipped host (full suite + dotnet focus 0 skips 0 fails); §2.5 binding satisfied | Run team handoff §"Pre-handoff gate environment" with detected toolchain versions + engine-specific counts |

---

## 8. Out of scope (NOT in this slice)

- **xUnit v3 actual coverage path** — deferred per decision §6. v3 detection
  emits warning + runs without coverage; that's all this slice does for v3.
- **NUnit / MSTest adapters** — deferred per decision §"Why no separate
  `MstestAdapter` / `NunitAdapter`". Future additive slices.
- **Solution-level multi-project execution** — single `.csproj` only for v1.
  Multi-`.csproj` workspaces get `ambiguous-project-layout` warning +
  first-csproj selection.
- **Multi-TFM** — `dotnet test` runs once per target framework; this
  slice handles single-TFM. Multi-TFM aggregation deferred.
- **`--blame` mode** — crash diagnostics flag. Not needed for v1.
- **R2 large-suite performance validation** — deferred per §5 above.
- **`--coverage-granularity=aggregate` opt-down flag** — defer until NFR
  actually violated.
- **`dotnet-coverage` (Microsoft first-party static instrumentation)** —
  alternative to Coverlet; out of scope. Future slice if user demand.
- **Retroactive CLI smoke backfill for pytest/jest/gotest** — equip-and-
  exercise §2 binds new adapters from policy date; pre-existing adapters
  optional backfill.

---

## 9. Equip-and-exercise §2.5 binding (compliance reminder)

This slice's diff modifies BOTH `src/novetest/run/adapters/dotnet_adapter.py`
AND `tests/integration/run/test_dotnet_*.py` → §2.5 IS BINDING.

**Run team's pre-handoff gate requirements:**

1. **Equipped host** — must have `dotnet --version >= 8.0` resolvable.
   Both this checkout's host (yjshin@$current) and the other equipped
   host have `~/.dotnet/dotnet` 8.0.421. Source any toolchain script if
   needed (`source ~/.local/share/novetest-toolchains.sh` on either).
2. **Toolchain version detection** — handoff §"Pre-handoff gate environment"
   section MUST list:
   - `dotnet --version` (must be >= 8.0)
   - User-resolved `coverlet.collector` version in the fixture (must be >= 6.0.2)
3. **Engine-specific integration counts** — handoff MUST report:
   - `uv run pytest -v tests/integration/run/test_dotnet_*.py` → **N passed, 0 skipped, 0 failed**
4. **Skip-gate exits zero on equipped host** — `shutil.which("dotnet")` must
   resolve. If skip count > 0 on the dotnet integration cases, the gate
   FAILS regardless of pass count.

§2.5 was empirically validated on JUnit hotfix-3 cycle + cargo CLI
orchestration cycle. Two clean validations. Don't be the third hotfix
because §2.5 wasn't honored.

---

## 10. Open items / suggestions for PM (post-handoff)

Run team's handoff SHOULD surface (and PM verifies + acts on):

### 10.1 dev-host-setup.md §6 update

Current §6 prescribes Microsoft package feed + Ubuntu 22.04. Reality:
both equipped hosts use user-local install. Recommend the handoff
update §6 to:

- Move user-local `dotnet-install.sh` path to primary recommendation
- Keep apt-feed path as alternative for system-wide installs
- Add a per-floor-bump check that the user-local path version meets matrix floor

### 10.2 .NET adapter cycle closes Phase 2.5

After this cycle closes, all 6 native engines are production-ready.
PM should update:

- `design/implementation-plan/delivery-phasing.md` — if any "all six adapters" narrative still has unchecked Phase 2.5 / Phase 3 status, tick at cycle close
- Phase 3 entry condition narrative

### 10.3 Backlog items inherited (JUnit + cargo cycles, not blocking)

If this cycle exposes any of these, surface in handoff:
- Jest node_modules / worktree heuristic (cargo cycle backlog item #1)
- `adapter-unparseable-output` umbrella split candidacy (cargo cycle backlog item #2 — likely trigger is dotnet's VSTest-specific signals)
- Gradle 9.x verification (JUnit cycle backlog)
- `.gradle/` `.gitignore` entry (trivial cleanup)
- JDK 11 readiness probe hard-reject (separate cycle)

---

## 11. Decisions referenced

| Decision | Honored as |
|---|---|
| `2026-06-03-coverlet-pertestcoverage-key.md` §1 | runsettings XML verbatim |
| `2026-06-03-coverlet-pertestcoverage-key.md` §2 | Coverlet 6.0.2 floor + `<SingleHit>false</SingleHit>` sibling |
| `2026-06-03-coverlet-pertestcoverage-key.md` §3 | per-test glob `coverage.*.cobertura.xml` |
| `2026-06-03-coverlet-pertestcoverage-key.md` §4 | `dotnet list package --include-transitive --format json` version detection |
| `2026-06-03-coverlet-pertestcoverage-key.md` §5 | aggregate fallback when < 6.0.2 OR absent |
| `2026-06-03-coverlet-pertestcoverage-key.md` §6 | xUnit v3 detection + `xunit-v3-coverage-deferred` warning |
| `2026-06-03-coverlet-pertestcoverage-key.md` R1 | parametrized-fixture slug-correlation probe in DoD |
| `2026-06-03-coverlet-pertestcoverage-key.md` R3 | tabular fallback for SDK < 7.0 |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1` | Manual Test re-pass on equipped host |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2` | 2 CLI-level smokes with skip-gate on `shutil.which("dotnet")` |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5` | Pre-handoff gate on equipped host; engine integration cases skip=0, fail=0 |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §4` | Gate-A: tool floor (dotnet 8.0) + plugin floor (coverlet 6.0.2) both checked |
| `2026-05-25-supported-engine-matrix.md` | .NET SDK 8.0 floor; xUnit 2.6 floor; Microsoft.NET.Test.Sdk 17.6 floor; Coverlet 6.0.2 floor |
| `2026-05-30-native-result-metadata-slot.md` | `metadata.native_exit_code` populated |

---

## 12. Effective date / expected delivery

Brief queued 2026-06-05. Run team picks up on CEO dispatch. Expected
single-cycle close with no hotfixes (JUnit + cargo experience reused).
On clean close: Phase 2.5 native engine work complete; 6/6 adapters
production-ready; Phase 3 entry condition met.
