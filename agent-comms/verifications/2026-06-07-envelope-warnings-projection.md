---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-06-07
slug: envelope-warnings-projection
status: ready-for-verification
merged_commit: 04420d22b5a72cd687d7aaf8ba2d1dcaa126a608
source_handoff: agent-comms/handoffs/run-team-2026-06-07-envelope-warnings-projection.md
source_task: agent-comms/tasks/run-team-2026-06-06-envelope-warnings-projection.md
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
---

# Verification — envelope-warnings-projection (Option C MVP-blocking slice)

## TL;DR

Adapter-emitted warnings now reach the JSON envelope's top-level `warnings`
field. The v1 metadata channel (`metadata.coverage_unavailable_*` +
`payload["warnings"]`) stays populated in lockstep — backward compatibility
preserved. 4 catalog rows (`dotnet/engine-misconfigured` +
`dotnet/xunit-v3-coverage-deferred` + `junit/missing-jacoco` +
`junit/ambiguous-build-tool`) project; cargo / pytest / jest / gotest have
no warning-emit sites today but the plumbing is wired and the envelope
unconditionally carries `warnings: []` for those engines.

## Merge summary

| Field | Value |
|---|---|
| Merged commit | `04420d22b5a72cd687d7aaf8ba2d1dcaa126a608` (FF from `130a5eb`) |
| Source feat commit | `c2340e8f0845a0ffd9401216931e7f88827a1c0e` |
| Source handoff | `agent-comms/handoffs/run-team-2026-06-07-envelope-warnings-projection.md` |
| Merge mode | `--ff-only` (worktree base = current main tip exactly; 2 commits ahead; pure FF) |
| Conflict resolution | None required (zero overlap with main tip) |
| Files touched | 20 (10 src + 7 tests + 1 handoff + INDEX + WORKLOG) |
| Delta | +1476 / −120 |

## Pre-merge gate (executed on merged tip)

