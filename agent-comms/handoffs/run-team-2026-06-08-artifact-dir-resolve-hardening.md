---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-08
slug: artifact-dir-resolve-hardening
related:
  - agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
  - agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
---

# Handoff — `artifact_dir.resolve()` preemptive hardening (B2-4, 3/3 of B2 UX parallel)

## Worktree / branch / base

| Field | Value |
|---|---|
| Worktree | `/home/yjshin/dev/aispace/novetest-artifact-resolve` |
| Branch | `run-team/artifact-dir-resolve-hardening` |
| Base | `7a17f85` (`main` tip; "comms: brief B2 UX-normalization 3-team parallel cycle") |
| Tip | committed atomically with this handoff |
| Working tree | clean (modulo the staged slice diff) |

## Files written / modified

### Source modifications (6 files, all under `src/novetest/run/adapters/`)

| File | Insertion site | Diff shape |
|---|---|---|
| `pytest_adapter.py` | `run_pytest` (after docstring, before `native_dir = artifact_dir / "native"`) | +10 LOC (1 effective + 9 rationale comment) |
| `jest_adapter.py` | `run_jest` | +7 LOC (1 effective + 6 rationale comment) |
| `junit_adapter.py` | `run_junit` | +7 LOC (1 effective + 6 rationale comment) |
| `gotest_adapter.py` | `run_gotest` | +5 LOC (1 effective + 4 rationale comment) |
| `cargo_adapter.py` | `run_cargo` | +5 LOC (1 effective + 4 rationale comment) |
| `dotnet_adapter.py` | `run_xunit` (before `workspace = test_target.workspace_path`) | +9 LOC (1 effective + 8 rationale comment) |

Each source edit consists of one effective statement — `artifact_dir = artifact_dir.resolve()` — preceded by a comment block referencing the 2026-05-16 origin TODO (`history/2026-05-16-phase0-release-and-phase2-entry.md` §60). The pytest_adapter carries the full long-form rationale; the other five reference it succinctly. Total src delta: 43 LOC across 6 files.

### Test modifications (6 files, all under `tests/unit/run/adapters/`)

| File | New tests | Approach |
|---|---|---|
| `test_pytest_adapter.py` | `test_relative_artifact_dir_resolves_against_cwd` + `test_absolute_artifact_dir_unchanged_after_resolve` | real pytest subprocess against `basic_workspace` (pytest is always present in dev venv) |
| `test_jest_adapter.py` | same two | reuses existing `_make_stub_subprocess` (`returncode=0`, `write_report=True`) + autouse `_stub_npx_on_path` |
| `test_junit_adapter.py` | `TestArtifactDirResolveHardening` class with same two methods | "no build tool found" early-raise: catches `AdapterInvocationError(kind="build-tool-undetermined")` + asserts on-disk `native/` existence at resolved path (no subprocess stub needed) |
| `test_gotest_adapter.py` | same two | reuses existing `_make_stub_subprocess(events=_passing_events())` + autouse `_stub_go_on_path` |
| `test_cargo_adapter.py` | same two | reuses existing `_make_stub_subprocess(events=_passing_events())` + autouse `_stub_cargo_on_path` |
| `test_dotnet_adapter.py` | `TestArtifactDirResolveHardening` class with same two methods | reuses existing `_make_run_subprocess_stub()` + autouse `_stub_dotnet_on_path` |

Total test delta: 403 LOC across 6 files (12 new tests).

### Coordination files (2 files)

| File | Change |
|---|---|
| `WORKLOG.md` | top entry added per charter format |
| `agent-comms/handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md` | this file |
| `agent-comms/INDEX.md` | will be regenerated atomically (`tools/regen_comms_index.py`) |

### Total diff

`git diff --stat 7a17f85..HEAD` → **13 files / +456 LOC** (6 src + 6 unit-test files + WORKLOG.md; +0 deletions).

## Verification

All commands run from `/home/yjshin/dev/aispace/novetest-artifact-resolve` (worktree root).

### `uv run mypy --strict src/novetest`

```
Success: no issues found in 92 source files
```

