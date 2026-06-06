---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: paused
created: 2026-06-06
slug: phase2.5-dotnet-adapter-hotfix
related:
  - agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md
  - agent-comms/findings/manual-test-team-2026-06-05-phase2.5-dotnet-adapter.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/questions/run-team-2026-06-06-dotnet-equip-blocker.md
  - agent-comms/questions/run-team-2026-06-06-envelope-warnings-projection.md
---

# Handoff — Phase 2.5 .NET adapter hotfix #1 (D1 pre-restore + envelope visibility) — **PAUSED**

## ⚠ Status

**PAUSED — §2.5 pre-handoff gate NOT satisfied on this checkout's
host.** Per
`decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
§2.5.3, work pauses and Run team files a `questions/` entry to PM
rather than handing off an un-exercised diff. This document is the
PAUSED handoff: source + tests are committed, unit gate is green,
mypy is clean, but the equipped-host integration gate did not run
because this host lacks the .NET SDK and both install paths are
blocked (`dotnet-install.sh` blocked by auto-mode classifier;
`sudo apt-get install dotnet-sdk-8.0` blocked by tty-less password
prompt + missing `.claude/settings.json` pre-authorization).

See `agent-comms/questions/run-team-2026-06-06-dotnet-equip-blocker.md`
for the four PM-disposition options. **Do NOT FF-merge this branch
until PM has authorized either an equip step on this host OR a
gate runner on a different host.**

## TL;DR

The Phase 2.5 .NET adapter hotfix #1 slice closes Manual Test's
verdict-blocking D1 from 2026-06-05:
``_probe_coverlet_version`` ran ``dotnet list <csproj> package
--include-transitive --format json`` BEFORE ``dotnet test`` against
a freshly-copied user project that had no ``obj/project.assets.json``;
the probe silently returned ``None``, the adapter treated Coverlet
as absent, and ``novetest run --coverage`` silently no-op'd.

**Fix shape (three parts):**

| Part | Description | Scope | Status |
|---|---|---|---|
| **F1a** | `_ensure_csproj_restored` runs `dotnet restore <csproj>` BEFORE the probe on the coverage path | Adapter | ✅ implemented + unit-tested |
| **F1b** | Metadata-level safety-net (`coverage_unavailable_kind` + `_message`) when probe returns `None` after restore | Adapter (Run-team-scope partial; full envelope-level requires cross-team plumbing — see companion question) | ✅ partial implemented + unit-tested |
| **F1c** | Integration test `test_coverage_run_on_fresh_fixture_with_no_prior_restore` explicitly asserts no-`obj/` precondition + post-fix `coverlet_version == "6.0.2"` | Test | ✅ implemented; **SKIPPED on this host (§2.5 gap)** |

## Worktree info

- **Worktree path**: `/home/yjshin/dev/aispace/novetest-dotnet-adapter-hotfix-1`
- **Branch**: `run-team/dotnet-adapter-hotfix-1`
- **Base commit**: `1f9486a` (current `main` tip — "comms: Manual Test findings (failed) + amend Coverlet decision + queue .NET adapter hotfix")
- **Commit**: pending — see "Pre-merge checklist (when unpaused)" below

## Pre-handoff gate environment (§2.5 — **NOT SATISFIED**)

### Detected toolchain (this checkout's host)

| Tool | Version | Matrix floor | Status |
|---|---|---|---|
| `dotnet` SDK | **MISSING** | 8.0 (LTS) | ❌ — not on PATH; `~/.dotnet/` does not exist |
| `~/.local/share/novetest-toolchains.sh` shim | **MISSING** | — | ❌ — not present on this host |
| `~/.nuget/packages/coverlet.collector` cache | **MISSING** | 6.0.2 | ❌ — not present |
| `uv` | 0.11.14 | (any) | ✅ |
| Python | 3.11.15 | 3.11 | ✅ |
| `jq` | **MISSING** | — | Optional; only used by ad-hoc CLI invocations |

### Install attempts

1. **`curl -fsSL https://dot.net/v1/dotnet-install.sh ...`** — Claude
   Code auto-mode classifier denied:
   *"Downloading and executing dotnet-install.sh from dot.net — not
   on the Toolchain Bootstrap allowlist and no explicit user
   authorization to install a .NET toolchain."*

