---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-06-08
slug: artifact-dir-resolve-hardening
related:
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
  - agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
---

# Task — Run adapters `artifact_dir.resolve()` 예방적 하드닝 (B2-4)

## Mission

6개 native engine 어댑터 entry point에서 `artifact_dir` 인자를
`.resolve()` 호출로 정규화. 미래 caller가 relative path를 넘기는 경우
artifact가 잘못된 디렉토리에 저장되는 silent failure를 예방.

## Background — self-contained

`agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md`
§60에 기록된 long-standing TODO:

> "**Run team (optional, low priority).** Add `artifact_dir =
> artifact_dir.resolve()` at the top of `run_pytest` to harden against
> future callers passing relative `artifact_dir`. Currently no
> production caller hits this (all build absolute paths under
> `.novetest/...`); the hardening is preemptive. One-line change."

5개월 전 시점에는 pytest 어댑터만 존재. 그동안 6개 어댑터 완성:
- pytest
- jest
- junit
- gotest (go-test)
- cargo (cargo-test)
- xunit (.NET)

본 슬라이스는 모든 6개 어댑터에 동일 패턴 적용 + 단위 테스트로 핀.

## Scope

### Phase 1 — 6개 어댑터 entry point 확인

- 각 어댑터의 `artifact_dir` 인자 받는 entry point 함수 위치 확인
- 현재 어떤 caller가 어떻게 path를 빌드하는지 확인 (모두 absolute path
  로 빌드한다는 5개월 전 기록이 여전히 사실인지 검증)

### Phase 2 — `.resolve()` 적용

- 각 어댑터 entry point 함수 최상단에 `artifact_dir = artifact_dir.resolve()` 1줄 추가
- 또는 `if not artifact_dir.is_absolute(): artifact_dir = artifact_dir.resolve()` (idempotent + intent 명시)
- 팀 판단 — handoff에 근거 명시

### Phase 3 — 단위 테스트

- 각 어댑터당 단위 테스트 1-2개:
  1. relative path 전달 시 정상 동작 (artifact가 예상 위치에 저장됨)
  2. absolute path 전달 시 기존 동작 unchanged
- **통합 테스트는 새로 만들지 않음** — 기존 통합 테스트는 이미 absolute
  path 사용. §2.5 게이트 발동 회피 목적.

## Out of scope

- 다른 어댑터 인자 (workspace_path, fixture_dir 등) 하드닝
- 통합 테스트 추가
- caller 측 path 빌드 로직 변경

## 파일 footprint 가이드

- `src/novetest/run/adapters/pytest_adapter.py`
- `src/novetest/run/adapters/jest_adapter.py`
- `src/novetest/run/adapters/junit_adapter.py`
- `src/novetest/run/adapters/gotest_adapter.py` (또는 비슷한 이름)
- `src/novetest/run/adapters/cargo_adapter.py` (또는 비슷한 이름)
- `src/novetest/run/adapters/dotnet_adapter.py`
- `tests/unit/run/adapters/test_*_adapter.py` (각각)

## Implementation guidance

### `.resolve()` vs `.absolute()` 선택

- `Path.resolve()`: symlink follow + normalize (`..` 해석)
- `Path.absolute()`: cwd 기준 prepend만, symlink/`..` 미해석
- PM 권장 = `.resolve()` (보다 강건). 팀 판단 다르면 handoff에 근거 명시.

### Idempotency 보장

- absolute path를 받았을 때도 `.resolve()`는 안전 (no-op + symlink follow)
- 따라서 무조건 `artifact_dir = artifact_dir.resolve()` 적용해도 됨

## Definition of done

1. 6개 어댑터 entry point 모두 `artifact_dir.resolve()` (또는 동등) 적용
2. 각 어댑터당 단위 테스트 1-2개: relative path resilience + absolute path unchanged
3. `uv run mypy --strict src/novetest` 클린
4. `uv run pytest -q tests/unit` 그린 (통합 테스트 추가 안 함, 기존 통합
   테스트는 §2.5 게이트 회피 위해 변경 없음)
5. WORKLOG.md 엔트리 (charter 양식)
6. Handoff `agent-comms/handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md`
   + DoD bullets believed closed 리스트
7. `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **B2 UX normalization 3팀 병렬 cycle의 3/3**. 같은
cycle에 진행 중:

- Coverage팀: outside-workspace path 정책 harmonization
  (`agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`)
- Localization팀: metadata shape + file-path absoluteness 정규화
  (`agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Run (본 슬라이스) | `src/novetest/run/adapters/` + 관련 단위 tests only |
| Coverage (페어 1) | `src/novetest/coverage/` + 관련 tests + coverage decision (amend) |
| Localization (페어 2) | `src/novetest/localization/` + 관련 tests + localization 명세 doc |

### 만지지 말 것

- `cli/output.py::EnvelopeWarning` shape (frozen 2026-06-07)
- `run/types.py::AdapterWarning` shape — 본 슬라이스는 어댑터 entry
  내부의 path resolve만 만짐, types/normalizer는 unchanged
- `coverage/**`, `localization/**`, `regression/**`, `replay/**`
- 어댑터 통합 테스트 (§2.5 게이트 회피 위해 변경 없음)
- v1 metadata bridge 키 — post-MVP cleanup

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### §2.5 equip-and-exercise 게이트

본 슬라이스는 어댑터 **src + 단위 테스트만** 만지고 어댑터 **통합
테스트는 손대지 않음** → §2.5 file-glob 휴리스틱 발동 안 함. 일반
host에서 진행 가능.

만약 인스펙션 결과 통합 테스트 추가가 정말로 필요하다고 판단되면 brief
일시 중단 + question 파일링 (`questions/run-team-2026-06-08-adapter-resolve-integration-need.md`).
PM이 §2.5 발동 여부 판단 후 진행.

## Reference

- `agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md`
  §60 — 원본 long-standing TODO (5개월 전 pytest only 시점)
- `agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
  §2.5 — file-glob 휴리스틱 (회피 위해 통합 테스트 변경 안 함)
- `.claude/agents/novetest-run-team.md` — 팀 charter

## 추정

- 6 어댑터 × 1줄 = ~6 LOC src
- 6 어댑터 × 1-2 단위 테스트 = ~30-60 LOC test
- Wall time: 1 시간
- 단일 cycle, 단일 attempt 예상