Unchanged source-file count (slice adds lines to existing files; no new modules).

### `uv run pytest -q tests/unit`

```
1106 passed in 2.75s
```

Baseline (pre-slice) was 1094 (1106 − 12); the +12 = exactly the new resolve tests.

### Targeted run of the 12 new tests

```
$ uv run pytest -v \
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

12 passed in 0.37s
```

### Integration tests

**Deliberately NOT run** per task §"§2.5 equip-and-exercise 게이트":

> 본 슬라이스는 어댑터 **src + 단위 테스트만** 만지고 어댑터 **통합 테스트는 손대지 않음** → §2.5 file-glob 휴리스틱 발동 안 함. 일반 host에서 진행 가능.

The §2.5 game avoidance is the whole point of the brief's "통합 테스트는 새로 만들지 않음" instruction. Integration tests already use absolute paths via `tmp_path` so they're regression-pinned at the existing surface; new resolve tests live at the unit boundary only. General (non-equipped) host is acceptable for this cycle.

## Implementation Choices

### `.resolve()` vs `if not is_absolute(): .resolve()` (brief §"`.resolve()` vs `.absolute()` 선택")

**Chose unconditional `.resolve()`** (PM-recommended option) for all six adapters.

Rationale documented in brief §"Idempotency 보장" — `.resolve()` is idempotent on absolute paths (returns the same path with symlinks followed) and resolves relative paths against cwd. The unconditional form:

- is one line shorter than the guarded form (1 line vs 2 lines + indent);
- has one fewer branch surface for tests to cover (the `is_absolute()` true/false split);
- produces identical behavior on relative paths;
- on absolute paths, includes the symlink-follow side effect, which we explicitly DO want — it means the path that flows through the adapter is the same shape whether the caller built it absolute or relative. The invariant "the artifact path that reaches the normalizer is canonicalized" is easier to reason about when there is no branching.

### `.resolve()` vs `.absolute()` (brief §"`.resolve()` vs `.absolute()` 선택")

**Chose `.resolve()`** (PM-recommended option) for stronger guarantees: `.resolve()` follows symlinks AND resolves `..` segments. `.absolute()` only prepends cwd. On the typical Linux/macOS dev host, the difference matters when:

- The caller passes `Path("foo/../bar")` — `.resolve()` produces `bar` absolutized; `.absolute()` produces `cwd/foo/../bar` literally.
- The caller works from a symlinked directory — `.resolve()` follows the symlink; `.absolute()` does not.

Test-suite side effect: `tmp_path` is sometimes a symlink target on macOS (`/var/folders/.../` → `/private/var/folders/.../`). Every test pair uses `(tmp_path / "abs-art").resolve()` for both the input AND the expected assertion target so the symlink-follow side effect is pre-applied. Without this care, `result.artifact_paths[k]` would land under the resolved (private) path while `tmp_path / "abs-art"` would compare under the unresolved (visible) path, and `expected_root in path.parents` would fail on macOS only.

### Placement (before `workspace = test_target.workspace_path` in dotnet)

In `run_xunit`, the existing structure had `workspace = test_target.workspace_path` as the first body line followed by `native_dir = artifact_dir / "native"`. Both placement orders (workspace-first or resolve-first) are functionally equivalent — `test_target.workspace_path` is already absolute coming from the resolver — but placing `artifact_dir = artifact_dir.resolve()` FIRST keeps the invariant uniform across all six entry points:

> "The adapter's first act after receiving `artifact_dir` is to absolutize it."

A future reader doesn't need to memorize per-adapter exceptions. Same principle applied across the 6 files for cohesion.

## DoD bullets believed closed

All 7 bullets in brief §"Definition of done":

