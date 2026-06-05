---
from: novetest-manual-test-team
to: novetest-pm-team
type: finding
status: complete
created: 2026-06-05
slug: phase2.5-dotnet-adapter
verdict: failed
verification: agent-comms/verifications/2026-06-05-phase2.5-dotnet-adapter.md
merged_commit: f8f8d93
related:
  - agent-comms/verifications/2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/handoffs/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
---

# Finding — Phase 2.5 .NET / xUnit v2 adapter (`f8f8d93`) — **failed**

## TL;DR

| Item | Result |
|---|---|
| Verdict | **failed** |
| Merged commit verified | `f8f8d93` |
| Pre-merge gate (full suite) | **1137 passed / 2 failed / 0 skipped in 61.19s** — verification doc expected 1136+3+0 |
| Pre-merge gate (dotnet focus) | **3 passed / 2 failed / 0 skipped in 9.59s** — verification doc expected 5+0+0 |
| `mypy --strict src` | (not re-run after first failure; was clean per Main Branch's gate at 91 files) |
| **Scenario A** (`novetest run .`) | **PASS** — exit 3, all envelope fields per spec |
| **Scenario B** (bare `novetest run`) | **PASS** — exit 3, workspace classification |
| **Scenario C** (coverage path) | **FAIL** — `coverage_xml=None`, no `runsettings` artifact, Coverlet not invoked despite `--coverage` flag |
| Equip-and-exercise decision §1 (smoke-gate actually executed) | **Satisfied** — dotnet 8.0.421 + Coverlet 6.0.2 cached, fully equipped; defect is *not* host-equip-related |

**One verdict-blocking defect (D1) and one verification-doc-vs-actual mismatch (D2) surfaced.** D1 is the primary blocker — Coverlet detection fails on a freshly-copied fixture because the adapter's `_probe_coverlet_version` runs **before** `dotnet test` (and `dotnet list package` requires `obj/project.assets.json` from a prior restore).

## What was tested (CEO-readable narrative)

The Phase 2.5 .NET / xUnit v2 adapter is the 6th and last native engine for Nove Test's MVP. It ships three things: (1) the basic `dotnet test` path that runs xUnit tests and parses TRX output; (2) the coverage path that emits a per-run `coverlet.runsettings` and invokes Coverlet via the XPlat data collector; (3) version-floor enforcement for Coverlet (≥ 6.0.2) and xUnit v3 deferral with a structured warning.

I verified all three on this equipped host (dotnet SDK 8.0.421, xUnit 2.6.0, Coverlet 6.0.2, Microsoft.NET.Test.Sdk 17.8.0 — all matrix-floor compliant; NuGet packages all cached locally; toolchain script sourced).

**The basic path is solid.** Scenarios A and B (the two CLI-level smoke runs against the no-coverage fixture) pass cleanly with the exact envelope shape Main Branch's verification doc anticipates. The adapter correctly:
- Records `engine_name = "xunit"` (the engine identity rule from decision `2026-05-25-supported-engine-matrix`).
- Preserves the user's `target_expression` and `target_type` on the audit trail.
- Captures xUnit's `[Theory]` parametrized test identity verbatim (`MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)`) — a load-bearing property for downstream SBFL fingerprinting.
- Populates all three required `metadata` keys: `dotnet_sdk_version`, `native_exit_code`, `xunit_version`.

**The coverage path is broken on a clean machine.** When I run `novetest run --coverage .` against a freshly-copied coverage fixture, the adapter:
1. Tries to detect the user's resolved Coverlet version by running `dotnet list package --include-transitive --format json` on the test csproj.
2. That command fails with `"No assets file was found... Please run restore before running this command"` because the freshly-copied fixture has no `obj/project.assets.json` yet (restore hasn't run).
3. The adapter swallows the failure silently (probe returns `None`).
4. Because Coverlet appears "absent", the adapter then issues an `engine-misconfigured` warning saying *"coverage was requested but `coverlet.collector` is not in the project's package graph"* — even though it IS in the csproj at version 6.0.2.
5. The adapter then **does not pass `--collect:"XPlat Code Coverage"` to `dotnet test`**, **does not generate the per-run `coverlet.runsettings`**, and **does not collect any coverage data**.
6. From the CEO's perspective: `novetest run --coverage` silently degrades to a no-coverage run, with the user having no idea why the cobertura XML they expected never materialized.

I confirmed the diagnosis empirically by doing the missing step manually: a one-line `dotnet restore` before `novetest run --coverage` flips the adapter from "no coverage" to "full coverage" — Coverlet 6.0.2 is detected, runsettings lands, cobertura XML is emitted. The bug is exactly that `_probe_coverlet_version` runs against a project that hasn't been restored, on the very first invocation.

This is the canonical case the equip-and-exercise decision was written to catch: the unit-level tests for the adapter pass (they mock `dotnet list package`), and on Main Branch's machine the integration tests passed too — presumably because their fixture's `obj/` directory was leftover from a prior `dotnet build` or restore in the same pytest session (or in a shared NuGet local cache for the project's csproj). On a clean Manual Test rerun on a properly equipped host, both integration tests fail and the CLI scenario silently degrades.

A secondary observation surfaces too (D2): the verification doc expects `run_record.coverage_xml` to be a non-empty list of paths. In my pre-restored Scenario-C reproduction the cobertura XML *does* land on disk and the path *is* recorded in `artifact_paths['coverage_xml']` (singular string) — but `run_record.coverage_xml` itself is still `None`. Either the verification doc's field-name expectation is inaccurate, or the adapter is supposed to populate that field and doesn't. Calling it out for PM disposition; not necessarily a defect.

## Environment

```
host           : equipped via ~/.local/share/novetest-toolchains.sh
HEAD           : f8f8d93 (FF-merged from run-team/phase2.5-dotnet-adapter onto 23b9d90)
dotnet SDK     : 8.0.421 (~/.dotnet/dotnet — user-local install)
DOTNET_ROOT    : ~/.dotnet
nuget cache    : ~/.nuget/packages — fully prewarmed
xunit          : 2.6.0 (in cache; pinned by fixture)
Microsoft.NET.Test.Sdk : 17.8.0 (in cache; pinned by fixture)
coverlet.collector     : 6.0.0, 6.0.2, 6.0.4 (in cache; fixture pins 6.0.2)
xunit.runner.visualstudio : 2.5.3
python         : 3.11.15 (uv-managed)
```

The host was confirmed equipped BEFORE running verification (per CEO's preceding instruction). No installation changes were made for this verification — the dotnet SDK and all NuGet packages were already in place from the prior cycle.

## Commands run + observed output

### 1. Pre-merge gate (full suite)

```sh
source ~/.local/share/novetest-toolchains.sh
uv run pytest -q tests/unit tests/integration
# Result: 1137 passed + 2 failed + 0 skipped in 61.19s (vs doc-expected 1136+3+0)
# Failures:
#   tests/integration/run/test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml
#   tests/integration/run/test_dotnet_coverage.py::test_coverage_runsettings_landed_under_artifact_dir
```

The +1 vs doc-expected (1137 instead of 1136) is the jest-fixture-`node_modules`-already-installed effect from the prior cycle (consistent with the cargo cycle's "Gotcha #3" pattern). Not regression-relevant.

### 2. Pre-merge gate (dotnet-focused)

```sh
uv run pytest -v tests/integration/run/test_dotnet_basic.py tests/integration/run/test_dotnet_coverage.py
# Result: 3 passed + 2 failed + 0 skipped in 9.59s (vs doc-expected 5+0+0)
# PASSED:
#   test_dotnet_basic.py::test_basic_run_passes_two_fails_one_metadata_present
#   test_dotnet_basic.py::test_cli_smoke_run_dot_emits_envelope
#   test_dotnet_basic.py::test_cli_smoke_run_bare_emits_envelope
# FAILED:
#   test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml
#     AssertionError: assert None == '6.0.2'
#     (result.payload["coverlet_version"] is None, expected "6.0.2")
#   test_dotnet_coverage.py::test_coverage_runsettings_landed_under_artifact_dir
#     AssertionError: assert "runsettings" in result.artifact_paths
#     (artifact_paths has only: stdout, stderr, trx, results_dir)
```

§2.5 mandate — "skip count for the engine's integration cases MUST be 0; failure count MUST be 0" — **not satisfied**. 2/5 dotnet integration tests fail with the canonical fixture, on a properly equipped host.

### 3. Scenario A — `novetest run .` (basic, no coverage) — PASS

```sh
cd /tmp && rm -rf dotnet-sut
cp -r .../tests/fixtures/projects/dotnet-test-basic dotnet-sut
cd dotnet-sut
uv run --project .../Nove-Test novetest init
uv run --project .../Nove-Test novetest run . > /tmp/dotnet-run-dot.json
# exit=3
```

Envelope key fields (verbatim observed):
- `ok = true`, `errors = []`
- `engine_name = "xunit"` ✓
- `engine_version = "8.0.421"` ✓
- `target_expression = "."`, `target_type = "directory"` ✓
- `summary_counts = {errored: 0, failed: 1, passed: 2, skipped: 0, total: 3}` ✓
- `status = "failed"` ✓
- `metadata = {dotnet_sdk_version: "8.0.421", native_exit_code: 1, xunit_version: "2.6.0"}` ✓ (all three required keys present)
- `test_results[]` contains all three expected `node_id`s including the parametrized `TestParametrized(a: 1, b: 2, expected: 3)` ✓

Verification doc's assertion script ran clean: **`Scenario A PASS`**.

### 4. Scenario B — bare `novetest run` (control) — PASS

```sh
cd /tmp/dotnet-sut
uv run --project .../Nove-Test novetest run > /tmp/dotnet-run-bare.json
# exit=3
```

- `target_expression = ""`, `target_type = "workspace"` ✓
- All other fields identical to Scenario A ✓

Verification doc's assertion script ran clean: **`Scenario B PASS`**.

### 5. Scenario C — coverage path — **FAIL**

```sh
cd /tmp && rm -rf dotnet-cov-sut
cp -r .../tests/fixtures/projects/dotnet-test-basic-coverage dotnet-cov-sut
cd dotnet-cov-sut
uv run --project .../Nove-Test novetest init
uv run --project .../Nove-Test novetest run --coverage . > /tmp/dotnet-run-cov.json
# exit=3
```

**Observed envelope** (key fields):
```
ok = true
errors = []
metadata = {dotnet_sdk_version: "8.0.421", native_exit_code: 1, xunit_version: "2.6.0"}
                              ^^^ NOTE: no coverlet_version, no coverage_mapping_granularity
coverage_xml = None
warnings = None
artifact_paths keys = ['results_dir', 'stderr', 'stdout', 'trx']
                              ^^^ NOTE: no 'runsettings', no 'coverage_xml'
summary_counts = {errored:0, failed:1, passed:2, skipped:0, total:3}  (test execution still happens)
```

**Verification doc expectations** (all unmet):
- `run_record.coverage_xml` non-empty list → got `None` ✗
- `runsettings` file staged under `artifact_dir/native/` → not generated ✗
- Aggregate cobertura xml emitted → not emitted ✗
- `metadata.coverlet_version = "6.0.2"` → key absent entirely ✗

Inspection of the artifact directory confirms the adapter ran `dotnet test` **without** any `--collect` argument — no XPlat collector activity in stdout, no `*.cobertura.xml`, no `coverlet.runsettings`. The user's `--coverage` flag was effectively ignored.

### 6. Root cause bisection — pre-restore workaround proves the defect

```sh
cd /tmp && rm -rf dotnet-cov-restored
cp -r .../tests/fixtures/projects/dotnet-test-basic-coverage dotnet-cov-restored
cd dotnet-cov-restored

# THE WORKAROUND — manual restore before invoking novetest
dotnet restore MathLib.Tests/MathLib.Tests.csproj
# Restored MathLib + MathLib.Tests in <1s

uv run --project .../Nove-Test novetest init
uv run --project .../Nove-Test novetest run --coverage . > /tmp/dotnet-run-cov-prestrore.json
# exit=3
```

**Now** the envelope contains everything Scenario C expected:
```
metadata = {coverage_mapping_granularity: "aggregate", coverlet_version: "6.0.2",
            dotnet_sdk_version: "8.0.421", native_exit_code: 1, xunit_version: "2.6.0"}
artifact_paths keys = ['coverage_xml', 'results_dir', 'runsettings', 'stderr', 'stdout', 'trx']
artifact_paths['runsettings']  = run/artifacts/.../native/coverlet.runsettings
artifact_paths['coverage_xml'] = run/artifacts/.../native/TestResults/<guid>/coverage.cobertura.xml
```

And the actual files land on disk:
```
.../native/coverlet.runsettings
.../native/TestResults/<guid>/coverage.cobertura.xml
.../native/TestResults/<guid>/coverage.opencover.xml
.../native/TestResults/<guid>/coverage.info
.../native/TestResults/<guid>/coverage.json
```

The single one-line difference (`dotnet restore` before `novetest run`) flips the entire coverage path from "silently broken" to "fully working". That bisection conclusively pins the defect.

### 7. Smoking-gun confirmation — direct `dotnet list package` probe

To confirm the failure mode is exactly what `_probe_coverlet_version` sees:

```sh
cd /tmp && rm -rf dotnet-probe
cp -r .../tests/fixtures/projects/dotnet-test-basic-coverage dotnet-probe
cd dotnet-probe
# (no restore performed — same state the adapter's pre-test probe sees)
dotnet list MathLib.Tests/MathLib.Tests.csproj package --include-transitive --format json
```

Output:
```json
{
  "version": 1,
  "parameters": "--include-transitive",
  "problems": [
    {
      "project": ".../MathLib.Tests.csproj",
      "level": "error",
      "text": "No assets file was found for `.../MathLib.Tests.csproj`. Please run restore before running this command."
    }
  ],
  "projects": [{"path": ".../MathLib.Tests.csproj"}]
}
```

The `projects[]` has no `frameworks`, so `_parse_coverlet_version_from_json` finds no `coverlet.collector` entry and returns `None`. The adapter's exit code from that subprocess is 0 (the JSON-format command returns success even on the "problems" path), so the parser path is taken — not the tabular fallback. And the parser, looking only for `topLevelPackages` / `transitivePackages`, has nothing to iterate.

The defect is structural and 100% reproducible on a fresh fixture.

## Issues found

### D1 (verdict-blocking) — `_probe_coverlet_version` requires restore state that doesn't exist yet

**Severity**: P0 — verdict-blocker. Coverage flag silently no-ops on every clean invocation.

**Location**: `src/novetest/run/adapters/dotnet_adapter.py:616-705` (the `_probe_coverlet_version` function), invoked from line 299 in the main adapter flow.

**Root cause**: The probe runs `dotnet list <csproj> package --include-transitive --format json` **before** `dotnet test`. `dotnet list package` requires `obj/project.assets.json`, which is generated by `dotnet restore`. On a freshly-copied user project (or the canonical integration test fixture, which is freshly `shutil.copytree`'d every test), this file does not exist yet, so the command emits a "No assets file" `problems[]` entry with empty `projects[].frameworks[]`, the parser returns `None`, and the adapter treats Coverlet as absent.

**User-visible symptom**: `novetest run --coverage` silently produces a no-coverage envelope (no `coverage_xml`, no `runsettings`, no `coverlet_version` in metadata) with no error message in `errors[]` and `warnings: null` at envelope level. The "engine-misconfigured: coverlet absent" warning the adapter emits in its internal `NativeResult.payload.warnings` does not propagate to the envelope's top-level `warnings` field on this code path.

**Reproducer** (minimal):
```sh
source ~/.local/share/novetest-toolchains.sh
cd /tmp && rm -rf dotnet-repro
cp -r .../tests/fixtures/projects/dotnet-test-basic-coverage dotnet-repro
cd dotnet-repro
uv run --project .../Nove-Test novetest init
uv run --project .../Nove-Test novetest run --coverage . | jq '.data.memory_entry.run_record.metadata'
# Expected (per spec): {coverlet_version: "6.0.2", coverage_mapping_granularity: "aggregate", ...}
# Actual:              {dotnet_sdk_version, native_exit_code, xunit_version} only — no coverlet_version
```

**Workaround proof**:
```sh
# Adding `dotnet restore` BEFORE novetest run flips the entire path from broken to working:
dotnet restore MathLib.Tests/MathLib.Tests.csproj
uv run --project .../Nove-Test novetest run --coverage . | jq '.data.memory_entry.run_record.metadata'
# Now: coverlet_version=6.0.2 ✓, coverage_mapping_granularity=aggregate ✓
```

**Fix shape suggestion** (for PM dispatch to Run team — Manual Test does not modify source):
The adapter could either (a) run `dotnet restore` itself before the probe, or (b) move the coverlet detection to AFTER `dotnet test` (which performs an implicit restore as a side effect) by parsing the resolved version from a different source (e.g., MSBuild diagnostic output, or inspecting the produced `bin/<config>/<tfm>/<test>.deps.json`), or (c) emit a structured `engine-misconfigured` warning at the envelope level when the probe returns None despite `--coverage` being requested, so the user at least knows something is off instead of silently getting an empty coverage envelope. PM judgment call on which path; Run team has the architectural context to pick.

**Why Main Branch's gate didn't see this**: An open question. Their gate reported 5/5 dotnet integration tests passing. The most likely explanations: (a) prior test-session state on their host left `obj/` directories or a usable NuGet local-cache state that survived between fixture copies in ways I haven't reproduced; or (b) a global `nuget.config` / MSBuild setting that affects `dotnet list package` behavior in the no-restore case. I cannot diagnose their host from here. But on my equipped host — which has every matrix-floor binary and every required NuGet package cached — the defect reproduces 100% of the time on a fresh fixture copy. The equip-and-exercise decision is functioning exactly as designed by surfacing this from a clean smoke run.

### D2 (informational, possibly verification-doc inaccuracy) — `run_record.coverage_xml` vs `artifact_paths.coverage_xml`

**Severity**: Informational. May be a doc-shape issue rather than a code defect.

**Observation**: With the pre-restore workaround applied, coverage works end-to-end (cobertura XML lands on disk). But:
- Verification doc expects: `run_record.coverage_xml` is a **non-empty list of paths**.
- Actual: `run_record.coverage_xml = None`. The path lives in `run_record.artifact_paths['coverage_xml']` as a **single string** (not a list).

It's plausible the verification doc author conflated the run_record-level field with the artifact_paths map. Or the adapter is supposed to populate `run_record.coverage_xml` and doesn't. Or the field's shape (list vs string) is by-design but mis-documented.

**Recommendation**: PM clarifies whether `run_record.coverage_xml` is a real field or a doc-error; if real, this becomes a P1 follow-up for Run team.

## Recommendations for PM

1. **Kick back to Run team for hotfix on D1.** This is verdict-blocking. The hotfix is small (a one-line `dotnet restore` call or a probe-timing change). The verification suite already pins it structurally (the two failing integration tests are the gate); they will go green when D1 is fixed.

2. **Investigate D2 with Run team for doc-or-code clarification.** Either:
   - Correct the verification doc's expectation (use `artifact_paths['coverage_xml']` as the assertion target), OR
   - Add the missing `run_record.coverage_xml` populator in the adapter.

3. **Treat this cycle as the third equip-and-exercise dividend.** This is the third consecutive adapter cycle (JUnit hotfix #1 → cargo CLI orchestration → this .NET cycle) where the equip-and-exercise decision (`2026-06-04`) caught a verdict-blocking defect that the unit suite, the adapter-direct tests, and even the merged-machine integration suite all missed. The pattern is consistent: any time the adapter has logic that depends on user-project state being initialized (Maven/Gradle's pre-existing artifacts, cargo's nextest invocation conventions, .NET's restore-before-list precondition), unit-level mocking is insufficient and only a clean E2E reproduction surfaces the defect. Strong evidence that the decision should stay in force through Phase 3 and beyond.

4. **Optional: ask Run team to investigate why Main Branch's gate passed 5/5 on the same fixture.** Their host has some state (NuGet config? Prior session artifacts?) that masks D1. If that state is reproducible deliberately, it could become a guardrail; if not, the discrepancy is a Process Gotcha worth recording — pre-merge gates on developer machines can be more lenient than fresh Manual Test machines, and the verification doc workflow should account for that.

5. **Do not yet move task / handoff / verification → history.** Cycle remains open until D1 hotfix lands + clean re-pass on equipped host.

## Artifacts preserved (on equipped host)

For PM/CEO cross-reference:
- `/tmp/dotnet-run-dot.json` — Scenario A envelope (PASS, basic path)
- `/tmp/dotnet-run-bare.json` — Scenario B envelope (PASS, workspace classification)
- `/tmp/dotnet-run-cov.json` — Scenario C envelope (**FAIL**, broken coverage path)
- `/tmp/dotnet-run-cov-prestrore.json` — Scenario C with pre-restore workaround (proves D1 root cause)
- `/tmp/dotnet-cov-sut/.novetest/run/artifacts/run_*/native/stdout.log` — captured `dotnet test` output showing NO `--collect` argument was passed
- `/tmp/dotnet-cov-restored/.novetest/run/artifacts/run_*/native/TestResults/*/coverage.cobertura.xml` — proof that coverage works end-to-end once D1's precondition is satisfied

Manual Test charter: these are scratch (ephemeral, not committed). If PM wants any preserved in history/, please call out which.

---

Verdict: **failed**. Cycle remains open; D1 hotfix required before re-pass.
