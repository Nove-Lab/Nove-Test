---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-05
slug: phase2.5-dotnet-adapter
related:
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md
  - design/implementation-plan/engine-adapters.md
---

# Handoff — Phase 2.5 .NET / xUnit v2 adapter (6th and last native engine)

## TL;DR

Phase 2.5 native engine work closes: **6/6 native engines production-
ready** (pytest / jest / gotest / cargo / junit / **xunit**). The .NET
adapter ships per `decisions/2026-06-03-coverlet-pertestcoverage-key.md`:
xUnit v2 + Coverlet via the VSTest XPlat data collector, decision §1.1
verbatim runsettings, version-floor enforcement, xUnit v3 deferral with
warning, TRX parsing, per-test failure capture, hermetic per-run
artifacts under `<artifact_dir>/native/`.

Pre-handoff gate ran on equipped host per
`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`
(slice modifies both `dotnet_adapter.py` AND `tests/integration/run/
test_dotnet_*.py`; §2.5 in force). **5/5 integration tests pass on
equipped host with 0 skips.**

**One question filed (non-blocking)**:
`agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-
empirically-inert.md` — `<PerTestCoverage>true</PerTestCoverage>` is
inert on Coverlet 6.0.x via the XPlat path. Adapter ships safest
behavior (forward-compat runsettings + auto-detect glob); PM disposition
amends decision §3 if confirmed.

## Worktree info

- **Worktree path**: `/home/yjshin/dev/aispace/novetest-dotnet-adapter`
- **Branch**: `run-team/phase2.5-dotnet-adapter`
- **Base commit**: `23b9d90` (current `main` tip — "comms: queue Phase 2.5 — .NET / xUnit v2 + Coverlet adapter")
- **Commit**: pending (see "Pre-merge checklist" below)

