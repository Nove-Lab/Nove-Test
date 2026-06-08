---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-08
slug: outside-workspace-path-harmonization
related:
  - agent-comms/handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
---

# Verification — Coverage outside-workspace path harmonization (B2-3)

## Merged commit + summary

- **Merged commit on main**: `6ebad33` (final cycle tip — sequential FF: coverage → localization → run); the coverage slice itself landed at intermediate tip `134918a`. The post-cycle main tip is what Manual Test exercises.
- **Source handoff consumed**: `agent-comms/handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`.
- **One-line summary**: `src/novetest/coverage/lcov_parser.py::_workspace_relative` now normalizes outside-workspace LCOV `SF:` paths to a `../`-prefixed POSIX relpath via `os.path.relpath` (mirroring istanbul / cobertura). `metadata['lcov_warnings']` is retained as a **forensic-only channel** and now carries BOTH the original absolute string AND the normalized relpath. No `schema_version` bump; on-disk shape unchanged.
- **5-parser asymmetry matrix (post-slice)**: all five parsers (coverage.py, istanbul, lcov, jacoco, cobertura) now uphold the universal contract `not Path(file_path).is_absolute()` across every `CoverageFactSet.files[*].file_path` regardless of native input shape.

## What did NOT change (regression safety)

- `decisions/2026-05-15-coverage-facts-json-layout.md` constraint #6 strengthened in-place + new "Amendment 2026-06-08" block — but no `schema_version` bump (on-disk layout unchanged; only the value of `file_path` shifts from absolute to relpath for the previously-undefined outside-workspace case).
- istanbul / cobertura / coverage.py / jacoco parser code untouched.
- The empty-list-noise suppression for `lcov_warnings` still holds: when no path is outside the workspace, the `lcov_warnings` key is omitted entirely (no `metadata['lcov_warnings'] == []`).

## Verification scenarios (target host = general)

§2.5 equip-and-exercise gate does NOT fire for this slice (no native adapter src + integration test edits combined). General host is acceptable.

All paths reference fields under the **`data.coverage_outcome`** block of the CLI envelope (verified by reading `src/novetest/cli/app.py::_coverage_outcome_payload` + `src/novetest/models/coverage_fact_set.py::CoverageFactSet.to_dict()`):

```
data.coverage_outcome.kind                          # "fact-set" | "unavailable"
data.coverage_outcome.files[*].file_path            # workspace-relative or "../"-prefixed POSIX relpath
data.coverage_outcome.metadata                      # dict; may contain "lcov_warnings" on lcov fact sets only
data.coverage_outcome.metadata.lcov_warnings        # list[str], present iff any outside-workspace path was encountered
```

### Scenario A — Universal contract: no `file_path` is ever absolute (load-bearing)

Run the **existing** 3 coverage E2E integration tests; each carries the universal `not Path(file_path).is_absolute()` assertion that previously held by per-fixture luck and now holds by contract:

```bash
cd /home/yjshin/dev/aispace/Nove-Test
uv run pytest -v \
  tests/integration/coverage/test_cargo_lcov_e2e.py \
  tests/integration/coverage/test_jest_coverage.py \
  tests/integration/coverage/test_dotnet_cobertura_derive.py
```

Expected: each test passes if its toolchain is equipped, else cleanly skips. The `assert not Path(f.file_path).is_absolute()` is the wire-level evidence. Cargo / jest / dotnet host equipment matters here ONLY for whether the test runs vs skips — neither outcome implies a regression.

### Scenario B — Outside-workspace forensic channel (focused unit test)

```bash
uv run pytest -v \
  tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning \
  tests/unit/coverage/test_lcov_parser.py::test_inside_only_paths_omit_lcov_warnings_metadata
```

Expected: both green. The first pins (a) the outside-workspace `file_path` is `../`-prefixed AND not absolute, (b) `metadata['lcov_warnings']` exists with one entry, (c) the warning entry contains BOTH the original absolute SF AND the normalized relpath AND the `workspace_root` literal. The second pins that inside-only fact sets continue to omit `lcov_warnings` entirely (no empty-list noise).