Host: WSL2 Ubuntu (yongjun9461 — the equipped host carrying through dotnet
hotfix #1 + cargo CLI orchestration + JUnit hotfix-3). Toolchain shim
`source ~/.local/share/novetest-toolchains.sh` banner:
`[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5`.

| Check | Command | Result |
|---|---|---|
| Default suite | `uv run pytest -q tests/unit tests/integration` | **1166 passed + 5 skipped + 0 failed in 120.80s** |
| mypy --strict | `uv run mypy` | **clean, 91 source files** |

Skip breakdown matches Run team's pre-handoff gate byte for byte: 2 jest
(node missing) + 2 gotest (go missing) + 1 maven async (pre-existing
cross-asyncio plugin). All toolchain-driven; none warnings-related.

## Empirical envelope captures (byte-verbatim from merged tip)

All 4 captures executed against `04420d2` via direct venv invocation
(`/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest …`) with the SuT
directory as cwd — the canonical pattern that sidesteps `uv run --directory`
not honoring cwd (Run handoff Gotcha #1, WORKLOG §"Gotcha 4" 2026-06-07).

### Cap-1 — dotnet / `engine-misconfigured` (coverage-requested-but-coverlet-absent)

Reproducer: copy `tests/fixtures/projects/dotnet-test-basic/` to
`/tmp/<SuT>/`, run `novetest init && novetest run --coverage` from
`/tmp/<SuT>/`.

Envelope top-level keys: `['command', 'data', 'errors', 'ok', 'schema', 'warnings']`.

`envelope["warnings"]` (verbatim from `/tmp/nv-cap-r-dotnet/run.json`):

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

**Backward-compat — v1 metadata channel still populated** at
`data.memory_entry.run_record.metadata`:

- `coverage_unavailable_kind`: `"coverlet-absent-or-stale"`
- `coverage_unavailable_message`: starts with `"novetest run --coverage was requested but coverlet.collector could not be detected in the project's package graph after \`dotnet restore\`. The run executed WITHOUT coverage collection. To enable coverage: add <PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" />` … (full string ends with "check the stderr.log artifact for `dotnet restore` errors.")

Other observed envelope facts:
- `data.memory_entry.run_record.engine_name`: `"xunit"`
- `data.memory_entry.run_record.engine_version`: `"8.0.421"` (dotnet SDK; engine-identity convention per `decisions/2026-05-25-supported-engine-matrix.md`)
- `data.memory_entry.run_record.status`: `"failed"` (fixture has intentional failing test)
- `data.memory_entry.run_record.artifact_paths` keys: `['results_dir', 'stderr', 'stdout', 'trx']` — **no `coverage_xml`** (coverage not collected; that's the warning's point)
- `data.memory_entry.run_record.metadata` keys: `['coverage_unavailable_kind', 'coverage_unavailable_message', 'dotnet_sdk_version', 'native_exit_code', 'xunit_version']`
- Process exit: 3 (`EXIT_USER_TESTS_FAILED` — fixture's intentional fail; warning is independent of test outcome)

### Cap-2 — junit / `missing-jacoco` (Maven path)

Reproducer: copy `tests/fixtures/projects/junit-maven-basic/` to
`/tmp/<SuT>/`, strip the `<plugin>…<groupId>org.jacoco</groupId>…</plugin>`
block from `pom.xml`, run `novetest init && novetest run --coverage`.

`envelope["warnings"]` (verbatim from `/tmp/nv-cap-r-junit-missing/run.json`):

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

Process exit: 3 (intentional Maven test failure).

### Cap-3 — junit / `ambiguous-build-tool`

Reproducer: copy `tests/fixtures/projects/junit-maven-basic/` to
`/tmp/<SuT>/`, add a single-line `build.gradle.kts` stub (literal:
`plugins { id("java") }`), run `novetest init && novetest run`
(NO `--coverage` needed — the warning fires unconditionally on
ambiguous-tool detection).

`envelope["warnings"]` (verbatim from `/tmp/nv-cap-r-junit-ambig/run.json`):

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

Process exit: 3 (Maven runs as the tiebreaker; intentional Maven test failure surfaces same as bare run).

### Cap-4 — cargo / empty-warnings control

Reproducer: copy `tests/fixtures/projects/cargo-test-basic/` to
`/tmp/<SuT>/`, run `novetest init && novetest run`.

Envelope facts:
- `envelope["warnings"]`: `[]` (empty list — field IS present, just no warnings emitted)
- `'warnings' in envelope`: `True`
- `data.memory_entry.run_record.engine_name`: `"cargo-test"`

This confirms the new wire-shape: **every Run envelope now carries
`warnings: [...]` unconditionally**, even for engines with zero warning
emit sites today. The field's presence is the contract; emptiness is the
normal state for cargo / pytest / jest / gotest.

Process exit: 3 (cargo-test-basic fixture has an intentional failing test).

## Verification scenarios for Manual Test

### A. Reproduce Cap-1 — dotnet/engine-misconfigured

1. Source toolchain shim: `source ~/.local/share/novetest-toolchains.sh`
2. `mkdir -p /tmp/nv-mt-dotnet && cp -r tests/fixtures/projects/dotnet-test-basic/* /tmp/nv-mt-dotnet/`
3. `cd /tmp/nv-mt-dotnet`
4. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init > init.json`
5. `NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage > run.json`
6. Assert: `jq -e '.warnings | length == 1 and .[0].code == "engine-misconfigured" and .[0].details.coverlet_floor == "6.0.2" and .[0].details.csproj == "MathLib.Tests.csproj"' run.json`
7. Assert: `jq -e '.data.memory_entry.run_record.metadata.coverage_unavailable_kind == "coverlet-absent-or-stale"' run.json` (backward-compat criterion #2)
8. Assert: `jq -e '.data.memory_entry.run_record.artifact_paths | has("coverage_xml") | not' run.json` (no coverage collected)

### B. Reproduce Cap-2 — junit/missing-jacoco (Maven)

1. `mkdir -p /tmp/nv-mt-junit-missing && cp -r tests/fixtures/projects/junit-maven-basic/* /tmp/nv-mt-junit-missing/`
2. Strip the `<plugin>…<groupId>org.jacoco</groupId>…</plugin>` block from `pom.xml`. (Python one-liner:
   `python3 -c "import re; p=open('pom.xml').read(); open('pom.xml','w').write(re.sub(r'\s*<plugin>\s*<groupId>org\.jacoco</groupId>.*?</plugin>','',p,flags=re.DOTALL))"`)
3. `cd /tmp/nv-mt-junit-missing && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage > run.json`
4. Assert: `jq -e '.warnings | length == 1 and .[0].code == "missing-jacoco" and .[0].details.build_tool == "maven"' run.json`

### C. Reproduce Cap-3 — junit/ambiguous-build-tool

1. `mkdir -p /tmp/nv-mt-junit-ambig && cp -r tests/fixtures/projects/junit-maven-basic/* /tmp/nv-mt-junit-ambig/`
2. Add gradle stub: `echo 'plugins { id("java") }' > /tmp/nv-mt-junit-ambig/build.gradle.kts`
3. `cd /tmp/nv-mt-junit-ambig && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run > run.json`
4. Assert: `jq -e '.warnings | length == 1 and .[0].code == "ambiguous-build-tool" and .[0].details.chosen_build_tool == "maven"' run.json`

### D. Reproduce Cap-4 — cargo empty-warnings control

1. `mkdir -p /tmp/nv-mt-cargo && cp -r tests/fixtures/projects/cargo-test-basic/* /tmp/nv-mt-cargo/`
2. `cd /tmp/nv-mt-cargo && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init && NOVETEST_OUTPUT=json /home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run > run.json`
3. Assert: `jq -e '.warnings == []' run.json` (empty list, field present)
4. Assert: `jq -e 'has("warnings")' run.json` (field-presence contract — every run envelope unconditionally carries it now)

### E. Pre-merge gate replication

1. `git fetch origin && git rev-parse origin/main` — confirm tip = `04420d2` (or whatever Coverage slice extends to)
2. `source ~/.local/share/novetest-toolchains.sh`
3. `uv run pytest -q tests/unit tests/integration` — expect 1166+5+0 against the bare envelope-warnings-projection tip
4. `uv run pytest -v tests/integration/run/test_dotnet_warnings.py tests/integration/run/test_junit_warnings.py` — expect 4 passed + 0 skipped + 0 failed in ~17s
5. `uv run mypy` — expect `Success: no issues found in 91 source files`

### F. Field-level identity check (criterion #3 — AdapterWarning ↔ EnvelopeWarning)

The architectural deviation in the handoff replaced `RunOutcome.warnings: tuple[EnvelopeWarning, ...]` with `RunOutcome.warnings: tuple[AdapterWarning, ...]` and added a CLI-boundary projector `_adapter_to_envelope_warnings` in `src/novetest/cli/app.py`. Field shapes must remain identical so the projection is a 1:1 copy.

1. `uv run pytest -v tests/unit/run/test_types.py::TestAdapterWarningStructuralContract::test_adapter_warning_field_names_match_envelope_warning tests/unit/cli/test_envelope_warnings_projection.py` — both batches must pass

### G. Replay engine scope footprint (manual sanity)

The handoff documents a single-line tuple-unpack adjustment in
`src/novetest/replay/engine.py` (`record, _ = await execute_with_engine_context(...)`)
as a mechanical consequence of the authorized `execute()` signature change.
Replay behavior must be unchanged.

1. `uv run pytest -v tests/unit/replay tests/integration/replay 2>&1 | tail -20` — expect no new failures (replay suite green pre- and post-slice)

### H. xUnit v3 deferral (adapter-direct, CLI smoke deferred per handoff §"Open items / surprises" #2)

`tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` covers this via stubbed subprocess because real xUnit 3.x requires Microsoft.Testing.Platform infrastructure unavailable on this host. Manual verification limited to:

1. `uv run pytest -v tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — must pass
2. Confirm via source read: `grep -n 'WARNING_XUNIT_V3_COVERAGE_DEFERRED\|xunit-v3-coverage-deferred' src/novetest/run/adapters/dotnet_adapter.py` — kind constant exists

## Critical edge cases worth probing

1. **`payload["warnings"]` legacy channel** — backward-compat criterion #2 mandates the legacy `result.payload["warnings"]` keeps working in lockstep with the new envelope-level field. The 4 adapter emit sites in `dotnet_adapter.py` and 4 in `junit_adapter.py` dual-write. Spot-check via `jq '.data.memory_entry.run_record.payload.warnings // empty' /tmp/nv-mt-dotnet/run.json` on Cap-1's capture — expect a list mirroring the envelope-level warnings entry (modulo field-name parity).

2. **Warning ordering across multiple emit sites** — single-warning captures don't exercise ordering. If a future SuT emits multiple kinds in one run (e.g. `coverlet-absent` + `xunit-v3-coverage-deferred` simultaneously), the array order should be insertion order (adapter's emit sequence). Currently no test covers multi-warning ordering; flagging as informational.

3. **Cap-1 absence of `coverage_xml` artifact path** — coverage was requested but no `coverage_xml` got registered because the warning fires BEFORE the test invocation. Manual Test cross-check: `jq -e '.data.memory_entry.run_record.artifact_paths | has("coverage_xml") | not' /tmp/nv-mt-dotnet/run.json`.

4. **Cap-3 trigger is build-tool detection, NOT coverage** — the `ambiguous-build-tool` warning fires from the engine selector during dispatch, before `--coverage` is consulted. Manual Test confirms by reproducing WITHOUT `--coverage` (scenario C step 3 above) — warning still fires.

5. **Cap-4 wire-shape contract is the empty list `[]`, NOT absence** — pre-slice the `warnings` field was either absent or always empty across run/test envelopes; post-slice the field is unconditionally present. Manual Test asserts BOTH `jq -e '.warnings == []'` AND `jq -e 'has("warnings")'`.

6. **JUnit `engine-misconfigured` brief-catalog row** — the handoff §"Brief §1.1 catalog deviation" reports the JUnit adapter does NOT emit `engine-misconfigured` as a payload warning (the kind is emitted by the .NET adapter and by readiness probe as an error). No integration test covers that misattributed row; Manual Test confirms via `grep -rn 'engine-misconfigured' src/novetest/run/adapters/junit_adapter.py` — expect zero hits.

7. **dotnet-test-basic vs dotnet-test-basic-coverage fixture distinction** — Cap-1 uses the `dotnet-test-basic` fixture (NO coverlet declared in csproj) because that's the fixture that triggers the warning. The `dotnet-test-basic-coverage` fixture (which DOES declare coverlet) would NOT trigger the warning. Manual Test confirms by inspecting `MathLib.Tests.csproj` in each fixture.

8. **`metadata.dotnet_sdk_version` vs `engine_version` distinction** — both record the dotnet SDK version (8.0.421 here), but at different envelope paths. `engine_version` is the engine-identity convention pin per `decisions/2026-05-25-supported-engine-matrix.md`; `metadata.dotnet_sdk_version` is the raw probe result. Both must be `"8.0.421"` byte-equal. Sanity: `jq -e '.data.memory_entry.run_record.engine_version == .data.memory_entry.run_record.metadata.dotnet_sdk_version' /tmp/nv-mt-dotnet/run.json`.

## Anything that wasn't obvious during merge

1. **Coverage slice merges atop this one** — `coverage-dotnet-cobertura-derive` is queued for sequential FF merge (conflict expected only on `WORKLOG.md` + `agent-comms/INDEX.md`; zero source-file overlap). Manual Test will see BOTH slices on the same `origin/main` tip; the verification doc for the Coverage slice is filed separately as `2026-06-07-dotnet-cobertura-derive.md`.

2. **No xUnit v3 CLI smoke** — `test_xunit_v3_deferral_emits_envelope_warning_via_adapter` is adapter-direct + stubbed subprocess. The CLI smoke variant was deferred because installing xUnit 3.x on this host requires Microsoft.Testing.Platform infrastructure that the host lacks (deferred per handoff §"Open items / surprises" #2). The warning emit path runs from csproj-string parsing BEFORE any subprocess, so adapter-direct is structurally sufficient. Documented in `test_dotnet_warnings.py` module docstring.

3. **`replay/engine.py` mechanical touch — NOT explicitly authorized but mandatory** — the handoff §"Cross-team scope footprint" calls out the single-line `record, _ = await execute_with_engine_context(...)` tuple unpack in `src/novetest/replay/engine.py` as a forced mechanical consequence of the authorized `execute()` signature change. Behavior unchanged. PM should ratify the scope footprint; flagging for visibility.

4. **`uv run --directory` does NOT honor cwd** — Run handoff Gotcha #1 + Run team's WORKLOG entry 2026-06-07 "Gotcha 4" pin this. Capture commands above use the venv's python directly via `/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest …` with cwd set to the SuT directory. The canonical integration test pattern in `tests/integration/orchestration/conftest.py::run_cli_in` follows the same shape.

5. **2 pre-existing untracked findings files** (from prior Manual Test dotnet hotfix-1 cycle: `manual-test-team-2026-06-06-host-equip.md` + `manual-test-team-2026-06-06-phase2.5-dotnet-adapter-hotfix.md`) remain present in `agent-comms/findings/` — NOT staged or committed by Main Branch per charter (Manual Test territory).

## Cross-team gap notes (forward to PM, NOT blocking this verification)

1. **`payload["warnings"]` legacy mirror** — both adapters dual-write the legacy `payload["warnings"]` AND the new structured tuple. The legacy mirror exists for backward-compat (criterion #2). The amended `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` may want a deprecation timeline now that envelope projection lands — PM judgement.

2. **Multi-warning ordering contract not pinned** — single-warning emit sites in today's adapters don't exercise array ordering. If multi-emit cases land later (.g. v3 deferral + coverlet absent for the same run), an ordering test should accompany the addition.

3. **`coverage_outcome.kind` flip will arrive via separate slice** — Cap-1's `data.memory_entry.run_record.coverage_outcome.kind` would still be `"unavailable"` even on the merged tip; the `"fact-set"` flip arrives via the queued `coverage-dotnet-cobertura-derive` slice (separate verification doc).