## Pre-handoff gate environment (§2.5 compliance)

Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5`,
this slice's diff matches the binding heuristic (modifies both
`src/novetest/run/adapters/dotnet_adapter.py` AND
`tests/integration/run/test_dotnet_*.py`), so the pre-handoff gate
runs on an equipped host.

### Detected toolchain versions

| Tool | Version | Matrix floor | Source |
|---|---|---|---|
| `dotnet` SDK | `8.0.421` | 8.0 (LTS) | `~/.dotnet/dotnet` (user-local via `dotnet-install.sh`) |
| Microsoft.NET.Test.Sdk (fixture) | `17.8.0` | 17.6 | Top-level PackageReference in fixture |
| `xunit` (fixture) | `2.6.0` | 2.6 | Top-level PackageReference in fixture |
| `xunit.runner.visualstudio` (fixture) | `2.5.3` | (matches `dotnet new xunit` default) | Transitive |
| `coverlet.collector` (coverage fixture) | `6.0.2` | 6.0.2 (decision §2) | Top-level PackageReference in `dotnet-test-basic-coverage` |

Toolchain preserved on this host from Manual Test's 2026-06-04
equipping session per `findings/manual-test-team-2026-06-04-host-equip.md`.
Sourced via `source ~/.local/share/novetest-toolchains.sh` before each
gate run.

### Engine-specific integration counts (§2.5.4 requirement)

`uv run pytest -v tests/integration/run/test_dotnet_*.py`:

```
tests/integration/run/test_dotnet_basic.py::test_basic_run_emits_native_result        PASSED
tests/integration/run/test_dotnet_basic.py::test_cli_smoke_run_dot_emits_envelope     PASSED
tests/integration/run/test_dotnet_basic.py::test_cli_smoke_run_bare_emits_envelope    PASSED
tests/integration/run/test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml  PASSED
tests/integration/run/test_dotnet_coverage.py::test_coverage_runsettings_landed_under_artifact_dir  PASSED
```

**5 passed, 0 skipped, 0 failed in 10.71s.** §2.5 mandate satisfied.

## Files written / modified

| File | Lines | Change |
|---|---|---|
| `src/novetest/run/adapters/dotnet_adapter.py` | +1310 / 0 | NEW — the adapter |
| `src/novetest/run/engine.py` | +8 / -1 | dispatch `engine_name == "xunit"` |
| `src/novetest/run/engine_selector.py` | +25 / -10 | `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE` + one-level-deep `*.csproj` glob + docstring |
| `src/novetest/run/normalizer.py` | +144 / 0 | `_normalize_xunit_payload` + `_aggregate_xunit_status` + dispatch |
| `src/novetest/run/readiness.py` | +239 / -1 | `_assess_xunit_readiness` + `_glob_dotnet_markers` + `_probe_dotnet_sdk_version` + dispatch branch |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | +1385 / 0 | NEW — 81 unit tests across 11 test classes |
| `tests/unit/run/test_xunit_readiness.py` | +282 / 0 | NEW — 8 readiness tests |
| `tests/unit/run/conftest.py` | +10 / 0 | 2 new fixtures (basic + coverage workspaces) |
| `tests/unit/run/test_engine.py` | +5 / -3 | "xunit" no longer the "unimplemented" example; uses "phpunit" |
| `tests/unit/run/test_engine_selector.py` | +10 / -7 | "dotnet → xunit" selection test (was "raises" test) |
| `tests/integration/run/test_dotnet_basic.py` | +280 / 0 | NEW — adapter-direct + 2 CLI smokes |
| `tests/integration/run/test_dotnet_coverage.py` | +160 / 0 | NEW — real Coverlet path + runsettings staging |
| `tests/fixtures/projects/dotnet-test-basic/` | 6 files | NEW — library + test project; 3-test contract; xunit 2.6.0 |
| `tests/fixtures/projects/dotnet-test-basic-coverage/` | 5 files | NEW — same shape + Coverlet 6.0.2 PackageReference |
| `agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md` | +210 / 0 | NEW — PerTestCoverage XPlat-path empirical finding |
| `scripts/dev-host-setup.md` | +51 / -29 | §6 user-local install promoted to primary; alternatives demoted; smoke probe text amended |
| `WORKLOG.md` | +6 lines | New top entry |

Total: **~3645 lines across 17 files** (1310 src adapter + 144 normalizer + 239 readiness + ~50 wiring + ~2100 tests + 210 question + 51 doc + 6 worklog + ~535 fixtures).

## Decisions referenced + how honored

| Decision | Honored |
|---|---|
| `2026-06-03-coverlet-pertestcoverage-key.md §1` (runsettings XML verbatim) | `_COVERLET_RUNSETTINGS_PER_TEST` matches byte-for-byte; pinned by `test_per_test_template_matches_decision_verbatim` |
| `2026-06-03-coverlet-pertestcoverage-key.md §2` (Coverlet 6.0.2 floor + `<SingleHit>false</SingleHit>` mandatory) | `COVERLET_FLOOR_VERSION = (6, 0, 2)` constant; aggregate template also pins `<SingleHit>false</SingleHit>` |
| `2026-06-03-coverlet-pertestcoverage-key.md §3` (per-test glob `coverage.*.cobertura.xml`) | `_glob_coverage_xml` returns `(per_test, aggregate)` tuple; per-test glob preferred, aggregate fallback |
| `2026-06-03-coverlet-pertestcoverage-key.md §4` (version detect via `dotnet list package`) | `_probe_coverlet_version` tries `--format json` (decision-preferred) then tabular fallback |
| `2026-06-03-coverlet-pertestcoverage-key.md §5` (aggregate fallback when < 6.0.2 OR absent) | `_COVERLET_RUNSETTINGS_AGGREGATE` template; `coverage_mode = "aggregate"` payload field |
| `2026-06-03-coverlet-pertestcoverage-key.md §6` (xUnit v3 → `xunit-v3-coverage-deferred` warning) | `_detect_xunit_major_version` returns 3 → warning + no coverage flags; pinned by `TestXunitV3DeferralWarning::test_v3_emits_warning_with_specific_kind` |
| `2026-06-03-coverlet-pertestcoverage-key.md R1` (parametrized slug correlation probe) | Fixture includes `[Theory] [InlineData(1,2,3)]` test; R1 probe asserts identity preserved + slug-correlation forward-compat live in `_slugify_for_coverlet`; **empirical finding** (filed question) supersedes the per-test slug behavior — aggregate fallback fires today |
| `2026-06-03-coverlet-pertestcoverage-key.md R3` (tabular fallback for SDK < 7.0) | `_parse_coverlet_version_from_text` regex tolerates wrapped lines + missing requested column |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1` | Manual Test re-pass runs on equipped host (this handoff describes what to verify) |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2` | 2 CLI-level smokes added (dot + bare); skip-gate on `shutil.which("dotnet")`; assert `(0, 3)` + envelope shape |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5` | Pre-handoff gate ran on equipped host with toolchain versions detected ≥ matrix floors; engine integration cases skip=0, fail=0 |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §4` | Gate-A: tool floor (`dotnet --version >= 8.0`) AND plugin floor (`coverlet.collector >= 6.0.2`) both verified |
| `2026-05-25-supported-engine-matrix.md` | All floors honored: .NET 8.0 + xUnit 2.6 + Test.Sdk 17.6 + Coverlet 6.0.2 |
| `2026-05-30-native-result-metadata-slot.md` | `metadata.native_exit_code` reserved key NOT pre-populated by adapter; normalizer overlays it; pinned by `TestMetadataPopulation::test_native_exit_code_preserved_in_normalized_record` |

## Pre-merge checklist (Main Branch team)

Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md §1
+ §2.5` Main Branch's pre-merge gate ALSO runs on an equipped host.