1. **6개 어댑터 entry point 모두 `artifact_dir.resolve()` (또는 동등) 적용** — ✓ all 6 at function-body top, after docstring, before any path composition.
2. **각 어댑터당 단위 테스트 1-2개: relative path resilience + absolute path unchanged** — ✓ 12 tests (2 per adapter) across 6 test files.
3. **`uv run mypy --strict src/novetest` 클린** — ✓ Success: no issues found in 92 source files.
4. **`uv run pytest -q tests/unit` 그린 (통합 테스트 추가 안 함, 기존 통합 테스트는 §2.5 게이트 회피 위해 변경 없음)** — ✓ 1106 passed in 2.75s; integration tests untouched and not run on this general host.
5. **WORKLOG.md 엔트리 (charter 양식)** — ✓ top entry added per charter "Entry format" (Landed / Verified / Left open / Gotcha / Next).
6. **Handoff `agent-comms/handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md` + DoD bullets believed closed 리스트** — ✓ this file.
7. **`python3 tools/regen_comms_index.py`** — will run atomically before commit.

## Cross-team scope footprint

Run-team-only. No touches to:

- `src/novetest/models/` (Memory team)
- `src/novetest/coverage/`, `localization/`, `regression/`, `replay/` (other teams)
- `src/novetest/orchestration/`, `cli/` (Orchestration team)
- `src/novetest/run/types.py`, `engine.py`, `normalizer.py`, `readiness.py`, `target_resolver.py`, `engine_selector.py` (Run-team-owned but NOT adapter-entry territory; brief explicitly scoped to "각 어댑터 entry point" only)
- `src/novetest/run/adapters/*` other than the entry function (helpers untouched)
- `tests/integration/run/` (§2.5 game avoidance)
- `tests/fixtures/projects/` (no fixture mutation needed)
- `cli/output.py::EnvelopeWarning` (frozen 2026-06-07)
- `run/types.py::AdapterWarning` (frozen 2026-06-06)
- v1 metadata bridge keys (post-MVP cleanup)

Disjoint from B2 parallel cycle peers:

- **Coverage team (B2-2)**: `src/novetest/coverage/` + coverage decision amend
- **Localization team (B2-3)**: `src/novetest/localization/` + localization spec doc

Zero merge conflict expected with either peer. Per brief §"Main Branch merge 순서" the alphabetic FF-merge order is **coverage → localization → run** so this slice merges LAST in the B2 parallel cycle.

## Pre-merge checklist (for Main Branch team)

1. FF-merge `run-team/artifact-dir-resolve-hardening` onto `main`. Conflicts expected: none against `7a17f85` baseline.
2. Run `uv run mypy --strict src/novetest` → expect `Success: no issues found in 92 source files`.
3. Run `uv run pytest -q tests/unit` → expect `1106 passed`.
4. (Optional but recommended) Run `uv run pytest -q tests/unit/run/adapters` to focus on the touched modules.
5. Write verification request to `agent-comms/verifications/` for Manual Test team.

§2.5 is NOT in force for this slice (no adapter integration test changes). General host acceptable for Main Branch's pre-merge gate too.

## Manual Test verification suggestions

Because the change is preemptive (no production caller currently passes a relative `artifact_dir`), there is no user-visible behavior change to probe via the CLI. Manual Test can:

1. **Confirm the invariant** by reading the 6 adapter entry points and verifying each opens with `artifact_dir = artifact_dir.resolve()` (1-line audit per file).
2. **Confirm no regression** by running `novetest run` against any fixture project as usual — artifacts should land under `.novetest/run/artifacts/run_<ulid>/` as before. The resolve is a no-op on the absolute path that orchestration constructs.
3. **Confirm the test surface** by re-running `uv run pytest -q tests/unit/run/adapters/` and inspecting the 12 new test names (pattern: `test_*_artifact_dir_*` or `TestArtifactDirResolveHardening`).

No Manual-Test-specific findings risk; this slice is mechanical hardening with comprehensive unit-test coverage.

## Surprises

None to report — the slice landed exactly to brief estimate. Wall time: ~1 hour (matched brief's "1 시간" estimate). LOC count exceeded the brief's guidance (43 src + 403 tests vs ~6 src + ~30-60 tests) but only because I chose to document the rationale in comments rather than only in the handoff — the surgical-changes-with-context trade-off documented in WORKLOG §Gotcha.

## Open items

None. The 2026-05-16 long-standing TODO closes with this slice.
