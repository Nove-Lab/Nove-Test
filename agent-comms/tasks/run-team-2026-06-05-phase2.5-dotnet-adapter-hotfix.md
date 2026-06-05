---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-05
slug: phase2.5-dotnet-adapter-hotfix
status: pending
related:
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/findings/manual-test-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md
  - design/implementation-plan/engine-adapters.md
---

# Phase 2.5 .NET adapter — hotfix #1 (D1 verdict-blocker + Coverlet decision amendment alignment)

## TL;DR

Manual Test verdict-failed `f8f8d93` on the equipped host with **one verdict-blocking defect (D1)** and surfaced two non-defect items (D2 verification-doc inaccuracy + the Run team's open question filed in handoff).

This hotfix brief scopes:

| Fix | Severity | Scope |
|---|---|---|
| **F1** — D1: `_probe_coverlet_version` runs before `dotnet restore`, fails silently on fresh user-project, degrades coverage to no-op | **P0 (verdict-blocker)** | Adapter: pre-restore call + envelope-level safety-net warning + integration test pinning fresh-fixture reproducer |
| **F2** — Adapter behavior alignment with amended decision (no code change; confirmation) | Confirm | Verify adapter still complies with §3 amendment |
| **F3** — D2: verification-doc field-path inaccuracy (no code defect) | Docs | Note for handoff; Main Branch updates next verification doc |

**Estimated scope**: ~30-50 LOC src + ~40-60 LOC tests. **1-3 hours.** Tiny slice.

## ✅ Coverlet PerTestCoverage question resolved 2026-06-05

CEO approved Option A on 2026-06-05. The amendment lives in
`decisions/2026-06-03-coverlet-pertestcoverage-key.md` (committed in the
same commit as this brief):

- §3 amended — aggregate-effective-default for v1; per-test deferred
- R4 added — Phase 4 SBFL on .NET = `failure_proximity` mode
- `engine-adapters.md §6` amended — same content reflected in design doc

The Run team's filed question
(`agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-empirically-inert.md`)
is **resolved** by this amendment. Question file will be archived at
cycle close.

The adapter ALREADY ships the safest behavior (per the Run team's
recommendation that became the amendment) — runsettings template
forward-compat + per-test glob with aggregate-fallback. **No F2 code
change required.**

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/findings/manual-test-team-2026-06-05-phase2.5-dotnet-adapter.md`** §"D1 (verdict-blocking)" — the verdict-blocking defect with exact reproducer
4. **`agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md` §3 + §"Risks" R4** — the amended contract (PerTestCoverage XPlat-path empirically inert, aggregate-effective-default ratified, R4 Phase 4 SBFL implications)
5. `agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §1 + §2 + §2.5 — still in force; this hotfix's diff modifies both `dotnet_adapter.py` and `test_dotnet_coverage.py` → §2.5 binds
6. `agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter.md` — the original brief (for context on the design constraints this hotfix preserves)
7. `agent-comms/handoffs/run-team-2026-06-05-phase2.5-dotnet-adapter.md` — the original handoff (for the architectural map of the adapter you're hotfixing)
8. `src/novetest/run/adapters/dotnet_adapter.py:299` — call site of `_probe_coverlet_version` in the main adapter flow
9. `src/novetest/run/adapters/dotnet_adapter.py:616-705` — `_probe_coverlet_version` itself
10. `tests/integration/run/test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml` + `::test_coverage_runsettings_landed_under_artifact_dir` — the two pre-merge-gate-green-but-Manual-Test-fail tests (key to understanding the Run team / Main Branch / Manual Test divergence)
11. `src/novetest/run/adapters/junit_adapter.py` lines around the build-tool argv composition — pattern reference for `dotnet restore` placement (analogous to JUnit's `mvn`/`gradle` invocation sequencing)
12. `src/novetest/utils/asyncio_subprocess.py` `run_subprocess` — the canonical adapter subprocess helper

---

## §1. F1 — D1 root cause analysis (binding)

### 1.1 The defect (Manual Test reproducer, verbatim from findings)

```sh
source ~/.local/share/novetest-toolchains.sh
cd /tmp && rm -rf dotnet-repro
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/dotnet-test-basic-coverage dotnet-repro
cd dotnet-repro
uv run --project <repo> novetest init
uv run --project <repo> novetest run --coverage . | jq '.data.memory_entry.run_record.metadata'
# Expected (per amended decision § + the original brief's intent):
#   {coverlet_version: "6.0.2", coverage_mapping_granularity: "aggregate", ...}
# Actual:
#   {dotnet_sdk_version, native_exit_code, xunit_version}   <- no coverlet_version, no coverage_mapping_granularity
```

The `--coverage` flag is silently no-op'd. No envelope-level warning, no
error. From the user's perspective `novetest run --coverage` does
nothing for coverage.

### 1.2 Root cause (already pinned by Manual Test bisection §6 + §7)

`_probe_coverlet_version` invokes:

```sh
dotnet list <csproj> package --include-transitive --format json
```

This command requires `obj/project.assets.json` (a restore artifact).
On a freshly-copied user project the file doesn't exist yet. Manual
Test confirmed the exit behavior at findings §7:

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

The subprocess **exits 0** (JSON-format command succeeds even on problems
path), the parser path is taken (NOT the tabular fallback), and the
parser sees `projects[].frameworks[]` empty → returns `None`. Adapter
treats Coverlet as absent → drops `--collect:"XPlat Code Coverage"` from
argv → silently no-coverage run.

### 1.3 The workaround that proves the diagnosis (Manual Test §6)

```sh
dotnet restore MathLib.Tests/MathLib.Tests.csproj  # 1-line addition
uv run --project <repo> novetest run --coverage . | jq '...'
# Now: coverlet_version=6.0.2, coverage_mapping_granularity=aggregate, runsettings staged, cobertura XML emitted
```

Single-line difference, full coverage path flips from "silently broken"
to "fully working". The defect is exactly that `_probe_coverlet_version`
runs against a project that hasn't been restored.

---

## §2. F1 — Fix shape (binding)

### 2.1 F1a — Pre-restore call before probe (adapter-side)

In `dotnet_adapter.py`, before the existing `_probe_coverlet_version`
call (around line 299), add a `dotnet restore <csproj>` subprocess
invocation:

```python
# Concrete shape (pseudocode — Run team adapts to actual signature):
await run_subprocess(
    ["dotnet", "restore", str(csproj_path)],
    cwd=workspace_path,
    timeout=300.0,  # restore can be slow on cold NuGet cache; 5 min ceiling
    capture_stdout=True,
    capture_stderr=True,
)
# Tolerate non-zero exit: if restore fails (e.g. offline + cold cache),
# proceed to probe anyway; if probe ALSO returns None, F1b safety-net fires.
```

**Idempotence**: `dotnet restore` is a no-op on already-restored projects
(re-reads `project.assets.json` cache; ~50-200ms when up-to-date). Safe
to always run on the coverage path.

**Timing**: Adds 1-3s on first invocation of a fresh fixture; near-zero
on subsequent invocations of the same fixture.

**Placement**: ONLY on the `--coverage` path (so non-coverage runs don't
pay the restore cost). Cheapest condition: `if collect_coverage:` (or
equivalent flag in the adapter's flow).

### 2.2 F1b — Envelope-level safety-net warning

Defense-in-depth for paths the adapter doesn't anticipate (e.g. restore
itself fails, network outage, malformed user csproj). When `--coverage`
is requested AND `_probe_coverlet_version` returns `None` AFTER restore,
emit a TOP-LEVEL `warnings` envelope entry:

```python
# Pseudocode:
if collect_coverage and coverlet_version is None:
    # Internal payload warning (already emitted by adapter today)
    payload_warnings.append(("engine-misconfigured", "coverlet.collector not in project's package graph; cannot collect coverage"))
    # NEW: bubble to envelope-level warnings via NativeResult.warnings
    result.warnings.append({
        "kind": "coverage-requested-but-coverlet-absent",
        "message": (
            "novetest run --coverage was requested but coverlet.collector "
            "could not be detected in the project's package graph. The run "
            "executed without coverage collection. To enable coverage: add "
            "<PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" /> "
            "to your test csproj."
        ),
    })
```

**Critical**: this warning MUST reach the envelope's top-level `warnings`
field, not just the internal payload. Manual Test findings §"D1" §"User-
visible symptom" pinpoint that the current warning lives only in
`NativeResult.payload.warnings` and does NOT propagate to envelope-level
`warnings` on this code path. The bubble-up is essential for D1 to be
fully closed (the user MUST see *something* when their `--coverage`
flag is ignored).

Run team — verify the exact mechanism for envelope warnings on existing
adapters. JUnit's `engine-misconfigured` warning (when JaCoCo absent
post-2026-06-04 hotfix) is the closest pattern; check
`junit_adapter.py` for the warning-propagation site.

### 2.3 F1c — Integration test pins the fresh-fixture reproducer

`tests/integration/run/test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml`
exists and passes on Run team's gate + Main Branch's gate but FAILS on
Manual Test's fresh repro. The mystery is unresolved (findings §"Why
Main Branch's gate didn't see this" notes the divergence as un-
diagnosed). The hotfix MUST close this:

1. **Add an integration test** (`test_coverage_run_on_fresh_fixture_with_no_prior_restore`)
   that:
   - Uses `tmp_path` (per-test scope, guaranteed fresh)
   - `shutil.copytree`s the `dotnet-test-basic-coverage` fixture
   - Confirms NO `obj/` directory in the copied destination (`assert not (workspace / "MathLib.Tests" / "obj").exists()`)
   - Invokes the adapter
   - Asserts Coverlet version detected post-fix; cobertura XML emitted
2. **Audit `test_coverage_run_emits_cobertura_xml`** and `test_coverage_runsettings_landed_under_artifact_dir`
   for shared state. Why did they pass on Run team's gate? Hypothesis:
   `shutil.copytree` source has `obj/` from a prior `dotnet test` run
   in the SAME pytest session. If so, the test's fixture source is
   polluted across runs.
3. **If audit finds shared-state issue**, add fixture cleanup BEFORE
   each test: `if (tmp_path / ... / "obj").exists(): shutil.rmtree(...)`
   or use a copy-from-clean-source pattern.

The Manual Test reproducer at §1.1 of this brief MUST pass post-fix.

---

## §3. F2 — Amended decision compliance (verification only, no code change)

The amendment to `decisions/2026-06-03-coverlet-pertestcoverage-key.md §3`
ratifies the aggregate-effective-default behavior the adapter ALREADY
ships:

- `mapping_granularity = "aggregate"` when 0 per-test files appear ✓ (per Run team handoff §"Decisions referenced" §3)
- Runsettings template retains `<PerTestCoverage>true</PerTestCoverage>` for forward-compat ✓
- Auto-fallback glob (per-test → aggregate when per-test returns 0) ✓

**No F2 code change required.** Run team's handoff should:
- Cite the amended §3 + R4 as the binding contract
- Confirm the adapter's existing behavior matches (it does)
- Mention R4 in the handoff's "decisions referenced" table so the Phase 4 Localization implication is recorded

---

## §4. F3 — D2 verification-doc inaccuracy (no code change)

Manual Test finding §"D2": verification doc expected
`data.memory_entry.run_record.coverage_xml` as a non-empty list of paths;
actual is `None`, with coverage XML path in `artifact_paths["coverage_xml"]`
as single string.

**PM confirmed by inspection**:
- `src/novetest/models/run_record.py:49` — only `artifact_paths: dict[str, str]` field; **no `coverage_xml` direct field exists**
- `src/novetest/coverage/derive.py:66` — `COVERAGE_JACOCO_XML_ARTIFACT_KEY = "coverage_xml"` is the universal artifact key
- `src/novetest/run/adapters/junit_adapter.py:435` — JUnit adapter writes to `artifact_paths["coverage_xml"]` (same canonical pattern)

**D2 is verification-doc-only.** The .NET adapter's behavior is correct
and consistent with all prior adapters. Main Branch's next verification
doc (post-hotfix re-pass) MUST assert against
`data.memory_entry.run_record.artifact_paths["coverage_xml"]` instead.

Run team's handoff should:
- Note D2 closure as "verification-doc-only; no source change required"
- Pin the correct field path: `RunRecord.artifact_paths["coverage_xml"]`

Main Branch sees the handoff and updates the next verification doc
accordingly.

---

## §5. Why Manual Test caught it but Run team's gate + Main Branch's gate didn't (forensic)

The hotfix MUST close this divergence empirically. Hypothesis to verify
during fix dev:

**Hypothesis H1**: The Run team's gate ran `test_dotnet_coverage.py` in
the same pytest session as `test_dotnet_basic.py` (or similar). The
basic test's `dotnet test` invocation populates `obj/project.assets.json`
in the *fixture source directory* (NOT in `tmp_path`), and the coverage
test's `shutil.copytree` picks up that polluted `obj/` directory.

**Hypothesis H2**: The fixtures have a pre-committed `obj/` directory
(unlikely — git-tracked obj would be wrong, but possible if .gitignore
is wrong).

**Hypothesis H3**: Some global `nuget.config` or MSBuild setting affects
`dotnet list package` behavior in the no-restore case (less likely
given Manual Test's fully-equipped host showed the same defect).

Run team verifies by:
1. `ls tests/fixtures/projects/dotnet-test-basic-coverage/MathLib.Tests/obj/` on a fresh `git status`-clean checkout — if present, H2.
2. After running `pytest -v tests/integration/run/test_dotnet_basic.py` (basic, non-coverage), check whether `obj/` appears in `tests/fixtures/projects/dotnet-test-basic-coverage/MathLib.Tests/` — if so, H1.
3. Compare `dotnet list package --include-transitive --format json` output before/after restore on a fresh fixture — confirms the asset-file-required behavior.

The integration test fix at §2.3 closes whichever hypothesis is the
truth.

---

## §6. DoD bullets (PM ticks at cycle close)

| # | Bullet | Evidence form expected |
|---|---|---|
| 1 | `dotnet_adapter.py` invokes `dotnet restore <csproj>` before `_probe_coverlet_version` on the coverage path (NOT on the non-coverage path) | grep `dotnet_adapter.py` for `["dotnet", "restore"`; conditional under `collect_coverage` |
| 2 | F1a behavior unit-tested: mock subprocess; assert restore happens before list-package on coverage path; assert restore NOT called on non-coverage path | new `TestPreRestore` class in `test_dotnet_adapter.py` |
| 3 | F1b envelope-level safety-net warning emitted when `--coverage` requested but Coverlet probe returns `None` after restore; warning kind `coverage-requested-but-coverlet-absent` (or equivalent) | new `TestEnvelopeSafetyNet` unit class + manual capture in handoff |
| 4 | F1c new integration test `test_coverage_run_on_fresh_fixture_with_no_prior_restore` passes; asserts no `obj/` in tmp_path; asserts `coverlet_version` populated post-fix | `test_dotnet_coverage.py::test_coverage_run_on_fresh_fixture_with_no_prior_restore` |
| 5 | Existing `test_coverage_run_emits_cobertura_xml` and `test_coverage_runsettings_landed_under_artifact_dir` audit complete; shared-state issue (if any) closed; both pass on truly-fresh-state per-test | handoff §"Hypotheses tested" with H1/H2/H3 disposition |
| 6 | D1 Manual Test reproducer (verbatim §1.1) passes end-to-end on equipped host without ANY pre-restore step | handoff §"D1 reproducer verification" with captured envelope |
| 7 | F2 — handoff cites amended decision §3 + R4; no code change required; adapter behavior matches | handoff §"Decisions referenced" |
| 8 | F3 — handoff notes D2 as verification-doc-only; pins correct field path `RunRecord.artifact_paths["coverage_xml"]` | handoff §"D2 disposition" |
| 9 | mypy --strict clean (91 source files unchanged) | mypy output |
| 10 | Pre-handoff gate on equipped host (§2.5 binding): full suite + dotnet focus 0 skips 0 fails; D1 reproducer pass | handoff §"Pre-handoff gate environment" |

---

## §7. Out of scope (NOT in this hotfix)

- The amended decision file (PM-owned; already amended in same commit as this brief queue)
- Verification doc D2 correction (Main Branch-owned; next verification doc handles it)
- `coverlet.msbuild` opt-in per-test path (future cycle; non-modification contract opt-in)
- Per-test coverage on .NET (deferred per amended decision §3)
- xUnit v3 actual coverage (out of MVP per original decision §6)
- Multi-project / multi-TFM / `--blame` / NUnit / MSTest (out of v1 per original brief §8)
- R2 large-suite performance validation (deferred per original brief §5)
- Phase 4 Localization SBFL mode dispatch logic (already exists per R4 amendment; no .NET-specific change needed)

---

## §8. Equip-and-exercise §2.5 binding (compliance reminder)

This hotfix slice modifies BOTH `src/novetest/run/adapters/dotnet_adapter.py`
AND `tests/integration/run/test_dotnet_coverage.py` → **§2.5 IS BINDING.**

Run team's pre-handoff gate:
1. **Equipped host** — `dotnet --version >= 8.0` + `coverlet.collector >= 6.0.2` resolvable
2. **Skip-gate check** — `shutil.which("dotnet")` must resolve; 0 skips on dotnet integration cases
3. **D1 reproducer** — Manual Test's verbatim §1.1 reproducer MUST pass post-fix on a fresh fixture copy (this is the critical exit criterion for this cycle's verdict)
4. **Test-isolation check** — the new fresh-fixture integration test MUST pass AND the existing two coverage tests MUST also pass with the audit cleanup (whichever hypothesis closure §5 yields)

**Third equip-and-exercise dividend** (per Manual Test finding §"Recommendations" #3): JUnit hotfix #1 → cargo CLI orchestration → this .NET cycle is now three consecutive adapter cycles where equip-and-exercise caught a verdict-blocking defect that unit suites and merged-machine integration suites all missed. Pattern reinforces: unit-level mocking is insufficient for adapter-side logic that depends on user-project state being initialized; only clean E2E on equipped host catches.

---

## §9. Decisions referenced

| Decision | Honored as |
|---|---|
| `2026-06-03-coverlet-pertestcoverage-key.md §3 (amended 2026-06-05)` | Aggregate-effective-default ratified; per-test deferred; adapter behavior already matches |
| `2026-06-03-coverlet-pertestcoverage-key.md §R4 (added 2026-06-05)` | Phase 4 SBFL on .NET → `failure_proximity` mode; documented in handoff for Run team's records |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1 + §2 + §2.5` | Manual Test re-pass on equipped host; CLI smokes already present; pre-handoff gate binding |
| `2026-05-30-native-result-metadata-slot.md` | `metadata.native_exit_code` already populated; no change |
| `2026-05-25-supported-engine-matrix.md` | All floors unchanged; no amendment |

---

## §10. Effective date

Brief queued 2026-06-05 PM. CEO will dispatch Run team from the next
available equipped host. Expected single-attempt close (no further
hotfixes). On clean Manual Test re-pass: **Phase 2.5 native engine work
complete; 6/6 adapters production-ready; Phase 3 entry condition met.**