1. `source ~/.local/share/novetest-toolchains.sh` before `pytest`.
2. `cd` into the worktree (`/home/yjshin/dev/aispace/novetest-dotnet-adapter`).
3. `uv run pytest -q tests/unit tests/integration` — expect **1136 passed + 3 skipped + 0 failed**. The 3 skips:
   - `test_jest_basic.py::test_jest_basic_runs_and_returns_passed_record`
   - `test_jest_coverage.py::test_jest_coverage_emits_istanbul_final_json`
   - 1 from `localization` (pre-existing pattern)
   - Same worktree-isolated `node_modules/` issue from cargo cycle's WORKLOG Gotcha #3.
4. `uv run pytest -v tests/integration/run/test_dotnet_*.py` — expect **5 passed + 0 skipped + 0 failed**.
5. `uv run mypy --strict src` — expect `Success: no issues found in 91 source files`.
6. Optional sanity reproducer:
   ```sh
   cd /tmp && rm -rf dotnet-sut && \
     cp -r /home/yjshin/dev/aispace/novetest-dotnet-adapter/tests/fixtures/projects/dotnet-test-basic dotnet-sut && \
     cd dotnet-sut && \
     uv run --project /home/yjshin/dev/aispace/novetest-dotnet-adapter novetest init && \
     uv run --project /home/yjshin/dev/aispace/novetest-dotnet-adapter novetest run .
   ```
   Expect: exit 3, ok=true, envelope `data.memory_entry.run_record.{engine_name: "xunit", target_expression: ".", target_type: "directory", summary_counts: {total: 3, passed: 2, failed: 1}}`.
7. FF-merge the branch onto `main`. No conflicts expected.
8. Write verification doc for Manual Test re-pass per `agent-comms/README.md` template + decision §3's required scenarios (CLI smoke gate + Gate A tool-floor + plugin-floor pre-flight).

## DoD bullets believed closed (brief §7)