### Scenario C — Decision doc reads cleanly

Read `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` end-to-end. Confirm:

1. Constraint #6 carries the binding rule: "Outside-workspace files (cargo build-script generated code, vendored paths, etc.) MUST be expressed as a `../`-prefixed POSIX relpath via `os.path.relpath` against `workspace_root`."
2. The new "Amendment 2026-06-08" block sits before "Effective date" and explains the per-parser asymmetry that triggered the slice.
3. No `schema_version` change appears anywhere in the diff (on-disk layout invariant).

### Scenario D — Manual cargo smoke (skip if cargo not equipped)

If cargo + `cargo-llvm-cov` are equipped:

```bash
cd /tmp && rm -rf novetest-cov-smoke-$$ && mkdir novetest-cov-smoke-$$ && cd novetest-cov-smoke-$$
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/cargo-test-basic .
cd cargo-test-basic
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run --coverage 2>/dev/null | tee /tmp/cargo-cov-envelope.json
# Inspect:
python3 -c "import json,sys; e=json.load(open('/tmp/cargo-cov-envelope.json')); files=e['data']['coverage_outcome']['files']; print('files:', len(files)); abs_paths=[f['file_path'] for f in files if f['file_path'].startswith('/')]; print('absolute count (must be 0):', len(abs_paths)); print('sample paths:', [f['file_path'] for f in files[:3]])"
```

Expected: `absolute count (must be 0): 0`. Any non-zero count is a regression. Sample paths should look workspace-relative (e.g. `src/lib.rs`) or `../`-prefixed if cargo emitted any build-script vendored path.

## Critical edge cases worth probing

1. **The forensic channel is single-source-of-truth for native debug**. If Manual Test wants to confirm the original absolute `SF:` value for a cargo build-script artifact, the only place to read it post-slice is `data.coverage_outcome.metadata.lcov_warnings[i]` — the warning string contains `<abs_path> -> <relpath>` so both forms are recoverable. `file_path` no longer carries the absolute form anywhere.
2. **No `schema_version` bump means downstream readers don't need re-loading**. A `CoverageFactSet` persisted before this slice is still consumed identically; the only difference is what `file_path` looks like for the previously-undefined outside-workspace case.
3. **istanbul + cobertura unchanged**. If Manual Test runs a jest E2E or a .NET Cobertura E2E and sees a `../`-prefixed `file_path`, that's the pre-existing istanbul / cobertura behavior — not new from this slice.

## Conflict resolution during merge

- **WORKLOG.md conflict during the localization rebase** (expected — all 3 parallel slices add 2026-06-08 top entries). Coverage's entry sat at HEAD when localization rebased; both preserved with `---` divider between them. Same pattern repeated when run rebased onto post-localization main. All 4 prior 2026-06-08 entries (coverage, localization, regression-fixed-tests-spec, defect7) plus the new run entry are preserved verbatim in the file's top section, separated by `---` dividers between the 3 newly-merged entries.
- No source-code conflicts (file-footprints fully disjoint per brief).

## Test gate (post-merge, full main tip `6ebad33`)

```
$ uv run mypy --strict src/novetest
Success: no issues found in 92 source files

$ uv run pytest -q tests/unit tests/integration
1209 passed, 23 skipped, 1 failed in 33.26s
```

The 1 failure is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `AdapterInvocationError: dotnet not found on PATH`. **Pre-existing host-equipment dependency**, documented identically in all 3 handoffs and in the prior cycle's WORKLOG. Reproduces on unmodified main `7a17f85` without any of these slices. Out of B2 cycle scope; PM may file a tiny follow-up for Run team to add a skip-guard parallel to the 26 cleanly-skipped toolchain-gated tests (flagged in coverage's handoff §Gotcha 1).
