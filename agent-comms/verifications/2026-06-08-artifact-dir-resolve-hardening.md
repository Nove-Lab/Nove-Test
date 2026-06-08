---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-08
slug: artifact-dir-resolve-hardening
related:
  - agent-comms/handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
---

# Verification — Run-team `artifact_dir.resolve()` preemptive hardening (B2-4)

## Merged commit + summary

- **Merged commit on main**: `6ebad33` (final B2 cycle tip — this slice merged last in the alphabetic sequence coverage → localization → run).
- **Source handoff consumed**: `agent-comms/handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md`.
- **One-line summary**: All 6 adapter entry points in `src/novetest/run/adapters/` now begin with `artifact_dir = artifact_dir.resolve()` as the first statement of the function body (after the docstring, before any path composition). Closes the 2026-05-16 long-standing TODO in `history/2026-05-16-phase0-release-and-phase2-entry.md` §60 which originally targeted only `pytest_adapter` (5 months before the other 5 adapters existed). Preemptive hardening: no production caller currently passes a relative `artifact_dir`, but the invariant "the adapter's first act after receiving `artifact_dir` is to absolutize it" is now uniform across the engine matrix.

## What changed (file-by-file)

| File | Insertion site | Lines |
|---|---|---|
| `src/novetest/run/adapters/pytest_adapter.py` | `run_pytest` line 69 | +10 (1 effective + 9 comment) |
| `src/novetest/run/adapters/jest_adapter.py` | `run_jest` line 79 | +7 (1 effective + 6 comment) |
| `src/novetest/run/adapters/junit_adapter.py` | `run_junit` line 136 | +7 (1 effective + 6 comment) |
| `src/novetest/run/adapters/gotest_adapter.py` | `run_gotest` line 84 | +5 (1 effective + 4 comment) |
| `src/novetest/run/adapters/cargo_adapter.py` | `run_cargo` line 159 | +5 (1 effective + 4 comment) |
| `src/novetest/run/adapters/dotnet_adapter.py` | `run_xunit` line 283 | +9 (1 effective + 8 comment) |

The pytest_adapter carries the full long-form rationale; the other five reference it succinctly. All 6 use the unconditional `.resolve()` form (idempotent on absolute paths, resolves relative paths against cwd, follows symlinks). Test files gained 2 unit tests each (12 total) under `tests/unit/run/adapters/test_*_adapter.py` pinning the dual invariant (relative resolves, absolute round-trips unchanged).

## What did NOT change (regression safety per brief §"Out of scope")

- No `workspace_path` / `fixture_dir` / other-arg hardening — explicitly excluded by brief.
- No integration tests added or modified — §2.5 game avoidance (the slice deliberately stays at unit-test level so the §2.5 file-glob heuristic does NOT fire).
- No `cli/output.py::EnvelopeWarning` shape changes (frozen 2026-06-07).
- No `run/types.py::AdapterWarning` shape changes (frozen 2026-06-06).
- No touches to `src/novetest/run/types.py`, `engine.py`, `normalizer.py`, `readiness.py`, `target_resolver.py`, `engine_selector.py` (Run-team-owned but NOT adapter-entry territory).
- No Coverage / Localization / Regression / Replay / Memory / Orchestration touches.
- No caller-side path-build changes (orchestration still constructs absolute paths under `.novetest/run/artifacts/run_<ulid>/`).

## Verification scenarios (target host = general)

§2.5 equip-and-exercise gate does NOT fire for this slice (no adapter integration test changes). General host is acceptable.

### Scenario A — 1-line audit of all 6 adapters (the cheapest evidence)

Confirm the invariant by grepping the merged main tip:

```bash
cd /home/yjshin/dev/aispace/Nove-Test
grep -n "artifact_dir = artifact_dir.resolve" src/novetest/run/adapters/*.py
```

Expected output (6 lines, one per adapter — line numbers exact):
```
src/novetest/run/adapters/cargo_adapter.py:159:    artifact_dir = artifact_dir.resolve()
src/novetest/run/adapters/dotnet_adapter.py:283:    artifact_dir = artifact_dir.resolve()
src/novetest/run/adapters/gotest_adapter.py:84:    artifact_dir = artifact_dir.resolve()
src/novetest/run/adapters/jest_adapter.py:79:    artifact_dir = artifact_dir.resolve()
src/novetest/run/adapters/junit_adapter.py:136:    artifact_dir = artifact_dir.resolve()
src/novetest/run/adapters/pytest_adapter.py:69:    artifact_dir = artifact_dir.resolve()
```

If any adapter is missing — regression.

### Scenario B — Targeted unit test matrix (12 new tests; load-bearing evidence)

```bash
uv run pytest -v \
  tests/unit/run/adapters/test_pytest_adapter.py::test_relative_artifact_dir_resolves_against_cwd \
  tests/unit/run/adapters/test_pytest_adapter.py::test_absolute_artifact_dir_unchanged_after_resolve \
  tests/unit/run/adapters/test_jest_adapter.py::test_relative_artifact_dir_resolves_against_cwd \
  tests/unit/run/adapters/test_jest_adapter.py::test_absolute_artifact_dir_unchanged_after_resolve \
  tests/unit/run/adapters/test_junit_adapter.py::TestArtifactDirResolveHardening \
  tests/unit/run/adapters/test_gotest_adapter.py::test_relative_artifact_dir_resolves_against_cwd \
  tests/unit/run/adapters/test_gotest_adapter.py::test_absolute_artifact_dir_unchanged_after_resolve \
  tests/unit/run/adapters/test_cargo_adapter.py::test_relative_artifact_dir_resolves_against_cwd \
  tests/unit/run/adapters/test_cargo_adapter.py::test_absolute_artifact_dir_unchanged_after_resolve \
  tests/unit/run/adapters/test_dotnet_adapter.py::TestArtifactDirResolveHardening
```

