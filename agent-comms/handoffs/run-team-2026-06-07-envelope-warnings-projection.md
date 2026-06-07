---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-07
slug: envelope-warnings-projection
related:
  - agent-comms/tasks/run-team-2026-06-06-envelope-warnings-projection.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
---

# Handoff — envelope-warnings-projection (Option C MVP-blocking slice)

## Worktree / branch / base

| Field | Value |
|---|---|
| Worktree | `/home/yjshin/dev/aispace/novetest-envelope-warnings-projection` |
| Branch | `run-team/envelope-warnings-projection` |
| Base | `130a5eb` (origin/main; "comms: queue 2 parallel MVP-blocking briefs") |
| Tip | will be committed atomically with this handoff |
| Working tree | clean (modulo the staged slice diff) |

## Files written / modified

### Source modifications (10 files)

| File | Shape | Authorization |
|---|---|---|
| `src/novetest/run/types.py` | +`AdapterWarning` dataclass + `NativeResult.warnings` field | Run team charter |
| `src/novetest/run/__init__.py` | re-export `AdapterWarning` | Run team charter |
| `src/novetest/run/engine.py` | `execute()` + `execute_with_engine_context()` return `tuple[RunRecord, tuple[AdapterWarning, ...]]` | Run team charter |
| `src/novetest/run/adapters/dotnet_adapter.py` | 4 emit sites dual-write `payload["warnings"]` + `result_warnings.append(AdapterWarning(...))`; NativeResult passes `warnings=tuple(result_warnings)` | Run team charter |
| `src/novetest/run/adapters/junit_adapter.py` | 2 distinct kinds × 2 build-tool paths = 4 emit sites, same dual-write pattern; new module-level `WARNING_AMBIGUOUS_BUILD_TOOL` + `WARNING_MISSING_JACOCO` constants | Run team charter |
| `src/novetest/orchestration/workflows/run.py` | `RunOutcome.warnings: tuple[AdapterWarning, ...] = field(default_factory=tuple)` + unpack execute() return | **brief §3 cross-team authorization** |
| `src/novetest/orchestration/workflows/test.py` | `TestOutcome.warnings: tuple[AdapterWarning, ...] = ()` + unpack execute() return + propagate to outcome | brief §3 (implicit — outcome consumed by build_test_envelope which §3 authorizes) |
| `src/novetest/cli/app.py` | +`_adapter_to_envelope_warnings(...)` helper + `run_cmd` passes converted warnings to `Envelope(...)` | **brief §3 cross-team authorization** |
| `src/novetest/cli/handlers/test.py` | `build_test_envelope` mirror projection (AdapterWarning → EnvelopeWarning) | brief §2.5 #2 (test_cmd / build_test_envelope explicit) |
| `src/novetest/replay/engine.py` | 1-line mechanical: `record, _ = await execute_with_engine_context(...)` | **NOT explicitly authorized; mechanical consequence of execute() signature change** — see §"Cross-team scope footprint" below |

### Test modifications (3 files)

| File | Change |
|---|---|
| `tests/unit/run/test_engine.py` | 7 call sites updated for `record, warnings = await execute(...)` tuple return; new asserts on `warnings == ()` for plumbing-only adapters |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | 1 site (`record, _warnings = await execute_with_engine_context(...)`) |
| `tests/unit/orchestration/workflows/test_run.py` | `fake_execute` returns `(record, ())` tuple |

### New test files (4 files)

