---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-08
slug: ux-normalize-metadata-and-paths
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md
---

# Task — Localization UX normalization: metadata shape + file-path absoluteness (B2-1 + B2-2)

## Mission

Localization 결과 envelope에 존재하는 두 가지 mode-별 비대칭을 정리해
사용자/AI consumer가 단일 shape로 결과를 소비할 수 있게 만듦.
B2-1 = metadata 키 셋 정규화, B2-2 = file-path 표현 정규화. 같은
디렉토리 (`localization/`) 만져서 합본 슬라이스.

## Background — self-contained

Phase 4 Localization은 3 mode를 가짐: `sbfl_per_test`, `sbfl_aggregate`,
`failure_proximity`.

`agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
§196에서 명시된 두 비대칭:

> "**UX normalizations** (low-priority polish, optional pre-MVP):
>  - `metadata` shape asymmetry across modes (per-test `{}` vs
>    aggregate/failure_proximity `{changed_files_count,
>    regression_reweighted}`)
>  - File-path absoluteness asymmetry (`failure_proximity` emits
>    absolute paths; others emit repo-relative)"

### 비대칭 1 — Localization 결과의 `metadata` 키 셋

| mode | metadata 키 셋 |
|---|---|
| `sbfl_per_test` | `{}` (empty) |
| `sbfl_aggregate` | `{changed_files_count, regression_reweighted}` |
| `failure_proximity` | `{changed_files_count, regression_reweighted}` |

### 비대칭 2 — Code location의 file-path 표현

| mode | file_path 표현 |
|---|---|
| `sbfl_per_test` | repo-relative |
| `sbfl_aggregate` | repo-relative |
| `failure_proximity` | **absolute** |

같은 envelope 내에서 mode 따라 paths 표현이 다름. AI consumer가 매번
mode 확인 후 path 처리 분기 필요.

## PM 권장 방향

### B2-1 metadata shape — 옵션 (a) 키 셋 통일

| 옵션 | 내용 | 평가 |
|---|---|---|
| **(a)** | 모든 mode가 동일 키 셋 `{changed_files_count, regression_reweighted}`. per-test 모드에서 의미 없으면 `None` 또는 default (`0`/`False`). | **PM 추천** — 사용자 첫인상 "어떤 mode 골라도 envelope shape 동일" |
| (b) | mode별 metadata 키 셋을 명세 doc에 명시. 현재 동작 그대로지만 명세 강화만 함. | 명세 작업으로 cycle 가치 절약 가능. 비대칭 자체는 그대로 |
| (c) | metadata 키 자체를 별도 discriminator 필드로 옮김 | 큰 schema 변경 |

PM 추천 = **(a)**. 이유:
- envelope freeze v2 amendment 비용이 적절함 (1-2 줄)
- 사용자/AI consumer가 단일 mental model로 envelope 소비
- per-test mode에서 default 값은 의미 자체가 NULL/0 → 사용자 혼동 없음

### B2-2 file-path absoluteness — 옵션 (a) repo-relative 통일

| 옵션 | 내용 | 평가 |
|---|---|---|
| **(a)** | `failure_proximity`를 repo-relative로 정규화 (sbfl_* 방향) | **PM 추천** — envelope 일반 관례 |
| (b) | sbfl_*를 absolute로 정규화 (failure_proximity 방향) | 다른 envelope path들과의 일관성 깨짐 (예: regression engine path도 relative) |

PM 추천 = **(a)**. 이유:
- repo-relative는 envelope 전반의 path 관례
- AI consumer가 envelope path를 다른 envelope과 합쳐 처리 쉬움
- failure_proximity 1 mode만 정규화 → 변경 면적 작음

## Scope

### B2-1 metadata shape 정규화

- 3 mode 모두 `metadata = {changed_files_count, regression_reweighted}` 키 셋 가짐
- per-test mode는 `changed_files_count = None` (또는 0), `regression_reweighted = False` (또는 None) — 팀이 의미적으로 적절한 default 선택. handoff에 근거 명시.
- 명세 doc 갱신:
  - `design/interace-contract/localization.md` 또는 envelope freeze 문서 (팀 charter "owned files" 우선 확인)
  - "Localization metadata 키 셋은 mode 무관 동일. per-test mode에서는 의미 없는 키가 default 값을 가짐" 명시

### B2-2 file-path absoluteness 정규화

- `failure_proximity` mode의 code location file_path를 repo-relative로 정규화
- 정규화 위치: failure_proximity engine 내부 path emit 시점 또는 결과 wrapping 시점 (팀이 inspect 후 결정)
- 정규화 기준: workspace root (Run team 패턴 따름)
- 통합 테스트: 기존 failure_proximity E2E가 repo-relative path 어설션으로 갱신

## Out of scope

- 다른 mode (sbfl_*)의 path 처리 변경
- `localization-cache-rederived` 등 기존 warning code 변경
- mode 자체의 algorithmic 정의 변경
- `cli/output.py::EnvelopeWarning` shape 변경 (frozen 2026-06-07)
- 다른 팀 territory (Coverage, Run, Regression)

## 파일 footprint 가이드

- `src/novetest/localization/` (engine + mode-별 emit)
- `src/novetest/localization/failure_proximity*` (path 정규화 위치 후보)
- `design/interace-contract/localization.md` 또는 envelope 명세 문서
- `tests/unit/localization/`
- `tests/integration/localization/` 또는 `tests/integration/orchestration/`

정확한 파일은 코드 inspect 후 결정.

## Implementation guidance

### 1. metadata 키 셋 통일 — default 값 선택

- `changed_files_count`: per-test mode에서 의미상 NULL → `None` 또는 `0`. PM 선호 `None` (의미 없음 명시).
- `regression_reweighted`: per-test mode에서 NULL → `None` 또는 `False`. PM 선호 `None`.
- 팀이 model schema 살펴서 nullable 가능 여부 확인 + 적절한 default 선택. handoff에 근거 명시.

### 2. file-path 정규화 시점

- engine 내부 path 결정 시점 또는 결과 wrapping 시점.
- workspace root 기준 `os.path.relpath` 또는 `Path.relative_to`.
- workspace root는 이미 Run Record에 저장됨 (`workspace_path`).

### 3. 명세 doc 갱신 어휘

- 보수적 어휘. 현재 동작을 명시. 향후 변경 여지를 남기되 contract를 명확히.
- 예시:
  > "Localization result의 `metadata`는 mode 무관 다음 키 셋을 가짐:
  > `changed_files_count: int | None`, `regression_reweighted: bool | None`.
  > per-test mode는 metadata가 의미 없으므로 두 키 모두 `None`."

## Definition of done

1. 3 mode 모두 `metadata` 키 셋 동일 (`changed_files_count`,
   `regression_reweighted` + default 값)
2. `failure_proximity` mode의 file_path가 repo-relative로 정규화
3. 명세 doc 갱신 (interface-contract 또는 envelope 명세)
4. 통합 테스트 매트릭스: 3 mode × 정규화된 envelope shape
5. 단위 테스트: metadata default 값 + path 정규화 로직
6. `uv run mypy --strict src/novetest` 클린
7. `uv run pytest -q tests/unit tests/integration` 그린
8. WORKLOG.md 엔트리 (charter 양식)
9. Handoff `agent-comms/handoffs/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`
   + DoD bullets believed closed 리스트
10. `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **B2 UX normalization 3팀 병렬 cycle의 2/3**. 같은
cycle에 진행 중:

