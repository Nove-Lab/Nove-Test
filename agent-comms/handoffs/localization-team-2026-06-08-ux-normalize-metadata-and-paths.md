---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-08
slug: ux-normalize-metadata-and-paths
related:
  - agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
  - agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
---

# Handoff — Localization UX normalization (B2-1 metadata + B2-2 paths)

## Worktree

- Branch: `localization-team/ux-normalize-metadata-and-paths`
- Path: `/home/yjshin/dev/aispace/novetest-localization-ux-normalize`
- Base: `7a17f85` (main tip at cycle start)

## Files written / modified

### Source (2 files)

- `src/novetest/localization/derive.py` — `_derive_per_test` now passes `metadata={"changed_files_count": None, "regression_reweighted": None}` to the `LocalizationFinding(...)` constructor (B2-1). Comment block explains the `None`-vs-`0/False` discriminator choice. **No other modes touched.**
- `src/novetest/localization/failure_proximity.py` — (1) new module-level helper `_normalize_to_workspace_relative(file_path: str, workspace_root: Path) -> str` at the bottom of the internals section. (2) Inside `derive_failure_proximity`'s outer loop: `workspace_root = store.path.parent` hoisted just before the per-test loop; inside the inner parse-results loop the parsed `file_path` is fed through the helper as `relative_file` BEFORE landing in the aggregation dicts. (3) `from pathlib import Path` added to imports. **No model schema change. No public API change.**

### Spec / design doc (1 file)

- `design/interace-contract/localization.md` — new `## Result shape — mode-invariant` section appended at the end. Carries (a) a 3-column key table for the `metadata` base-key contract, (b) a `code_location.file` representation paragraph stating "workspace-relative across all three modes", (c) an explicit edge-case paragraph for absolute-out-of-workspace paths (kept absolute as a "not your code" cue).

### Tests (5 files)

- `tests/unit/localization/test_derive.py` — 2 new tests at the bottom under a B2-1 §"metadata shape normalization" header:
  - `test_per_test_metadata_has_mode_invariant_keys_with_none_values` — in-memory shape pin.
  - `test_per_test_metadata_survives_persistence_roundtrip` — cache-reader pin (catches a future `dict[str, Any]` JSON-serialization regression on `None` values).
- `tests/unit/localization/test_derive_failure_proximity.py` — 4 new tests under a B2-2 §"file-path absoluteness normalization" header:
  - `test_absolute_workspace_internal_path_normalized_to_relative` — production-shape input (absolute under workspace) → relative output.
  - `test_absolute_path_outside_workspace_kept_absolute` — defensive edge case (e.g. stdlib frame).
  - `test_relative_path_passes_through_unchanged` — idempotence pin.
  - `test_absolute_and_relative_for_same_file_collapse_to_relative` — load-bearing aggregation-before-normalization invariant (`score_raw == 2.0` for 2-test combined entry).
- `tests/integration/localization/test_failure_proximity_e2e.py` — tightened the existing `test_failure_proximity_ranks_buggy_file_top`: (a) entry-wide `not Path(entry.code_location.file).is_absolute()` loop; (b) exact-string assertion `sut_entry.code_location.file == "localization_no_coverage/statistics.py"` replacing the previous loose substring check; (c) B2-1 metadata-keys-present + type assertions (`int` / `bool` for failure_proximity).
- `tests/integration/localization/test_localization_branch_basic.py` — B2-1 assertion block added: `metadata["changed_files_count"] is None` AND `metadata["regression_reweighted"] is None` (per-test mode side of the 3-mode matrix).
- `tests/integration/localization/test_aggregate_mode_e2e.py` — B2-1 assertion block added: `metadata["changed_files_count"]` is `int` AND `metadata["regression_reweighted"]` is `bool` (aggregate mode side of the 3-mode matrix).

### Coordination

- `WORKLOG.md` — new top entry (charter format: Landed / Verified / Left open / Gotcha / Next).
- `agent-comms/handoffs/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md` — this file.

## Verification result

- `uv run mypy --strict src/novetest` → **Success: no issues found in 92 source files**.
- `uv run pytest -q tests/unit tests/integration` → **1194 passed + 26 skipped + 1 failed in 31.55s**. The 1 failure is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `AdapterInvocationError: dotnet not found on PATH`. **Pre-existing host-equipment dependency**; brief §"§2.5 equip-and-exercise 게이트" explicitly says §2.5 gate does NOT apply to this slice (no native adapter touches → general non-equipped host is acceptable). Same pre-existing failure documented in the prior cycle's WORKLOG (defect7 entry, 2026-06-08).
- Localization-scoped focused suite `uv run pytest -q tests/unit/localization tests/integration/localization` → **163 passed + 2 skipped + 0 failed in 2.71s**.

### 3-mode matrix evidence