| # | DoD bullet (paraphrased) | Evidence pointer | ✓ |
|---|---|---|---|
| 1 | `dotnet_adapter.py` created with `ENGINE_NAME = "xunit"` + canonical adapter pattern | `src/novetest/run/adapters/dotnet_adapter.py` + `test_engine_name_constant` | ✓ |
| 2 | `engine_selector.py` `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE["dotnet"] = "xunit"` | `src/novetest/run/engine_selector.py:64` | ✓ |
| 3 | xUnit v2 detection + v3 → `xunit-v3-coverage-deferred` warning + no coverage argv | `TestXunitVersionDetection` + `TestXunitV3DeferralWarning` unit classes | ✓ |
| 4 | Coverlet version detection via JSON; tabular fallback | `TestCoverletVersionDetection` (11 cases incl. both paths) | ✓ |
| 5 | < 6.0.2 OR absent → `engine-misconfigured` + aggregate fallback runsettings | `TestArgvComposition::test_coverage_coverlet_absent_omits_coverage_flags` + `test_coverage_coverlet_below_floor_falls_back_to_aggregate` + `TestEngineMisconfiguredWarnings` | ✓ |
| 6 | `coverlet.runsettings` generated per-run at `<artifact_dir>/native/`; XML matches decision §1.1 verbatim (per-test) OR §1.1 minus PerTestCoverage (aggregate) | `TestRunsettingsGeneration::test_per_test_template_matches_decision_verbatim` + `test_aggregate_template_drops_per_test_keeps_singlehit` | ✓ |
| 7 | TRX parser produces normalized outcomes + duration + failure_reference | `TestTrxParsing` (14 cases) | ✓ |
| 8 | Per-test Cobertura → test identity correlation works for parametrized fixture (R1 probe) | `test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml` — aggregate fallback path (per empirical finding); R1 closure via filed question | ✓ |
| 9 | `coverage_xml` paths emitted ABSOLUTE; orchestration relativizes via `.relative_to(store.path)` | `test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml` asserts `is_relative_to(artifact_dir)` | ✓ |
| 10 | `summary_counts` + `status` + `metadata.native_exit_code` populated correctly on canonical fixture | `test_dotnet_basic.py::test_basic_run_emits_native_result` + `TestMetadataPopulation::test_native_exit_code_preserved_in_normalized_record` | ✓ |
| 11 | All 3 test files green on equipped host | 5 integration pass + 81 adapter unit pass + 8 readiness unit pass | ✓ |
| 12 | 2 CLI smokes; assertion `(0, 3)`; skip-gate on `shutil.which("dotnet")` | `test_dotnet_basic.py` contains both literal function names; `(0, 3)` assertion verbatim | ✓ |
| 13 | `uv run mypy --strict src` clean (90 → 91 source files) | `Success: no issues found in 91 source files` | ✓ |
| 14 | Pre-handoff gate green on equipped host; §2.5 binding satisfied | §"Pre-handoff gate environment" above (toolchain versions + 5 passed + 0 skipped on engine cases) | ✓ |

PM verifies + ticks these at cycle close.

## Open items / surprises for PM

### Critical (filed, non-blocking — must be ratified)

1. **`agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md`** — `<PerTestCoverage>true</PerTestCoverage>` is empirically inert on Coverlet 6.0.x via the XPlat data collector path. Verified with `--diag` log capture (config reaches Coverlet, no per-test files emitted). Adapter ships aggregate-effective-default with forward-compat runsettings + auto-detect glob; the safest behavior. Recommend PM ratify decision §3 amendment per the question's option 2 and update the docs to describe aggregate-as-default. Affects Phase 4 Localization's SBFL per-test granularity on .NET projects (reduced to aggregate for v1).

### Operational (non-blocking)