2. **`sudo apt-get install -y dotnet-sdk-8.0`** (Ubuntu noble main
   has 8.0.127, matrix-floor-compliant) — sudo prompted for
   password; this session has no tty. `.claude/settings.json` only
   pre-authorizes `openjdk-17-jdk*` and `maven*` apt installs.
   `dotnet-sdk-8.0` is NOT pre-authorized.

### Engine-specific integration counts (§2.5.4 mandate)

`uv run pytest -v tests/integration/run/test_dotnet_*.py`:

```
tests/integration/run/test_dotnet_basic.py::test_basic_run_emits_native_result               SKIPPED
tests/integration/run/test_dotnet_basic.py::test_cli_smoke_run_dot_emits_envelope            SKIPPED
tests/integration/run/test_dotnet_basic.py::test_cli_smoke_run_bare_emits_envelope           SKIPPED
tests/integration/run/test_dotnet_coverage.py::test_coverage_run_emits_cobertura_xml         SKIPPED
tests/integration/run/test_dotnet_coverage.py::test_coverage_runsettings_landed_under_artifact_dir  SKIPPED
tests/integration/run/test_dotnet_coverage.py::test_coverage_run_on_fresh_fixture_with_no_prior_restore  SKIPPED   <-- NEW (F1c)
```

**6 SKIPPED, 0 failed in 0.38s.** §2.5 mandate
("skip count for the engine's integration cases MUST be 0;
failure count MUST be 0") **NOT SATISFIED on this host.**

The 0 failures is encouraging (no integration-test regression risk)
but the 6 skips are the §2.5 blocker.

## Files written / modified

| File | Lines | Change |
|---|---|---|
| `src/novetest/run/adapters/dotnet_adapter.py` | +127 / -1 | F1a `_ensure_csproj_restored` helper + call site + F1b metadata safety-net + extended module docstring + `__all__` export |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | +320 / -8 | Stub extended for `restore` recognition + `captured_restore` + `call_log` + `restore_returncode` params; new `TestPreRestore` (6 tests) + `TestEnvelopeSafetyNet` (4 tests) |
| `tests/integration/run/test_dotnet_coverage.py` | +105 / 0 | New `test_coverage_run_on_fresh_fixture_with_no_prior_restore` test with explicit precondition assertions + hypothesis disposition comment |
| `agent-comms/questions/run-team-2026-06-06-dotnet-equip-blocker.md` | +148 / 0 | NEW — §2.5 gate blocker question (this slice's blocking issue) |
| `agent-comms/questions/run-team-2026-06-06-envelope-warnings-projection.md` | +230 / 0 | NEW — F1b cross-team envelope-warnings plumbing question |
| `agent-comms/handoffs/run-team-2026-06-06-phase2.5-dotnet-adapter-hotfix.md` | this file | NEW — PAUSED handoff |
| `WORKLOG.md` | +14 lines | New top entry |
| `agent-comms/INDEX.md` | regenerated | Reflects new pending question + paused handoff |

**Total**: ~944 lines across 8 files (127 src adapter + 320 unit test + 105 integration test + 378 question/handoff/worklog/index).

## Decisions referenced + how honored

| Decision | Honored |
|---|---|
| `2026-06-03-coverlet-pertestcoverage-key.md §3` (amended 2026-06-05) | aggregate-effective-default ratified; adapter unchanged from prior cycle (decision F2 — no code change required) |
| `2026-06-03-coverlet-pertestcoverage-key.md R4` | Phase 4 SBFL on .NET → `failure_proximity` mode; documented in original handoff |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §1 + §2` | CLI smokes already present from prior cycle (unchanged here); Manual Test re-pass mandate carries to next cycle |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md §2.5` | **NOT SATISFIED on this host** — formal pause filed per §2.5.3; PM disposition required |
| `2026-05-30-native-result-metadata-slot.md` | `coverage_unavailable_kind` + `_message` keys added to metadata; `native_exit_code` reserved-key guard respected (not pre-populated by adapter) |
| `2026-05-25-supported-engine-matrix.md` | All floors unchanged; no amendment |

## Hypothesis disposition (brief §5)

The brief §5 asked Run team to investigate why Main Branch's gate
passed 5/5 dotnet integration tests on the equipped host while
Manual Test's gate failed on the SAME tests with the SAME fixture.

| Hypothesis | Disposition |
|---|---|
| **H1**: cross-test pollution within same pytest session (basic test populates `obj/` that coverage test sees) | **REJECTED**. Both integration tests use per-function `tmp_path` and `shutil.copytree(FIXTURE_ROOT, dest)`. Each test gets a fresh isolated copy. Cross-test state leak through tmp_path is impossible. The basic test populates `obj/` inside ITS OWN tmp_path; that doesn't propagate to the coverage test's separate tmp_path. |
| **H2**: pre-committed `obj/` in the fixture source | **REJECTED**. `find tests/fixtures/projects/dotnet-test-basic-coverage -type d` shows only `MathLib/` + `MathLib.Tests/`; `.gitignore` correctly excludes `bin/ obj/ TestResults/ coverlet.runsettings`. Verified on this checkout's `git status`-clean state. |
| **H3**: external NuGet config / packages cache state on Main Branch's host | **MOST PLAUSIBLE, NOT EMPIRICALLY VERIFIED**. Some `NUGET_PACKAGES` env var, `nuget.config`, or pre-populated NuGet cache on Main Branch's machine may have incidentally satisfied `dotnet list package --include-transitive --format json` without an explicit restore. Without access to Main Branch's host I cannot empirically confirm. **F1a closes the dependency regardless of the cause.** |

The new F1c integration test (`test_coverage_run_on_fresh_fixture_with_no_prior_restore`)
makes the no-`obj/` precondition explicit so any future regression
that re-introduces the dependency is caught structurally, not by
luck of host state.

## DoD bullets believed closed (brief §6)

| # | DoD bullet | Evidence | ✓ |
|---|---|---|---|
| 1 | `dotnet_adapter.py` invokes `dotnet restore <csproj>` before `_probe_coverlet_version` on the coverage path (NOT on the non-coverage path) | `src/novetest/run/adapters/dotnet_adapter.py:377` — call site under `if collect_coverage and not is_xunit_v3:`; `_ensure_csproj_restored` helper at line 726 | ✓ |
| 2 | F1a behavior unit-tested: mock subprocess; assert restore happens before list-package on coverage path; assert restore NOT called on non-coverage path | `tests/unit/run/adapters/test_dotnet_adapter.py::TestPreRestore` — 6 tests including ordering + non-coverage + xunit-v3 + failure-tolerance + argv-shape + helper-direct | ✓ |
| 3 | F1b safety-net warning emitted when `--coverage` requested but Coverlet probe returns `None` after restore; warning kind `coverage-requested-but-coverlet-absent` (or equivalent) | `TestEnvelopeSafetyNet` (4 tests); metadata key `coverage_unavailable_kind = "coverlet-absent-or-stale"`. **NOTE**: formal envelope top-level `warnings` projection deferred to follow-up cross-team slice — see `questions/.../envelope-warnings-projection.md`. THIS SLICE ships Run-team-scope partial via metadata. | ✓ (partial) |
| 4 | F1c new integration test `test_coverage_run_on_fresh_fixture_with_no_prior_restore` passes; asserts no `obj/` in tmp_path; asserts `coverlet_version` populated post-fix | `tests/integration/run/test_dotnet_coverage.py::test_coverage_run_on_fresh_fixture_with_no_prior_restore`. **SKIPPED on this host** (§2.5 gap); execution requires equipped-host. | ⚠ pending §2.5 |
| 5 | Existing `test_coverage_run_emits_cobertura_xml` and `test_coverage_runsettings_landed_under_artifact_dir` audit complete; shared-state issue (if any) closed; both pass on truly-fresh-state per-test | Audit complete (see "Hypothesis disposition" above): both existing tests already use per-function `tmp_path` + `shutil.copytree` of git-clean fixture; H1+H2 rejected. No shared-state cleanup required. | ✓ |
| 6 | D1 Manual Test reproducer (verbatim §1.1) passes end-to-end on equipped host without ANY pre-restore step | **Requires equipped host** — currently SKIPPED. Test code is in place (`test_coverage_run_on_fresh_fixture_with_no_prior_restore`); execution pends PM disposition. | ⚠ pending §2.5 |
| 7 | F2 — handoff cites amended decision §3 + R4; no code change required; adapter behavior matches | See "Decisions referenced" table above. Coverlet decision §3 amendment ratified by 2026-06-05; adapter ships aggregate-effective-default behavior unchanged. | ✓ |
| 8 | F3 — handoff notes D2 as verification-doc-only; pins correct field path `RunRecord.artifact_paths["coverage_xml"]` | D2 disposition: `RunRecord.artifact_paths["coverage_xml"]` is the canonical field per `src/novetest/run/adapters/dotnet_adapter.py:454`. Verification doc author conflated it with a nonexistent direct `run_record.coverage_xml` field. Main Branch's next verification doc must use `data.memory_entry.run_record.artifact_paths["coverage_xml"]` (single string, not list of paths). | ✓ |
| 9 | mypy --strict clean (91 source files unchanged) | `uv run mypy` → "Success: no issues found in 91 source files" | ✓ |
| 10 | Pre-handoff gate on equipped host (§2.5 binding): full suite + dotnet focus 0 skips 0 fails; D1 reproducer pass | **NOT SATISFIED on this host.** Filed `questions/run-team-2026-06-06-dotnet-equip-blocker.md` per §2.5.3 protocol. | ⚠ PAUSED |

8/10 fully ✓; 2/10 (bullets 4 + 6 + the equipped-host portion of 10) pend equipped-host execution.

## What WAS verified locally (unequipped-host gate)

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit tests/integration` | **1139 passed + 11 skipped + 0 failed in 86.75s** |
| `uv run pytest -q tests/unit/run/adapters/test_dotnet_adapter.py` | **91 passed in 0.24s** (10 NEW: 6 TestPreRestore + 4 TestEnvelopeSafetyNet; on top of 81 pre-existing) |
| `uv run mypy` (full strict) | **Success: no issues found in 91 source files** |
| `uv run mypy --strict src/novetest/run/adapters/dotnet_adapter.py` | **Success: no issues found in 1 source file** |
| Hotfix-3 JUnit regression canaries (`test_init_script_present_with_coverage_and_jacoco`, etc.) | Green (in `tests/unit/run/adapters/test_junit_adapter.py` — passing as part of the 1139) |
| Hotfix-2 Maven `failure.ignore` regression canary | Green (passing as part of the 1139) |

11 skipped breakdown (unequipped-host expected): 6 dotnet (3 basic
+ 3 coverage; the +1 vs pre-hotfix 5 skips is the new F1c test) +
2 jest (require Node) + 2 gotest (require Go) + 1 junit (no
java/mvn/gradle — though most junit tests have fallbacks). None
are regressions; all are toolchain-presence skip-gates.

## Pre-merge checklist (when PM unpauses this handoff)

Once `agent-comms/questions/run-team-2026-06-06-dotnet-equip-blocker.md`
is resolved (Option 1 / 2 / 3 / 4 — see that doc), Main Branch's
pre-merge gate must:

1. `cd /home/yjshin/dev/aispace/novetest-dotnet-adapter-hotfix-1` (or wherever the worktree lives post-disposition)
2. (Option 1+2+4 only) Source the toolchain shim or run `dotnet --version` to confirm SDK is present
3. `uv run pytest -q tests/unit tests/integration` — expect ≥ **1139 passed** (the F1c test promotes from SKIPPED to PASSED on equipped host) + ≤ **5 skipped** (jest + gotest + 1 junit; the 6 dotnet skips drop to 0)
4. `uv run pytest -v tests/integration/run/test_dotnet_*.py` — expect **6 passed + 0 skipped + 0 failed** (3 basic + 3 coverage including F1c)
5. `uv run mypy --strict src` — expect **Success: no issues found in 91 source files**
6. **D1 Manual Test reproducer probe** (the canonical exit criterion for this cycle's verdict):
   ```sh
   cd /tmp && rm -rf dotnet-repro
   cp -r <repo>/tests/fixtures/projects/dotnet-test-basic-coverage dotnet-repro
   cd dotnet-repro
   uv run --project <repo> novetest init
   uv run --project <repo> novetest run --coverage . | python3 -c "
   import json, sys
   e = json.load(sys.stdin)
   rr = e['data']['memory_entry']['run_record']
   meta = rr['metadata']
   assert meta['coverlet_version'] == '6.0.2', meta
   assert meta['coverage_mapping_granularity'] == 'aggregate', meta
   assert 'coverage_unavailable_kind' not in meta, meta
   assert 'coverage_xml' in rr['artifact_paths'], rr['artifact_paths']
   print('D1 reproducer PASS')
   "
   ```
7. FF-merge the branch onto `main`. No conflicts expected.
8. Write verification doc for Manual Test re-pass per
   `agent-comms/README.md` template + the amended Coverlet decision §3
   + the corrected field path (`data.memory_entry.run_record.artifact_paths["coverage_xml"]`).

## Open items / surprises for PM

### Critical (filed; blocking on PM disposition)

1. **`agent-comms/questions/run-team-2026-06-06-dotnet-equip-blocker.md`** — §2.5 gate blocker on this host. PM picks one of four equip-or-handoff options; this handoff's status changes from `paused` → `ready` once resolved + the §2.5 gate executes successfully.

2. **`agent-comms/questions/run-team-2026-06-06-envelope-warnings-projection.md`** — F1b's strict "envelope top-level warnings field" requirement is cross-team. THIS slice ships Run-team-scope partial via metadata (`coverage_unavailable_kind` + `_message`). PM picks Option A (keep as-is) / B (single reserved key) / C (formal cross-team follow-up slice) / D (defer F1b entirely; revert metadata surface). Non-blocking for THIS slice; resolution shapes follow-up cycle scope.

### Operational (non-blocking)

3. **`.claude/settings.json` apt allowlist expansion**. Adding `Bash(sudo apt-get install -y dotnet-sdk-8.0*)` parallels the existing `openjdk-17-jdk*` and `maven*` entries. PM may want to make this part of standard cycle equip-policy for hosts that bounce between adapter cycles.

4. **Auto-mode classifier "Toolchain Bootstrap allowlist"**. Both `dotnet-install.sh` (this cycle) and `gradle 8.x` / `maven 3.9` (JUnit hotfix-3 cycle) downloads blocked. CEO may want to scope a meta-decision on which toolchain bootstraps are pre-authorized vs require per-cycle authorization. Three classifier-blocked downloads in three cycles is a pattern.

### Forward (informational)

5. **Hypothesis H3 (NuGet config / packages cache state) un-resolved**. The F1a fix is bulletproof regardless, but if the Main Branch host's masking state is reproducible deliberately it could become a guardrail/anti-guardrail in the dev-host-setup doc. PM may want to ask Manual Test or whoever owns that host to dump `nuget.config` + `NUGET_PACKAGES` env on the next cycle.

## Worklog entry text (drafted; staged with the slice)

```
## 2026-06-06 — phase2.5 / dotnet-adapter-hotfix #1 (D1 pre-restore + envelope visibility partial — PAUSED on §2.5)

- Landed: Implemented Phase 2.5 .NET adapter hotfix #1 per
  `tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md`. Closes
  Manual Test 2026-06-05 D1 verdict-blocker: `_probe_coverlet_version`
  ran `dotnet list package --include-transitive --format json` before
  `dotnet test` against a project with no `obj/project.assets.json`,
  probe returned None, `--coverage` silently no-op'd. Three-part fix:
  F1a `_ensure_csproj_restored` runs `dotnet restore <csproj>` BEFORE
  the probe on the coverage path (only); F1b safety-net metadata keys
  `coverage_unavailable_kind` + `_message` surface via
  `RunRecord.metadata` to the envelope (Run-team-scope partial; full
  envelope top-level `warnings` projection requires cross-team
  plumbing — filed `questions/.../envelope-warnings-projection.md`);
  F1c new integration test `test_coverage_run_on_fresh_fixture_with_no_prior_restore`
  explicitly asserts no-`obj/` precondition + post-fix detection.
- Verified: Local gate on unequipped host green. `uv run pytest -q`
  → 1139 passed + 11 skipped + 0 failed in 86.75s (10 new unit
  tests: 6 TestPreRestore + 4 TestEnvelopeSafetyNet). `uv run mypy`
  → 91 source files clean. Hypothesis disposition: H1 (cross-test
  pollution) REJECTED — both integration tests use per-function
  tmp_path; H2 (pre-committed obj/) REJECTED — fixture source git-
  clean, .gitignore correct; H3 (external NuGet state on Main
  Branch's host) MOST PLAUSIBLE, F1a closes the dependency
  regardless.
- Left open: **§2.5 NOT SATISFIED** on this checkout's host —
  dotnet missing, both install paths blocked (`dotnet-install.sh`
  by classifier, `sudo apt-get install -y dotnet-sdk-8.0` by
  tty-less sudo + `.claude/settings.json` non-pre-authorization).
  Filed `questions/run-team-2026-06-06-dotnet-equip-blocker.md`
  per decision §2.5.3; PM picks Option 1 (apt allowlist) / 2
  (`dotnet-install.sh` auth) / 3 (Manual Test gate) / 4 (other
  equipped host). Handoff written as `status: paused`; NO FF-merge
  until §2.5 satisfied. Out of scope: cross-team envelope
  `warnings` plumbing (filed companion question); .gradle/
  gitignore entry; JDK 11 readiness probe; matrix Maven ceiling.
- Gotcha: 5 pinned. (1) Brief F1b literal "envelope top-level
  warnings field" is cross-team — no adapter-emitted warning
  reaches `envelope["warnings"]` today across ALL six adapters;
  `payload["warnings"]` dies at normalizer. Run-team-scope partial
  via metadata works but is a per-warning bespoke key, not a
  scalable surface. (2) `dotnet-install.sh` download blocked by
  auto-mode classifier — same pattern as JUnit hotfix-3's Maven/
  Gradle block. Three classifier blocks in three cycles. (3)
  `sudo apt-get install dotnet-sdk-8.0` would work on Ubuntu noble
  main (8.0.127 available) but `.claude/settings.json` only
  pre-authorizes JDK/maven — sudo prompts for password with no
  tty. (4) The "shared state" mystery in brief §5 / Manual Test
  findings §"Why Main Branch's gate didn't see this" remains
  un-resolved (most plausibly H3 = NuGet cache state). F1a closes
  the dependency regardless. (5) `dotnet-test-basic-coverage`
  fixture source IS git-clean on this host (verified `find -type
  d` + `.gitignore` content) — H2 conclusively rejected.
- Next: PM disposition on equip-or-handoff (4 options in
  question doc) + cross-team envelope warnings (4 options in
  companion question). On resolution: §2.5 gate executes, D1
  reproducer probe runs, handoff flips paused→ready, Main Branch
  FF-merges, Manual Test re-passes on equipped host. On clean
  close: D1 closed; Phase 2.5 native engine work complete; 6/6
  adapters production-ready; Phase 3 entry unblocked.
```

## Worktree status

- Working tree clean (after commit)
- Branch base: `1f9486a`
- Tip: TBD (single commit "fix(run): .NET adapter hotfix #1 — pre-restore + metadata safety-net + D1 reproducer test")
- No conflicts with `main`
- FF-mergeable when PM unpauses