| Mode | E2E test | `code_location.file` shape | `metadata.changed_files_count` | `metadata.regression_reweighted` |
|---|---|---|---|---|
| `sbfl_per_test` | `test_localization_branch_basic.py` | repo-relative (always was) | `None` | `None` |
| `sbfl_aggregate` | `test_aggregate_mode_e2e.py` | repo-relative (always was, via `CoverageFactSet.files[*].file_path`) | `int` (≥ 0) | `bool` |
| `failure_proximity` | `test_failure_proximity_e2e.py` | repo-relative (this slice's fix; pinned exact-string `localization_no_coverage/statistics.py`) | `int` (≥ 0) | `bool` |

## Worklog entry text (already added)

See the new top entry in `WORKLOG.md` — section `## 2026-06-08 — B2 UX-normalization / localization-metadata-and-paths`.

## DoD bullets — believed closed

All 10 bullets in `agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md` §"Definition of done":

1. ✓ 3 mode 모두 `metadata` 키 셋 동일 (`changed_files_count` + `regression_reweighted` + default 값) — `_derive_per_test` 추가 + 다른 두 mode는 이미 그대로 → 3-mode matrix 단위 + 통합 테스트로 pin.
2. ✓ `failure_proximity` mode의 file_path가 repo-relative로 정규화 — `_normalize_to_workspace_relative` 헬퍼 + 파서 결과 루프 내부 적용 + entry-wide `not is_absolute()` 통합 어설션.
3. ✓ 명세 doc 갱신 (`design/interace-contract/localization.md` §"Result shape — mode-invariant").
4. ✓ 통합 테스트 매트릭스: 3 mode × 정규화된 envelope shape (3 파일에 분산: branch / aggregate / failure_proximity E2E 각각).
5. ✓ 단위 테스트: 6개 (per-test metadata 2개 + failure_proximity path 4개).
6. ✓ `uv run mypy --strict src/novetest` 클린 (92 src files).
7. ✓ `uv run pytest -q tests/unit tests/integration` 그린 (1194 passed + 26 skipped; 1 fail = dotnet host-equip, 무관 pre-existing).
8. ✓ WORKLOG.md 엔트리 추가 (charter 양식).
9. ✓ Handoff (this file).
10. ⏳ `python3 tools/regen_comms_index.py` — will run after commit.

## Open items / PM ratification requests

### Brief 사실 오류 1건 + PM 디스포지션 요청

**Brief §"Implementation guidance" §2** said: "workspace root는 이미 Run Record에 저장됨 (`workspace_path`)". **이 정보는 부정확함.** `RunRecord` 모델에 `workspace_path` 필드는 **없다** (확인: `grep -rn workspace_path src/novetest/models/run_record.py` → zero hits).

대신 코드에서 통용되는 workspace root 표현은 `store.path.parent` (= `<workspace>/.novetest/`의 부모). 이미 `derive.py::_resolve_repo_path`가 사용하는 패턴이고 이번 슬라이스의 B2-2 헬퍼도 동일 표현을 사용함. 스키마 변경 없이 닫음.

**PM 결정 필요**: 향후 cross-machine fact-set transport / replay 시 `RunRecord.workspace_path`를 top-level 필드로 가지는 게 옳다면, Memory team 슬라이스가 별도로 필요함. 이번 슬라이스는 이를 추가하지 않았고 (forbidden territory — models 변경은 Memory team).

### 부수 영향 없음

다른 mode (sbfl_per_test, sbfl_aggregate)의 path 처리는 손대지 않았고, 그 모드들의 기존 통합 어설션 (`.endswith(...)` 형식)도 그대로 통과함. failure_proximity의 기존 happy-path 단위 테스트 (입력이 이미 relative 형식) 도 통과 — 헬퍼는 relative 입력에 idempotent.

### Edge case: 절대 경로지만 workspace 외부

`/usr/lib/python/.../stdlib.py` 같은 stdlib frame이 pytest traceback에 섞여있을 때, 헬퍼는 `Path.relative_to`가 던지는 `ValueError`를 잡고 입력을 절대 형식 그대로 반환함. 이를 "드롭" 또는 "warning" 으로 처리하지 **않음** — brief가 "정규화"만 명시했고 "필터링"은 명시 안 함. 절대 경로 형식 자체가 "내 코드 아님" 디스코버리 단서 역할을 함. Defect-3 cargo stdlib-pollution 해결의 방어 자세와 일관됨.

## Pre-merge checklist (for Main Branch team)

1. `git worktree list` → confirm worktree at `/home/yjshin/dev/aispace/novetest-localization-ux-normalize`.
2. `git log --oneline localization-team/ux-normalize-metadata-and-paths ^main` → 2 commits expected (src+tests + handoff).
3. FF-merge order per brief §"Main Branch merge 순서": **coverage → localization → run**.
4. Post-merge: full `uv run pytest -q tests/unit tests/integration` rerun on the merged main tip. Expect 1194 + the deltas from coverage + run slices (sequential merges); pre-existing dotnet host-equip failure persists (unrelated).
5. Verification doc for Manual Test: probe `novetest localization <run_id>` on a no-coverage fixture; expected envelope keys:
   - `data.localization_finding.entries[*].code_location.file` is workspace-relative (no leading `/`).
   - `data.localization_finding.metadata.changed_files_count` is `int` (failure_proximity) or `null` (sbfl_per_test).
   - `data.localization_finding.metadata.regression_reweighted` is `bool` (failure_proximity) or `null` (sbfl_per_test).

## Cross-team scope footprint

Per brief §"파일 ownership — Zero 충돌 보장" + actual diff:

- Localization-only territory: `src/novetest/localization/derive.py`, `src/novetest/localization/failure_proximity.py`, `design/interace-contract/localization.md`, `tests/unit/localization/**`, `tests/integration/localization/**`.
- Coordination overlap: `WORKLOG.md` (every slice appends a top entry; all 3 parallel slices will touch this — standard top-entry conflict resolution at merge time, no semantic conflict).
- Zero touches to: Coverage, Run, Regression, Replay, Memory, Orchestration, CLI, models. The two B2 parallel-cycle siblings (Coverage outside-workspace + Run artifact_dir.resolve) have disjoint file footprints.