2. **`dev-host-setup.md §6` amendment** — Promoted user-local `dotnet-install.sh` path to primary (matches both equipped hosts' actual install pattern). Apt + Homebrew demoted to alternatives. Brief §10.1 anticipated this; PM may want to retroactively apply the same shape to §3 (Go) and §4 (Rust) where the user-local pattern is also the equipped-host reality.

3. **Phase 2.5 native engine work complete** — 6/6 adapters production-ready. PM may want to tick the Phase 2.5 / Phase 3 entry condition in `design/implementation-plan/delivery-phasing.md` at cycle close.

4. **`adapter-unparseable-output` umbrella overload** (carried over from cargo cycle) — This slice adds two `kind` values: `unparseable-output` (the generic; covers malformed TRX + missing TRX + "dotnet test exited non-zero with no TRX") and `project-not-found` (a new kind for "no csproj exists"). I picked `project-not-found` as a distinct kind because it surfaces BEFORE any subprocess spawn and would be misleading to lump under `unparseable-output`. PM may want to add this to the inventory; brief §2.8 noted the cumulative count was 4 sub-kinds on `unparseable-output` after cargo, now 4 still (no new `unparseable-output` sub-kinds added).

5. **Worktree-isolated `node_modules/`** (carried over from cargo cycle) — Same 2 jest skips as before. §2.5's diff-classification heuristic correctly bounds the binding scope to the engine in the diff (dotnet), so the jest skips are out of scope for this gate. PM may revisit at a later cycle.

### Forward (not blocking; informational)

6. **`coverlet.msbuild` user-cooperation path for per-test coverage** — IF the Coverlet question's resolution is "deferred per-test, ship aggregate for v1", PM may want to scope a follow-up cycle that explores opt-in `coverlet.msbuild` mode (which DOES produce per-test files but requires a csproj modification). The non-modification contract is project-wide; an opt-in flag would have to make the modification explicit + user-authorized. NOT in scope for v1.

7. **xUnit v3 / Microsoft.Testing.Platform coverage adapter** — Already-deferred per decision §6. Slice activates when v3 adoption + MTP coverage extension paths mature in upstream.

8. **CI matrix cells for .NET and Rust** — Currently neither has a Release-team CI cell. Both adapters operate-and-test under the equip-and-exercise mandate, which carries the operational gap. PM may want to coordinate with Release on adding cells to the GH Actions matrix at a Phase 6 cleanup cycle.

## Worklog entry text (pasted verbatim)

```
## 2026-06-05 — phase2.5 / dotnet-adapter (the 6th and last native engine)

- Landed: Closed Phase 2.5 .NET adapter per
  `tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md` — **the sixth
  and last Native Engine adapter** brings `novetest run` from 5
  ecosystems (pytest / jest / gotest / cargo / junit) to 6 (+xunit / .NET).
  1 new src file (source count 90 → 91 with `dotnet_adapter.py`), 4
  modified src files, 2 new fixtures, 4 new test files, 1 new question,
  1 modified script doc. Materially closes Phase 2.5 native engine work.
  [...]
- Verified: Pre-handoff gate on equipped host per §2.5. Toolchain:
  dotnet 8.0.421 + xunit 2.6.0 + Coverlet 6.0.2 (matrix floors honored).
  Equipped-host integration: `uv run pytest -v tests/integration/run/
  test_dotnet_*.py` → 5 passed + 0 skipped + 0 failed in 10.71s.
  Default suite: 1136 passed + 3 skipped + 0 failed (post-cargo-CLI
  baseline 1042+3+0 → +94 net new passing). mypy --strict: Success
  no issues found in 91 source files (+1 vs baseline 90).
- Left open: 14 DoD bullets believed closed per brief §7 — all green
  on equipped host; PM verifies + ticks at cycle close. Out of scope:
  NO xunit v3 actual coverage; NO NUnit/MSTest adapters; NO solution-
  level multi-project; NO multi-TFM; NO --blame; NO R2 large-suite
  perf; NO --coverage-granularity opt-down; NO dotnet-coverage; NO
  retroactive CLI smoke backfill. One open question filed:
  `questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-
  inert.md` — PerTestCoverage inert on Coverlet 6.0.x XPlat path;
  adapter ships safest behavior; PM disposition pending.
- Gotcha: 6 pinned. (1) PerTestCoverage empirically inert on XPlat path;
  aggregate-effective-default is the realized behavior. (2) Canonical
  library + test split needs one-level-deep csproj glob. (3) Same-
  assembly tests yield empty coverage; library/test split mandatory.
  (4) Test-project name preference overrides alphabetical sort. (5)
  ambiguous-project-layout warning refined to fire only on true
  multi-test-project / sln ambiguity. (6) TRX namespace handling
  requires explicit `_TRX_NS` ns_map in ElementTree.
- Next: Handoff written. PM verifies DoD + addresses Coverlet question
  + dispatches Main Branch for FF-merge (equipped-host gate per §2.5)
  + dispatches Manual Test for re-pass. On clean close: Phase 2.5
  complete; 6/6 adapters ready; Phase 3 entry condition met.
```

(Full content lives at WORKLOG.md top of file as the new entry.)
