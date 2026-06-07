---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-06-07
slug: dotnet-cobertura-derive
status: ready-for-verification
merged_commit: c1ee2a4921b004cbc7d9a8e78bd481de62c8ab82
source_handoff: agent-comms/handoffs/coverage-team-2026-06-07-dotnet-cobertura-derive.md
source_task: agent-comms/tasks/coverage-team-2026-06-06-dotnet-cobertura-derive.md
related:
  - agent-comms/verifications/2026-06-07-envelope-warnings-projection.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
---

# Verification — dotnet-cobertura-derive (closes 6th-engine Coverage promise)

## TL;DR

`novetest run --coverage` against a .NET project now produces a real
`CoverageFactSet` instead of `CoverageUnavailable`. The headline flip:
`data.coverage_outcome.kind` moves from `"unavailable"` (pre-slice,
flagged as a Critical edge in the envelope-warnings-projection
verification doc) to **`"fact-set"`** (post-slice).
`coverage show` / `coverage diff` / `inspect` Coverage sections all light up.

## Merge summary

| Field | Value |
|---|---|
| Merged commit | `c1ee2a4921b004cbc7d9a8e78bd481de62c8ab82` (FF from `d735a6a` after rebase) |
| Source feat commit (pre-rebase) | `ade29ac027123da41ed73127b64ba21820511f75` |
| Source handoff | `agent-comms/handoffs/coverage-team-2026-06-07-dotnet-cobertura-derive.md` |
| Merge mode | Rebase Coverage worktree onto `d735a6a`, then `--ff-only` (1 commit ahead post-rebase) |
| Files touched (post-rebase) | 10 (3 src + 5 tests/fixtures + 1 handoff + WORKLOG) |
| Delta | +2419 / −24 |

### Conflict resolution

One conflict during rebase, on `WORKLOG.md` top-entry collision:

