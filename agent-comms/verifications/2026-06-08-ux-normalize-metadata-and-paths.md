---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-08
slug: ux-normalize-metadata-and-paths
related:
  - agent-comms/handoffs/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
  - agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
---

# Verification — Localization UX normalization (B2-1 metadata + B2-2 paths)

## Merged commit + summary

- **Merged commit on main**: `6ebad33` (final B2 cycle tip — sequential FF: coverage → localization → run); the localization slice itself landed at intermediate tip `304e8f1`.
- **Source handoff consumed**: `agent-comms/handoffs/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`.
- **One-line summary**: Two mode-level UX asymmetries closed. **B2-1**: `derive.py::_derive_per_test` now passes `metadata={"changed_files_count": None, "regression_reweighted": None}` to `LocalizationFinding(...)` (was previously falling through to empty `{}` via `default_factory`). The `None` (vs `0` / `False`) is a deliberate discriminator: per-test does NOT consult RegressionFactSet (structural noop), while aggregate / failure_proximity DO consult it and surface `int` / `bool`. **B2-2**: `failure_proximity.py::derive_failure_proximity` now feeds parsed `file_path`s through a new internal helper `_normalize_to_workspace_relative(file_path, workspace_root)` BEFORE aggregation, so absolute paths under the workspace root land as workspace-relative in the envelope. `workspace_root = store.path.parent`. Outside-workspace absolute paths (stdlib frames, `/rustc/<hash>/...`) are kept absolute as a "not your code" cue. No model schema change. No `EnvelopeWarning` shape change.

## Wire-level envelope shape (pinned from merged source)

Verified by reading `src/novetest/cli/app.py::_localization_outcome_payload` + `src/novetest/models/localization_finding.py::LocalizationFinding.to_dict()`:

```
data.localization_outcome.kind                                  # "fact-set" | "unavailable"
data.localization_outcome.run_reference                         # dict (run_id/workspace_hash/...)
data.localization_outcome.mode                                  # "sbfl_per_test" | "sbfl_aggregate" | "failure_proximity"
data.localization_outcome.formula                               # "ochiai" | "op2" | "dstar" | "tarantula"
data.localization_outcome.entries[*].code_location.file         # workspace-relative across ALL 3 modes
data.localization_outcome.entries[*].code_location.kind         # "symbol" | "line" | "branch" | "file"
data.localization_outcome.entries[*].code_location.primary_line # int
data.localization_outcome.metadata.changed_files_count          # int | null (null only on sbfl_per_test)
data.localization_outcome.metadata.regression_reweighted        # bool | null (null only on sbfl_per_test)
```

**Note**: `_localization_outcome_payload` spreads `outcome.to_dict()` directly into the `data.localization_outcome` block AFTER popping the top-level `schema_version`. So `entries` / `metadata` / `mode` / `formula` etc. sit directly under `data.localization_outcome.*` — not nested inside `data.localization_outcome.localization_finding.*`.

## What did NOT change (regression safety per brief §"Out of scope")