- Coverage팀: outside-workspace path 정책 harmonization
  (`agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`)
- Run팀: 6개 어댑터 `artifact_dir.resolve()` 예방적 하드닝
  (`agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Localization (본 슬라이스) | `src/novetest/localization/` + 관련 tests + localization 명세 doc |
| Coverage (페어 1) | `src/novetest/coverage/` + 관련 tests + coverage decision (amend) |
| Run (페어 2) | `src/novetest/run/adapters/` + 관련 단위 tests only |

### 만지지 말 것

- `cli/output.py::EnvelopeWarning` shape (frozen 2026-06-07)
- `run/types.py::AdapterWarning` shape
- `coverage/**`, `run/**`, `regression/**`, `replay/**`
- v1 metadata bridge 키 (`coverage_unavailable_*`) — post-MVP cleanup

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native 어댑터 변경 아니므로 §2.5 게이트 발동 **안 함**.
일반 host에서 진행 가능.

## Reference

- `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"Other deferred items" #5 — 원본 deferred 항목
- `agent-comms/history/2026-06-08-b1-polish-parallel-pair-defect7-and-fixed-tests-spec.md`
  §"PM dispositions" 2 — CLI emit 위치 deviation 패턴 (직전 Localization
  slice의 architectural deviation 사례; 위치 결정 자율성 참고)
- `.claude/agents/novetest-localization-team.md` — 팀 charter

## 추정

- B2-1 metadata: ~10-20 LOC src + ~15-25 LOC test
- B2-2 path: ~10-20 LOC src + ~15-25 LOC test
- 명세 doc: ~10-20 lines docs
- Wall time: 2-3 시간
- 단일 cycle, 단일 attempt 예상