- The Run slice (`envelope-warnings-projection`, merged immediately before in commit `d735a6a`) added its 2026-06-07 entry as the new top entry.
- The Coverage slice's pre-rebase commit also added a 2026-06-07 entry to the top.
- Resolved per the team's **incoming-on-top convention** for WORKLOG: Coverage entry sits at the top (line 23+), Run entry sits second (line 31+), separated by `---`. Both 2026-06-07 entries are preserved verbatim — neither's content was modified.
- INDEX.md auto-merged cleanly with no conflict (the regen-friendly file shape absorbed both commits' updates without manual intervention).

No source-file conflicts — Run slice owns `run/` + `orchestration/` + `cli/` + `replay/`; Coverage slice owns `coverage/`. Zero overlap.

## Pre-merge gate (executed on merged tip `c1ee2a4`)

Host: same equipped WSL2 Ubuntu host carrying through .NET hotfix #1, cargo CLI orchestration, JUnit hotfix-3, and the envelope-warnings-projection slice immediately prior. Toolchain shim sourced via
`source ~/.local/share/novetest-toolchains.sh` — banner:
`[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5`.

| Check | Command | Result |
|---|---|---|
| Default suite | `uv run pytest -q tests/unit tests/integration` | **1197 passed + 5 skipped + 0 failed in 127.16s** |
| mypy --strict | `uv run mypy` | **clean, 92 source files** |

Test arithmetic: 1166 (post-Run-slice baseline) + 31 (Coverage slice's new tests: 19 cobertura_parser + 11 derive-xunit + 1 dotnet cobertura derive E2E) = **1197 expected, 1197 observed**. mypy adds +1 source file (`cobertura_parser.py`) bringing 91 → **92**.

Skip breakdown unchanged from prior slice: 2 jest + 2 gotest + 1 maven async (all toolchain-driven).

## Empirical envelope captures (byte-verbatim from merged tip)

5 CLI smokes captured against `/tmp/nv-cap-c-dotnet/` — a clean copy of `tests/fixtures/projects/dotnet-test-basic-coverage/` (which **does** declare `<PackageReference Include="coverlet.collector" Version="6.0.2" />`). Run IDs differ run-to-run; values below are from this Main Branch capture session.

### Cap-1 — `novetest init`

```
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init
```

Exit: `0`. Envelope: `{"ok": true, "command": "init", ...}`.

### Cap-2 — `novetest run --coverage` (the headline flip)

```
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage
```

Exit: `3` (intentional failing test in fixture).

Envelope facts (verbatim):

- `envelope["ok"]`: `true`
- `envelope["command"]`: `"run"`
- `envelope["warnings"]`: `[]` (the wire-shape contract from the prior slice — Coverage cases emit no adapter warnings on the happy path)
- `data.memory_entry.entry_id`: `"01KTH76B2HF5KSE3Y9679EW2D3"` (this capture)
- `data.memory_entry.has_coverage_facts`: **`true`** (was `false` pre-slice)
- **`data.coverage_outcome.kind`**: **`"fact-set"`** ← **the headline flip** (was `"unavailable"` pre-slice)
- `data.coverage_outcome.mapping_granularity`: `"aggregate"` (decision `2026-06-03 §3` amended literal pin)
- `data.coverage_outcome.summary`:
  ```json
  {
    "covered_branches": 0,
    "covered_statements": 2,
    "excluded_statements": 0,
    "missing_branches": 0,
    "missing_statements": 0,
    "num_branches": 0,
    "num_statements": 2,
    "percent_covered": 100.0
  }
  ```
- `data.coverage_outcome.run_reference.run_id`: same ULID as `entry_id`
- `data.memory_entry.run_record.engine_name`: `"xunit"`
- `data.memory_entry.run_record.engine_version`: `"8.0.421"` (dotnet SDK; engine-identity convention)
- `data.memory_entry.run_record.artifact_paths` keys: `['coverage_xml', 'results_dir', 'runsettings', 'stderr', 'stdout', 'trx']` — **`coverage_xml` IS registered** (single string path; e.g. `run/artifacts/run_<ULID>/native/TestResults/<GUID>/coverage.cobertura.xml`)
- `data.memory_entry.run_record.metadata`:
  ```json
  {
    "coverage_mapping_granularity": "aggregate",
    "coverlet_version": "6.0.2",
    "dotnet_sdk_version": "8.0.421",
    "native_exit_code": 1,
    "xunit_version": "2.6.0"
  }
  ```
- **No** `coverage_unavailable_kind` / `coverage_unavailable_message` (F1b safety-net inverse-confirmed: it should NOT fire on the happy path where coverlet IS declared)

### Cap-3 — `novetest inspect <run_id>`

```
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest inspect 01KTH76B2HF5KSE3Y9679EW2D3
```

Exit: `0`. Envelope facts:

- `envelope["command"]`: `"inspect"`
- `data.sub_reports.coverage`: `"available"` (was `"unavailable"` pre-slice)
- `data.coverage_outcome.kind`: `"fact-set"` + same summary block as Cap-2

### Cap-4 — `novetest coverage show <run_id>`

```
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest coverage show 01KTH76B2HF5KSE3Y9679EW2D3
```

Exit: `0`. Envelope facts:

- `envelope["command"]`: `"coverage.show"`
- `data.coverage_outcome.kind`: `"fact-set"`
- `data.coverage_outcome.mapping_granularity`: `"aggregate"`
- `data.coverage_outcome.summary.percent_covered`: `100.0`
- `data.coverage_outcome.summary.num_statements`: `2`
- `data.coverage_outcome.summary.covered_statements`: `2`

**Empirical surprise — flagged for Manual Test**: the `coverage show` envelope at `data.coverage_outcome` carries ONLY the aggregate summary block (kind, mapping_granularity, run_reference, summary) — there is no per-file array at the `data.coverage_outcome` level for this verb. The Cap-2 path persists the full per-file `CoverageFactSet` (visible via `has_coverage_facts=true` and the `coverage_xml` artifact registered for the run), but the `coverage show` CLI representation surfaces the aggregate view. The Coverage handoff §"DoD bullet 6" says "`coverage show` returns structured per-file coverage" — interpretation: persisted, available in derived fact-set, but the CLI's default `coverage show` envelope is aggregate. Manual Test should confirm whether this is intended.

### Cap-5 — `novetest coverage diff <run1> <run2>` (identical re-runs)

```
# Second run on same workspace
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage
# → run_id 01KTH78X38M806XN9BB6E5N14F
NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest coverage diff 01KTH76B2HF5KSE3Y9679EW2D3 01KTH78X38M806XN9BB6E5N14F
```

Exit: `0`. Envelope facts:

- `envelope["command"]`: `"coverage.diff"`
- `data.coverage_delta.kind`: `"delta"`
- `data.coverage_delta.baseline_granularity`: `"aggregate"`
- `data.coverage_delta.target_granularity`: `"aggregate"`
- `data.coverage_delta.file_deltas`: `[]` (identical re-runs)
- `data.coverage_delta.files_added`: `[]`
- `data.coverage_delta.files_removed`: `[]`
- `data.coverage_delta.summary_before.percent_covered`: `100.0`
- `data.coverage_delta.summary_after.percent_covered`: `100.0`
- `data.coverage_delta.baseline_run_reference.run_id`: `01KTH76B2HF5KSE3Y9679EW2D3`
- `data.coverage_delta.target_run_reference.run_id`: `01KTH78X38M806XN9BB6E5N14F`

## Verification scenarios for Manual Test

### A. Reproduce Cap-2 — the headline flip

1. `source ~/.local/share/novetest-toolchains.sh` (banner must show `dotnet=8.0.421`)
2. `mkdir -p /tmp/nv-mt-cob && cp -r tests/fixtures/projects/dotnet-test-basic-coverage/* /tmp/nv-mt-cob/`
3. `cd /tmp/nv-mt-cob`
4. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init > init.json`
5. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage > run.json`
6. Assert: `jq -e '.data.coverage_outcome.kind == "fact-set"' run.json` ← **headline flip**
7. Assert: `jq -e '.data.coverage_outcome.mapping_granularity == "aggregate"' run.json`
8. Assert: `jq -e '.data.coverage_outcome.summary.num_statements == 2 and .data.coverage_outcome.summary.covered_statements == 2 and .data.coverage_outcome.summary.percent_covered == 100.0' run.json`
9. Assert: `jq -e '.data.memory_entry.has_coverage_facts == true' run.json`
10. Assert: `jq -e '.data.memory_entry.run_record.artifact_paths | has("coverage_xml") and has("runsettings")' run.json`
11. Assert: `jq -e '.data.memory_entry.run_record.metadata.coverlet_version == "6.0.2"' run.json`
12. Assert: `jq -e '.data.memory_entry.run_record.metadata.coverage_mapping_granularity == "aggregate"' run.json`
13. Assert: `jq -e '.data.memory_entry.run_record.metadata | has("coverage_unavailable_kind") | not' run.json` (F1b safety-net inverse — must NOT fire on happy path)
14. Assert: `jq -e '.warnings == []' run.json` (no adapter warning on happy path)

### B. Reproduce Cap-3 — inspect lights up

Pre-condition: Scenario A completed; note the `run_id` (e.g. `jq -r '.data.memory_entry.entry_id' run.json`).

1. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest inspect <RUN_ID> > inspect.json`
2. Assert: `jq -e '.data.sub_reports.coverage == "available"' inspect.json`
3. Assert: `jq -e '.data.coverage_outcome.kind == "fact-set"' inspect.json`
4. Assert: `jq -e '.data.coverage_outcome.summary == (input | .data.coverage_outcome.summary)' inspect.json run.json` (cross-check: inspect's summary matches the source run's)

### C. Reproduce Cap-4 — coverage show

1. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest coverage show <RUN_ID> > show.json`
2. Assert: `jq -e '.data.coverage_outcome.kind == "fact-set" and .data.coverage_outcome.mapping_granularity == "aggregate" and .data.coverage_outcome.summary.percent_covered == 100.0' show.json`
3. (Manual Test judgment) Inspect whether per-file detail is expected here vs. the aggregate-only envelope shape (see Critical edge #4 below).

### D. Reproduce Cap-5 — coverage diff (identical re-runs)

1. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage > run2.json`
2. `RUN_2=$(jq -r '.data.memory_entry.entry_id' run2.json)`
3. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest coverage diff <RUN_ID> $RUN_2 > diff.json`
4. Assert: `jq -e '.data.coverage_delta.kind == "delta" and .data.coverage_delta.file_deltas == [] and .data.coverage_delta.files_added == [] and .data.coverage_delta.files_removed == []' diff.json`
5. Assert: `jq -e '.data.coverage_delta.summary_before.percent_covered == 100.0 and .data.coverage_delta.summary_after.percent_covered == 100.0' diff.json`

### E. Pre-merge gate replication

1. `git fetch origin && git rev-parse origin/main` — confirm tip = `c1ee2a4` (or whatever the push lands)
2. `source ~/.local/share/novetest-toolchains.sh`
3. `uv run pytest -v tests/integration/run/test_dotnet_coverage.py tests/integration/coverage/test_dotnet_cobertura_derive.py` — expect **4 passed + 0 skipped + 0 failed**
4. `uv run pytest -q tests/unit tests/integration` — expect **1197 passed + 5 skipped + 0 failed**
5. `uv run mypy` — expect `Success: no issues found in 92 source files`

### F. Backward-compat — non-.NET coverage paths unchanged

Coverage slice extends derive dispatch via a new engine-name branch (`xunit`) but must not regress the existing 4 paths (coverage.py JSON, Istanbul JSON, LCOV, JaCoCo XML).

1. `uv run pytest -v tests/unit/coverage 2>&1 | tail -25` — expect all pre-existing parser/derive test classes green (test_derive_pytest, test_derive_jest, test_derive_junit, test_derive_cargo all pass alongside the new test_derive_xunit + test_cobertura_parser)

### G. §2.4 source-resolution edge — sources-not-found discriminator

The Coverage handoff documents a §2.4 path where sources whose resolved path no longer exists on disk are silently dropped at the derive layer. If ALL files drop, the derive returns `CoverageUnavailable(missing-native-payload)` with literal `cobertura-sources-not-found` discriminator.

1. `uv run pytest -v tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_partial_survival_drops_only_missing_files` — both must pass

### H. Engine-name dispatch + mypy

Coverage slice pins `_XUNIT_ENGINE_NAME = "xunit"` at the derive layer and shares the `coverage_xml` artifact key with JUnit (engine-name discriminates the right parser).

1. `uv run pytest -v tests/unit/coverage/test_derive_xunit.py -k routes` — must pass (engine-name discrimination)
2. `uv run mypy src/novetest/coverage` — must show `Success` (Coverage submodule isolated check)

## Critical edge cases worth probing

1. **`metadata.coverlet_version` accuracy** — Cap-2 shows `coverlet_version="6.0.2"`. The fixture pins `<PackageReference Include="coverlet.collector" Version="6.0.2" />`. If a future fixture bumps the pin, this metadata key must follow. Manual Test cross-checks by reading `tests/fixtures/projects/dotnet-test-basic-coverage/MathLib.Tests/MathLib.Tests.csproj` and confirming the version literal matches `metadata.coverlet_version`.

2. **`coverage_xml` artifact path is a SINGLE string** — not a list; the corrected D2 path established in `verifications/2026-06-06-phase2.5-dotnet-adapter-hotfix.md`. Manual Test: `jq -e '.data.memory_entry.run_record.artifact_paths.coverage_xml | type == "string"' run.json`.

3. **`runsettings` artifact registered alongside `coverage_xml`** — new in this slice's happy path (per-run hermetic runsettings at `<artifact_dir>/native/coverlet.runsettings`). Manual Test: `jq -e '.data.memory_entry.run_record.artifact_paths | has("runsettings")' run.json`. Open the runsettings file at the artifact path and confirm it contains the `<PerTestCoverage>true</PerTestCoverage>` element per amended decision `2026-06-03 §3` (the element is empirically inert via XPlat data collector path but kept for forward-compat).

4. **`coverage show` aggregate-only envelope shape** — Cap-4 surfaces ONLY the aggregate `summary` at `data.coverage_outcome`. No per-file array at the verb-level envelope. The persisted fact set DOES contain per-file detail (verified via `has_coverage_facts=true` and the registered `coverage_xml` artifact); the question is whether `coverage show`'s CLI representation is expected to bubble the per-file detail up or whether the aggregate is sufficient for the v1 contract. Coverage handoff §"DoD bullet 6" claims "structured per-file coverage" — Manual Test verifies whether the persisted fact-set is examinable via some other verb / flag, or if this is a deliberate aggregate-default with future per-file opt-in.

5. **§2.4 sources-not-found discriminator literal** — when all files drop, the derive returns `CoverageUnavailable` with detail containing `cobertura-sources-not-found`. Today's literal is free-form text (matches existing JaCoCo / LCOV "missing-native-payload" detail strings); Coverage handoff Q3 flags this as potential future structured-discriminator follow-up. Manual Test confirms the literal appears via `tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found`.

6. **`mapping_granularity = "aggregate"` is the literal pin** — decision `2026-06-03 §3` ratifies aggregate-effective-default for v1; per-test deferred until upstream Coverlet XPlat fix. If Manual Test observes `"per-test"` ever surfacing in the envelope, that signals an upstream Coverlet release fixed PerTestCoverage AND the parser's directory-shape branch is firing (unit test `test_derive_xunit_directory_artifact_globs_xml_children` covers the branch; today's runtime envelope should always be `"aggregate"`).

7. **`branch_arc_semantics = "branches-omitted"` metadata pin** — v1 Cobertura parser drops `branch="true"` + `condition-coverage` attrs to match JaCoCo's lines-only v1 scope. The metadata pin makes the absence machine-distinguishable from "no branches were detected". Manual Test confirms via `jq -e '.data.memory_entry.run_record.metadata // {} | has("branch_arc_semantics") | not' run.json` — wait, this pin actually lives at the `coverage_fact_set.metadata` level not `run_record.metadata`. Manual Test verifies by inspecting the persisted fact set if there's a CLI path that exposes it; otherwise via `coverage show`-style verbs.

8. **WORKLOG conflict resolution preserves both entries verbatim** — the Coverage entry and the Run entry are both 2026-06-07-dated. After this slice merges, WORKLOG's top entry is the Coverage one, second is the Run one. Both entries' bullet text is byte-equivalent to what the respective teams wrote (no surgical edits to entry content). Manual Test can sanity-check via `head -45 WORKLOG.md` — expect Coverage entry first, then `---`, then Run entry.

## Anything that wasn't obvious during merge

1. **Rebase + FF merge sequence** — Coverage worktree's base was `130a5eb` (the queueing commit). After the Run slice landed at `d735a6a`, Coverage was rebased onto `d735a6a`, producing post-rebase tip `c1ee2a4`. The single WORKLOG conflict was resolved per the incoming-on-top convention. Coverage's INDEX update auto-merged cleanly (regen-friendly file).

2. **The headline flip's "pre-slice → post-slice" interplay with the prior verification doc** — `verifications/2026-06-07-envelope-warnings-projection.md` §"Cross-team gap notes" #3 explicitly anticipated this: "Cap-1's `data.memory_entry.run_record.coverage_outcome.kind` would still be `unavailable` even on the merged tip; the `fact-set` flip arrives via the queued `coverage-dotnet-cobertura-derive` slice (separate verification doc)." This document IS that separate verification doc; the flip lands here.

3. **`coverage_outcome` envelope path corrected** — the gap-note in the prior verification doc said `data.memory_entry.run_record.coverage_outcome.kind` but empirical capture shows the actual location is `data.coverage_outcome.kind` (sibling of `memory_entry`, not nested under `run_record`). This document uses the empirically-correct path. Manual Test should NOT use the prior-doc path literally.

4. **Cap-1 from prior verification doc (dotnet/engine-misconfigured) is on a DIFFERENT fixture** — that one uses `dotnet-test-basic` (NO coverlet declared). This document's Cap-2 uses `dotnet-test-basic-coverage` (coverlet declared). Both fixtures must remain in tree; they exercise different envelope paths. Manual Test confirms by `ls tests/fixtures/projects/ | grep dotnet`.

5. **5 pre-existing skips** unchanged from prior slice: 2 jest (node missing) + 2 gotest (go missing) + 1 maven async. Toolchain-driven, none .NET-related.

6. **WORKLOG bottom anchor unchanged** — the 2026-06-06 entries below the two new 2026-06-07 entries are byte-identical to pre-merge `main` (the rebase didn't touch them). Cross-check: `git diff d735a6a..c1ee2a4 -- WORKLOG.md` should show only the new Coverage top entry added.

## Cross-team gap notes (forward to PM, NOT blocking this verification)

1. **`coverage show` per-file representation** — open question whether the aggregate-only envelope at `data.coverage_outcome` for `coverage show <run_id>` is the intended v1 contract or whether per-file detail should bubble up. PM judgment.

2. **`sources-not-found` discriminator structuring** — Coverage handoff Q3 flags potential future addition of `reason_kind` / `reason_detail` split to `CoverageUnavailable` for AI consumers. Free-form text works today; structured field is a polish backlog candidate.

3. **CI matrix .NET cell** — Coverage handoff Q5 flags that `test_dotnet_cobertura_derive.py` skips without `dotnet` on PATH. Currently CI lanes don't include .NET; the test skips in CI today. Release team backlog item.

4. **Cobertura branches deferral vs JaCoCo's synthesized branch facts** — Coverage handoff Q2 notes a partial drift: JaCoCo emits synthesized branch indices via cb/mb counters; Cobertura v1 emits zero (with `branch_arc_semantics = "branches-omitted"` metadata pin). PM may want to align in a post-MVP polish cycle.

5. **Phase 2/3 6th-engine Coverage promise is now closed** — combined with the envelope-warnings-projection slice immediately prior, BOTH MVP-blocking briefs from `commits 130a5eb` ("comms: queue 2 parallel MVP-blocking briefs") now land. PM's cycle-close ratifies the 12 DoD bullets in the Coverage handoff + the 11 DoD bullets in the Run handoff once Manual Test passes both verifications.