- No change to sbfl_* modes' path emission — they were already workspace-relative via the `CoverageFactSet.files[*].file_path` contract.
- No change to `localization-cache-rederived` warning code (or any other CLI warning shape).
- No mode algorithmic-definition changes (placeholder formula in `failure_proximity` stays — that's a mode definition, not a bug).
- No `cli/output.py::EnvelopeWarning` shape changes (frozen 2026-06-07).
- No touches to Coverage / Run / Regression / Replay / Memory / Orchestration territory (the two B2 sibling slices in this cycle are fully disjoint).
- No `LocalizationFinding.metadata` schema bump (already `dict[str, Any]`, accepts `None` values).

## Verification scenarios (target host = general)

§2.5 equip-and-exercise gate does NOT fire for this slice. General host is acceptable.

### Scenario A — 3-mode metadata matrix (load-bearing B2-1 evidence)

The 3-mode integration matrix is already pinned via three E2E tests. Re-run all three to confirm:

```bash
cd /home/yjshin/dev/aispace/Nove-Test
uv run pytest -v \
  tests/integration/localization/test_localization_branch_basic.py::test_localization_run_against_branch_fixture_ranks_buggy_function_top \
  tests/integration/localization/test_aggregate_mode_e2e.py::test_localization_aggregate_run_against_cargo_fixture_ranks_buggy_file_top \
  tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top
```

Expected — all three pass (or aggregate/failure_proximity cleanly skip if cargo toolchain isn't equipped). The per-test variant runs always (pure pytest fixture). Each test pins the corresponding row of the matrix:

| Mode | `metadata.changed_files_count` | `metadata.regression_reweighted` | `code_location.file` |
|---|---|---|---|
| `sbfl_per_test` | `None` (the structural-noop discriminator) | `None` | workspace-relative |
| `sbfl_aggregate` | `int` (≥ 0) | `bool` | workspace-relative |
| `failure_proximity` | `int` (≥ 0) | `bool` | workspace-relative — load-bearing for B2-2 |

### Scenario B — failure_proximity wire-level CLI (load-bearing B2-2 evidence)

Construct a no-coverage Python run, derive failure_proximity findings, inspect the envelope path-relativity:

```bash
cd /tmp && rm -rf novetest-fp-smoke-$$ && mkdir novetest-fp-smoke-$$ && cd novetest-fp-smoke-$$
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/localization-no-coverage .
cd localization-no-coverage
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run | tee /tmp/fp-run.json | python3 -c "import json,sys; r=json.load(sys.stdin); print('run_id:', r['data']['run_reference']['run_id'])"
RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/fp-run.json'))['data']['run_reference']['run_id'])")
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest localization "$RUN_ID" > /tmp/fp-loc.json
python3 << 'PYEOF'
import json
from pathlib import Path
e = json.load(open('/tmp/fp-loc.json'))
oc = e['data']['localization_outcome']
print('kind:', oc['kind'])
print('mode:', oc.get('mode'))
print('formula:', oc.get('formula'))
print('metadata:', oc.get('metadata'))
entries = oc.get('entries', [])
print('entry count:', len(entries))
abs_files = [en['code_location']['file'] for en in entries if Path(en['code_location']['file']).is_absolute()]
print('absolute file count (workspace-internal must be 0):', len(abs_files))
if entries:
    print('sample files:', [en['code_location']['file'] for en in entries[:3]])
PYEOF
```

Expected:
- `kind: fact-set`
- `mode: failure_proximity`
- `formula: ochiai` (the placeholder per the mode definition)
- `metadata: {'changed_files_count': <int>, 'regression_reweighted': <bool>}` — both keys present, values are `int` / `bool` (NOT `None` — failure_proximity DOES consult RegressionFactSet).
- `absolute file count (workspace-internal must be 0): 0` — load-bearing for B2-2.
- Sample files look like `localization_no_coverage/statistics.py` (workspace-relative), NOT `/tmp/pytest-of-yjshin/.../localization-no-coverage/localization_no_coverage/statistics.py`.

### Scenario C — sbfl_per_test discriminator pin (B2-1 negative-control)

The per-test mode's discriminator (both metadata values `null`) is the key novel-shape for downstream consumers (they should NOT confuse "structural noop" with "consulted, no boost"):

```bash
uv run pytest -v \
  tests/unit/localization/test_derive.py::test_per_test_metadata_has_mode_invariant_keys_with_none_values \
  tests/unit/localization/test_derive.py::test_per_test_metadata_survives_persistence_roundtrip
```

Expected: both green. The roundtrip test catches the `dict[str, Any]` JSON-serialization-of-None nuance.

### Scenario D — failure_proximity path-normalization unit matrix

```bash
uv run pytest -v \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_workspace_internal_path_normalized_to_relative \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_path_outside_workspace_kept_absolute \
  tests/unit/localization/test_derive_failure_proximity.py::test_relative_path_passes_through_unchanged \
  tests/unit/localization/test_derive_failure_proximity.py::test_absolute_and_relative_for_same_file_collapse_to_relative
```

Expected: all 4 green. The last is the load-bearing aggregation-before-normalization invariant (a file accessed via both absolute and relative spellings collapses into ONE relative entry with combined `score_raw == 2.0`).

### Scenario E — spec doc reads cleanly

Read `design/interace-contract/localization.md` end-to-end. Confirm the new "Result shape — mode-invariant" subsection at the bottom carries:
1. A 3-column metadata key table (key / per-test / aggregate-or-failure_proximity).
2. A `code_location.file` representation paragraph stating "workspace-relative across all three modes".
3. An explicit edge-case paragraph for absolute-out-of-workspace paths (kept absolute as a "not your code" cue).

## Critical edge cases worth probing

1. **Discriminator semantics** (per-test `None` vs failure_proximity `0` / `False`): a downstream consumer that wants to know "did this finding come from a mode that consulted the RegressionFactSet?" can read `metadata.regression_reweighted is None` to discriminate. Do NOT collapse `None` with `False` in any consumer.
2. **Outside-workspace stdlib leakage**: pytest tracebacks sometimes include `/usr/lib/python3.11/...` frames. The failure_proximity helper's `except ValueError` branch keeps these absolute (defensive — same posture as Defect-3 cargo stdlib-pollution). Confirm no Manual-Test invocation surfaces a stdlib path as a top entry; if one does, it's a fixture issue (not a slice regression).
3. **Symlink handling intentionally NOT addressed**: `Path.resolve()` deliberately NOT called on either side of `relative_to` (handoff §Gotcha #2). If a host has symlinked `tmp_path` and Manual Test sees an absolute file_path leaking that wouldn't normally, that's a containerized / NFS / Docker-bind-mount scenario worth filing — but the v1 design choice was "conservative non-resolving start; add resolve() if real-host evidence emerges".
4. **No `RunRecord.workspace_path` field exists** (handoff §"Open items"): the brief incorrectly claimed one. PM disposition open — if cross-machine fact-set transport / replay needs a top-level field, that's a separate Memory-team slice.

## Conflict resolution during merge

- **WORKLOG.md conflict during the localization rebase** (expected — coverage + localization + run all add 2026-06-08 top entries). Resolved by preserving all entries, separated by `---` dividers. Localization was placed above coverage in the rebase resolution (newest-on-top within the cycle). Then when run rebased, the same pattern repeated with run placed on top.
- No source-code conflicts (3 file footprints fully disjoint).

## Test gate (post-merge, full main tip `6ebad33`)

```
$ uv run mypy --strict src/novetest
Success: no issues found in 92 source files

$ uv run pytest -q tests/unit tests/integration
1209 passed, 23 skipped, 1 failed in 33.26s
```

The 1 failure is the pre-existing `test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `dotnet not found on PATH`. Same pre-existing host-equipment dependency documented in all 3 handoffs and in the prior cycle's WORKLOG. Reproduces identically on unmodified main `7a17f85`. Out of B2 cycle scope.