| File | Tests | Purpose |
|---|---|---|
| `tests/unit/run/test_types.py` | 10 (3 classes) | AdapterWarning structural contract (field names match EnvelopeWarning per criterion #3, frozen, details accepts arbitrary types) + projection round-trip + NativeResult.warnings field default/custom/immutable |
| `tests/unit/cli/test_envelope_warnings_projection.py` | 7 (2 classes) | `_adapter_to_envelope_warnings` empty/single/multiple/ordering/dict-copy-isolation/wire-shape + `build_test_envelope` warnings projection (empty/single/multiple) |
| `tests/integration/run/test_dotnet_warnings.py` | 2 | dotnet/`engine-misconfigured` (coverage-absent) via CLI subprocess on copy-of-dotnet-test-basic + `--coverage`; dotnet/`xunit-v3-coverage-deferred` via adapter-direct + stubbed subprocess (CLI smoke for v3 needs MTP infrastructure — adapter-direct is sufficient because the warning emit is csproj-string-driven) |
| `tests/integration/run/test_junit_warnings.py` | 2 | junit/`missing-jacoco` via CLI subprocess on copy-of-junit-maven-basic with jacoco-maven-plugin block stripped; junit/`ambiguous-build-tool` via CLI subprocess on copy-of-junit-maven-basic with added stub build.gradle.kts |

### WORKLOG entry

`WORKLOG.md` — one new top entry dated 2026-06-07.

## Verification (pre-handoff gate per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5)

### Pre-handoff gate environment

| Field | Value |
|---|---|
| Host | YJ-LAPTOP (WSL2-on-Windows; same host used for .NET hotfix #1 §2.5 gate per `findings/manual-test-team-2026-06-06-host-equip.md`) |
| Toolchain shim | sourced via `source ~/.local/share/novetest-toolchains.sh` — banner: `[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5` |
| dotnet | 8.0.421 (matrix floor 8.0 ✓) |
| java | 17.0.19 (matrix floor 17 ✓) |
| mvn | 3.8.7 (matrix floor 3.8 ✓) |
| gradle | 8.5 (matrix floor 7.6 ✓) |
| cargo | 1.96.0 + cargo-nextest 0.9.137 (matrix floor 1.74 + 0.9.50 ✓) |
| python3 | 3.11.15 + uv 0.11.14 (matrix floor 3.11 ✓) |
| node / npm | **MISSING** — jest integration tests skip-gate |
| go | **MISSING** — gotest integration tests skip-gate |

Jest + gotest skip-gates are pre-existing on this host; both adapters emit zero warnings today and the §1.1 catalog does not assign any warning kind to them, so the missing tooling has no functional impact on the slice's binding gates.

### Default suite gate

```
$ uv run pytest -q tests/unit tests/integration
1166 passed, 5 skipped, 0 failed in 170.86s (0:02:50)
```

Baseline post-dotnet-hotfix-#1 (commit `6c7bc76`) was **1145 passed + 5 skipped + 0 failed** → **+21 net new passing tests** from the slice (10 test_types + 7 test_envelope_warnings_projection + 4 test_*_warnings).

Skip breakdown: 2 jest (node missing) + 2 gotest (go missing) + 1 cross-asyncio maven (pre-existing async-engine config issue, unchanged from baseline). All toolchain-driven, none warnings-related.

### Per-warning integration gate (brief §4 binding)

```
$ uv run pytest -v tests/integration/run/test_dotnet_warnings.py tests/integration/run/test_junit_warnings.py
tests/integration/run/test_dotnet_warnings.py::test_cli_smoke_coverage_absent_emits_envelope_warning           PASSED [ 25%]
tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter      PASSED [ 50%]
tests/integration/run/test_junit_warnings.py::test_cli_smoke_missing_jacoco_emits_envelope_warning            PASSED [ 75%]
tests/integration/run/test_junit_warnings.py::test_cli_smoke_ambiguous_build_tool_emits_envelope_warning      PASSED [100%]
4 passed in 17.07s
```

All 4 catalog rows turn into a discrete green test. Skip count = 0; failure count = 0.

### Full integration suite

```
$ uv run pytest -q tests/integration
109 passed, 5 skipped, 0 failed in 161.65s (0:02:41)
```

### mypy strict

```
$ uv run mypy --strict src/novetest
Success: no issues found in 91 source files
```

Unchanged source-file count (91) — slice adds fields to existing types.py, doesn't introduce new source modules.

## CLI smoke envelope captures (brief §4 mandate — dotnet + junit + cargo)

### (a) dotnet — coverage-requested-but-coverlet-absent

**Reproducer**: copy `tests/fixtures/projects/dotnet-test-basic/` into `/tmp/<SuT>`, run `novetest init && novetest run --coverage`.

**`envelope.warnings[]`**:

```json
[
  {
    "code": "engine-misconfigured",
    "details": {
      "coverlet_floor": "6.0.2",
      "csproj": "MathLib.Tests.csproj"
    },
    "message": "coverage was requested but `coverlet.collector` is not in the project's package graph; add <PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" /> (or later 6.0.x) to the .csproj. Coverage data was not collected for this run."
  }
]
```

**Backward-compat criterion #2 — v1 metadata bridge still populated**:

```json
{
  "coverage_unavailable_kind": "coverlet-absent-or-stale",
  "coverage_unavailable_message": "novetest run --coverage was requested but coverlet.collector could not be detected in the project's package graph after `dotnet restore`. The run executed WITHOUT coverage collection. To enable coverage: add <PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" /> (or later 6.0.x) to your test .csproj. If the package IS declared and this warning persists, check the stderr.log artifact for `dotnet restore` errors."
}
```

(Visible at `data.memory_entry.run_record.metadata`.)

Exit code: 3 (EXIT_USER_TESTS_FAILED — fixture has 1 intentionally-failing test; the warning is independent of test outcomes).

### (b) junit — missing-jacoco (Maven path)

**Reproducer**: copy `tests/fixtures/projects/junit-maven-basic/` into `/tmp/<SuT>`, strip the `jacoco-maven-plugin` block from `pom.xml`, run `novetest init && novetest run --coverage`.

**`envelope.warnings[]`**:

```json
[
  {
    "code": "missing-jacoco",
    "details": {
      "build_tool": "maven"
    },
    "message": "coverage was requested but the project's pom.xml does not declare jacoco-maven-plugin; add the plugin (>= 0.8.11) under <build><plugins> in pom.xml. Coverage data was not collected for this run."
  }
]
```

Exit code: 3 (intentional Maven test failure).

### (c) junit — ambiguous-build-tool

**Reproducer**: copy `tests/fixtures/projects/junit-maven-basic/` into `/tmp/<SuT>`, add a minimal `build.gradle.kts` stub (`plugins { id("java") }`), run `novetest init && novetest run`.

**`envelope.warnings[]`**:

```json
[
  {
    "code": "ambiguous-build-tool",
    "details": {
      "chosen_build_tool": "maven"
    },
    "message": "both pom.xml and build.gradle{,.kts} were detected; Maven was chosen as the default tiebreaker per decisions/2026-06-03 ratification of brief §6 D3. To use Gradle instead, remove the Maven manifest or (future) pass --build-tool=gradle."
  }
]
```

Exit code: 3 (Maven runs as the tiebreaker; intentional test failure surfaces same as bare run).

### (d) cargo — no warning emit sites today

Brief §1.1 said "(existing kinds — Run team enumerates)". After grepping `cargo_adapter.py` for warning-emit patterns: **zero kinds**. Plumbing-only: `NativeResult.warnings` defaults to `()`, the envelope projection delivers an empty `warnings: []` field. Verified by the default `tests/unit/run/test_engine.py::test_execute_with_engine_context_dispatches_cargo` which now asserts `warnings == ()`.

If future cargo warnings are added (e.g. the post-MVP "cargo-llvm-cov absent" recommendation case in the 2026-05-31 cargo polish history), they slot into the same dual-channel pattern dotnet + junit already use; no plumbing changes needed.

## Architectural deviation (per brief §2 "Run team may refine")

### `RunOutcome.warnings: tuple[AdapterWarning, ...]` (not `EnvelopeWarning`)

Brief §2.5 literally typed `RunOutcome.warnings: tuple[EnvelopeWarning, ...] = ()`. Implementing that exactly would force `orchestration/workflows/run.py` to `from novetest.cli.output import EnvelopeWarning` — inverting the existing `cli → orchestration → run` dependency direction. Combined with the existing `cli/handlers/test.py → orchestration/workflows/test::TestOutcome` import path, this creates a circular dependency at module load time.

**Resolution**: orchestration layer holds the `AdapterWarning` shape; CLI handler projects to `EnvelopeWarning` at envelope-construction time via the new `_adapter_to_envelope_warnings(...)` helper. The two dataclasses are field-by-field identical per decision criterion #3, so the conversion is one line per warning. Per-test verified in `tests/unit/run/test_types.py::test_adapter_warning_field_names_match_envelope_warning`.

### Normalizer NOT modified — warnings lifted at engine layer

Brief §2.4 PM-preferred design: lift `NativeResult.warnings` at the normalizer. Brief §2.4 also says "Run team has the context to decide cleanly".

The normalizer takes `NativeResult` → returns `RunRecord` (a single value, signature unchanged for 6 engine paths). Adding warnings to the return type forces ~20 call-site rewrites in `tests/unit/run/test_normalizer.py` — pure churn for no behavioral benefit.

**Resolution**: lift warnings at the engine layer (`execute()` reads `native_result.warnings` after the normalizer returns). The normalizer's signature stays clean. The change is localized to engine.py + 7 call sites in test_engine.py. Net test churn ~30 LOC vs ~60+ LOC for the normalizer-layer alternative.

## Cross-team scope footprint (DoD bullet #7)

### Strictly authorized (brief §3)

- `src/novetest/orchestration/workflows/run.py` ✓
- `src/novetest/cli/app.py` ✓

### Implicitly authorized (brief §2.5 references)

- `src/novetest/cli/handlers/test.py` — brief §2.5 #2 explicitly named "test_cmd (build_test_envelope or wherever the envelope is built for the integrated workflow)"; the actual `build_test_envelope` lives here post the 2026-06-02 handler refactor.
- `src/novetest/orchestration/workflows/test.py` — adds `TestOutcome.warnings` field which `build_test_envelope` reads. Mechanically required by the authorized handler change.

### Mechanical adjustment (NOT explicitly authorized)

- `src/novetest/replay/engine.py` — single-line `record, _ = await execute_with_engine_context(...)` tuple unpack. The `_` discards warnings because replay's envelope is the Replay Result block, not a Run Record envelope; the original-run's warnings already surfaced when the original run executed. Behavior unchanged. **The reason this is acceptable**: brief §2.5 "Scope guard" forbids silently expanding scope to other orchestration/CLI files; replay is neither orchestration nor CLI, and the change is a mandatory call-site adjustment forced by the authorized `execute()` signature change. PM should ratify or flag.

If PM wants to keep the execute() signature unchanged, the alternative is to add `execute_returning_warnings()` as a parallel API. This would be a larger surface change and leaves a long-term naming wart; recommend ratifying the current single-API design.

## Brief §1.1 catalog deviation

The brief catalog assigns `engine-misconfigured` to JUnit. After grepping `junit_adapter.py`: **the JUnit adapter does NOT emit `engine-misconfigured` as a payload warning**. That kind is emitted by:

- `.NET adapter`: `WARNING_COVERLET_BELOW_FLOOR: Final[str] = "engine-misconfigured"` + `WARNING_COVERLET_ABSENT: Final[str] = "engine-misconfigured"` — covered by `test_dotnet_warnings.py::test_cli_smoke_coverage_absent_emits_envelope_warning`.
- `Readiness probe (readiness.py)`: surfaces `engine-misconfigured` as `EngineReadinessResult.state` which raises `EngineNotReadyError` and surfaces as `envelope.errors[{"code": "engine-engine-misconfigured"}]`, NOT a warning.

The brief catalog's "JUnit / engine-misconfigured" row appears to be a brief-authoring error — likely confusion between the .NET adapter's `engine-misconfigured` kind and JUnit's readiness-probe misconfig state. **No integration test created for the misattributed JUnit row**; the .NET row IS integration-tested.

## Open items / surprises

1. **`uv run --directory <DIR>` does NOT change cwd for the inner command** — initial ad-hoc smoke capture failed because `uv run --directory /path/to/worktree novetest run` (run from `/tmp/<SuT>`) resolved the manifest from `--directory` but ran novetest's pytest against the worktree (1171 self-tests). Resolution: invoke the venv's python directly via `/path/to/worktree/.venv/bin/python -m novetest run --coverage` with `cd /tmp/<SuT>` as actual cwd. The canonical integration test pattern (`subprocess.run([sys.executable, "-m", "novetest", *args], cwd=workspace)`) avoids this trap; ad-hoc smoke scripts need the same shape. Captured in WORKLOG Gotcha #4.

2. **xUnit v3 CLI smoke deferred to adapter-direct path** — published `xunit` 3.x package requires Microsoft.Testing.Platform infrastructure that the test machine doesn't have. CLI smoke would fail at `dotnet restore`. Adapter-direct + stubbed subprocess covers the same warning-emit path because xUnit v3 detection runs from csproj-string parsing BEFORE any subprocess. Documented in `test_dotnet_warnings.py` module docstring + per-test docstring.

3. **`replay/engine.py` mechanical touch** — single `, _` tuple unpack to consume the new execute() return. Behavior unchanged; PM should ratify the scope footprint.

4. **5 pre-existing skips** stay unchanged: 2 jest (node missing on this host) + 2 gotest (go missing) + 1 maven async-engine (pre-existing cross-asyncio plugin issue). None warnings-related; documented under "Default suite gate" above.

## Pre-merge checklist (Main Branch team)

1. `cd /home/yjshin/dev/Nove-Test`
2. `source ~/.local/share/novetest-toolchains.sh` — confirm banner `dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5`
3. `git fetch origin && git checkout main && git merge --ff-only run-team/envelope-warnings-projection`
4. `uv run mypy --strict src/novetest` — expect `Success: no issues found in 91 source files`
5. `uv run pytest -q tests/unit tests/integration` — expect **1166 passed + 5 skipped + 0 failed** (5 skips: 2 jest + 2 gotest + 1 maven async; toolchain-driven)
6. `uv run pytest -v tests/integration/run/test_dotnet_warnings.py tests/integration/run/test_junit_warnings.py` — expect **4 passed + 0 skipped + 0 failed**
7. Spot-reproduce one CLI smoke (recommended: dotnet coverage-absent) per the reproducer script in §"CLI smoke envelope captures (a)" to confirm `envelope.warnings[].code == "engine-misconfigured"` against the freshly-merged tip.
8. Verification doc: write `agent-comms/verifications/2026-06-07-envelope-warnings-projection.md` with Cap-X format (one Cap per warning kind: Cap-1 dotnet/engine-misconfigured, Cap-2 junit/missing-jacoco, Cap-3 junit/ambiguous-build-tool, Cap-4 cargo/empty-warnings-control). Note that envelope wire-shape now includes a non-empty `warnings: [...]` array for adapter-warning runs — distinct from the pre-slice posture where this field was always empty for run/test envelopes.

## DoD bullets believed closed (per brief §5)

All 11 bullets:

| # | Bullet | Closed via |
|---|---|---|
| 1 | `AdapterWarning` landed in `run/types.py`; structurally compatible with `EnvelopeWarning` | `test_adapter_warning_field_names_match_envelope_warning` |
| 2 | `NativeResult.warnings: tuple[AdapterWarning, ...] = ()` field | `test_warnings_defaults_to_empty_tuple` + types.py diff |
| 3 | All 6 adapters write to `result.warnings`; existing `payload["warnings"]` retained | grep on adapter sources + integration smoke captures (b)+(c) showing dual channels |
| 4 | Normalizer lifts NativeResult.warnings → orchestration | deviated: lifted at engine layer (engine.py) — same end-to-end effect, smaller churn |
| 5 | `RunOutcome.warnings` field added | orchestration/workflows/run.py diff + smoke (a) shows envelope.warnings populated |
| 6 | `run_cmd` + `test_cmd` pass `warnings=` to `Envelope(...)` | cli/app.py + cli/handlers/test.py diffs + `test_envelope_warnings_projection.py::TestBuildTestEnvelopeWarningsProjection` |
| 7 | Cross-team scope guard | authorized: orchestration/run.py + cli/app.py + cli/handlers/test.py + orchestration/test.py (all per brief §3 or implicit); mechanical: replay/engine.py (1-line, documented in §"Cross-team scope footprint") |
| 8 | Per-warning integration tests; all PASS on equipped host | 4 tests, 4 passing — `test_*_warnings.py` |
| 9 | Backward-compat: v1 metadata keys + legacy payload["warnings"] still populated | criterion #2 verified in smoke (a) (metadata) + integration test assertions on `payload["warnings"]` in xunit-v3 case |
| 10 | mypy --strict clean | `Success: no issues found in 91 source files` |
| 11 | §2.5 pre-handoff gate | green; smoke captures pasted above; toolchain shim sourced; 1166+5+0 total |