Expected: 12 passed in <1s (subprocess-stubbed; no native toolchain required). Each pair pins:
- `test_relative_artifact_dir_resolves_against_cwd`: a relative `Path("rel-art")` input with `monkeypatch.chdir(tmp_path)` produces `result.artifact_paths` values rooted under `(tmp_path / "rel-art").resolve() / "native"`.
- `test_absolute_artifact_dir_unchanged_after_resolve`: an absolute `(tmp_path / "abs-art").resolve()` input round-trips unchanged (the existing production caller shape).

The junit pair uses the "no build tool found" early-raise path (no subprocess stub needed). The dotnet pair lives under `TestArtifactDirResolveHardening` class. Both proof shapes are equally valid.

### Scenario C — No-regression smoke against any fixture project

Because the change is preemptive (no production caller currently passes a relative `artifact_dir`), there is no user-visible behavior change to probe at the envelope level. Run a normal `novetest run` against any fixture and confirm artifacts still land where they always did:

```bash
cd /tmp && rm -rf novetest-art-smoke-$$ && mkdir novetest-art-smoke-$$ && cd novetest-art-smoke-$$
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/basic_workspace .
cd basic_workspace
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run | python3 -c "import json,sys; r=json.load(sys.stdin); ap=r['data']['run_outcome']['artifact_paths']; print('artifact_paths keys:', list(ap.keys())); print('all absolute:', all(p.startswith('/') for p in ap.values())); print('sample:', list(ap.values())[:2])"
```

Expected: `all absolute: True`. The resolve is a no-op on the absolute path orchestration constructs (idempotent), so this is a no-regression check.

### Scenario D — Inverse-verification by constructing a relative `artifact_dir` directly

Per handoff §"Manual Test verification suggestions": pre-this-slice, a relative `artifact_dir` would produce `result.artifact_paths` values that are either also relative OR rooted under the wrong cwd. Post-this-slice, every value is absolute and rooted under the cwd-anchored resolved root. This is verified at unit-test level (Scenario B above) — production CLI callers never pass relative paths so there's no direct CLI surface.

## Critical edge cases worth probing

1. **Symlink-follow side effect on macOS / WSL2** (handoff §"Implementation Choices"): `tmp_path` is sometimes a symlink target (`/var/folders/.../` → `/private/var/folders/.../` on macOS; less common on Linux but possible). Every test uses `(tmp_path / "abs-art").resolve()` for BOTH the input AND the expected assertion target so the symlink-follow side effect is pre-applied. If Manual Test re-runs the unit tests on a host with symlinked `tmp_path`, the tests still pass because the resolve is applied symmetrically — but be aware that the canonical artifact path may differ from the `tmp_path / "abs-art"` literal (it's the resolved form).
2. **The unconditional `.resolve()` over `if not is_absolute()` guard**: handoff §Gotcha #1 documents the team-judgment choice. Both forms are functionally equivalent under current pathlib semantics. The unconditional form is one line shorter, has one fewer branch to test, and produces identical behavior. Side effect: symlinks are followed even on already-absolute inputs (we explicitly want this so the path that flows through the adapter is the same shape regardless of how the caller built it).
3. **The dotnet adapter's resolve runs BEFORE `workspace = test_target.workspace_path`** (handoff §"Implementation Choices"): the existing structure had the workspace assignment as the first body line. Both placements are functionally equivalent (`test_target.workspace_path` is already absolute from the resolver) but uniform placement keeps the invariant memorizable.
4. **Long-standing TODO closed**: this slice closes the 2026-05-16 origin TODO (5 months after surfacing). The handoff and WORKLOG cross-reference `history/2026-05-16-phase0-release-and-phase2-entry.md` §60 for forensic continuity.

## Conflict resolution during merge

- **WORKLOG.md conflict during the Run team rebase onto post-localization main** (expected — coverage + localization + run all add 2026-06-08 top entries). Resolved by placing the Run team's entry on top, with `---` dividers separating it from localization + coverage (which were already separated by `---` from the prior localization rebase). All 5 prior 2026-06-08 entries (run, localization, coverage, regression-fixed-tests-spec, defect7) are preserved verbatim, in newest-merged-first order.
- No source-code conflicts (3 file footprints fully disjoint as expected).

## Test gate (post-merge, full main tip `6ebad33`)

```
$ uv run mypy --strict src/novetest
Success: no issues found in 92 source files

$ uv run pytest -q tests/unit tests/integration
1209 passed, 23 skipped, 1 failed in 33.26s
```

Baseline (pre-cycle, main `7a17f85`): 1191 passed. Net delta: +18 (= 1 coverage + 5-6 localization + 12 run, within expected range).

The 1 failure is the pre-existing `test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `dotnet not found on PATH`. Same pre-existing host-equipment dependency documented in all 3 handoffs and in the prior cycle's WORKLOG. Reproduces identically on unmodified main `7a17f85`. Out of B2 cycle scope; PM may file a tiny follow-up for Run team to add a skip-guard parallel to the 26 cleanly-skipped toolchain-gated tests (Coverage handoff §Gotcha 1 flagged this; this slice deliberately did NOT touch that file because the surgical-changes posture is "don't expand scope mid-merge").
