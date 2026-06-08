---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-06-08
slug: outside-workspace-path-harmonization
related:
  - agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md
  - agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md
---

# Task — Coverage outside-workspace path 정책 harmonization (B2-3)

## Mission

Coverage 엔진 파서들 사이의 outside-workspace path 표현 비대칭을 정리.
cargo_lcov는 outside-workspace path를 절대 경로 + `lcov_warnings`로
emit하고, istanbul은 `../`-prefixed relpath로 emit. 동일 surface
(Coverage Facts의 file path)에서 두 표현이 섞이면 cross-ecosystem
consumer가 매번 분기해야 함. 비대칭 해결.

## Background — self-contained

`agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md`
§"Coverage handoff Open Q's" #3 (DEFERRED 항목)에서 명시:

> "Outside-workspace path handling deviates from istanbul precedent
> (cargo keeps absolute + emits `lcov_warnings`; istanbul uses
> `../`-prefixed relpath). DEFERRED — current behavior is correct per
> brief; harmonization would touch both parsers + amendment to
> `decisions/2026-05-15-coverage-facts-json-layout.md`. Low priority;
> flagged in this history for future awareness."

이번 B2 UX normalization cycle에서 surface.

### 현재 5개 파서

Coverage 엔진은 5개 파서:
- `coverage_parser.py` (Python coverage.py JSON)
- `istanbul_parser.py` (JS/TS)
- `lcov_parser.py` (Rust cargo / Go gotest 공용 LCOV)
- `jacoco_parser.py` (Java)
- `cobertura_parser.py` (.NET)

알려진 비대칭은 위 2개 (lcov + istanbul). 다른 3개의 outside-workspace
처리는 이 brief의 첫 단계에서 확인 필요.

## PM 권장 시나리오: (A) `../`-prefixed relpath로 정규화

### 3개 시나리오 옵션

| ID | 방향 | 변경 면적 | Decision amend 면적 |
|---|---|---|---|
| **(A)** | cargo + (다른 파서가 비대칭이면 그것도) → istanbul 패턴 (`../`-prefixed relpath) | 1-2 파서 수정 | 작음 ("path는 `../`-prefixed relpath로 통일") |
| (B) | istanbul + 다른 → cargo 패턴 (absolute + warnings) | 여러 파서 + warning channel | 큼 |
| (C) | ecosystem별 차이 인정 + decision에 명시 | 0 (코드 변경 없음) | 중간 (명세 강화만) |

### PM 추천 = (A) 근거

1. `../`-prefixed relpath는 Python pathlib / JS path.relative / Node 등
   범용 path 표현. AI consumer에게도 처리 쉬움.
2. outside-workspace 정보가 path 자체로 self-evident (절대 경로 + 별도
   warning 채널보다 envelope 1면에 집중).
3. 변경 면적이 가장 작음 — 1개 (또는 2개) 파서만 수정.
4. Decision amend도 단명한 1문장 추가.

### `lcov_warnings`의 운명

PM 의견: relpath로 정규화 후엔 outside-workspace 식별이 path 자체로
가능 → `lcov_warnings` emit **유지하되 forensic-only**로 (사용자가
"이 파일은 워크스페이스 밖이에요"를 명시적 시각 신호로 받음).
Coverage 팀이 코드 살펴본 후 emit-제거가 더 깔끔하다고 판단하면
question 파일링.

## Scope

### Phase 1 — Inspect

1. 5개 파서 각각의 outside-workspace path 처리 점검:
   - lcov_parser (cargo, gotest 공용)
   - istanbul_parser
   - coverage_parser
   - jacoco_parser
   - cobertura_parser
2. 비대칭 매트릭스 작성 (어느 파서가 어떻게 처리하는지)

### Phase 2 — Harmonize

PM 시나리오 (A) 따라:
- 절대 경로 emit하는 파서를 `../`-prefixed relpath로 정규화
- 기존 절대 경로 + warning channel 동작이 있는 경우 PM과 같이 운명 결정
  - 기본: warning emit 유지 (forensic continuity)
  - Alternative: emit 제거 (cleaner) → handoff에 근거 명시

### Phase 3 — Decision amend + tests

- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` amend
  (CEO 승인 받음 — 본 brief 자체가 시나리오 (A)를 PM 추천으로 박았고
  CEO가 디스패치하는 시점에 implicit 비준)
  - 1-2 문장 추가: "outside-workspace path는 `../`-prefixed relpath로
    표현. ecosystem별 native 도구가 절대 경로를 emit하더라도 파서가
    `os.path.relpath`로 정규화 후 envelope에 surface."
- 단위 테스트: 각 정규화된 파서당 outside-workspace 픽스쳐 1-2개
- 통합 테스트: 기존 cargo/istanbul E2E 가 정규화된 path 어설션으로 갱신

### Out of scope

- Phase 1 inspect 결과 다른 시나리오 (B 또는 C)가 더 적합하다면 brief
  진행 멈추고 question 파일링 (`questions/coverage-team-2026-06-08-outside-workspace-scenario.md`)
- 비대칭 외의 다른 path 표현 (예: case-sensitivity, symlink 처리) 손대지 말 것
- 다른 파서의 deeper rewriting

## 파일 footprint 가이드

- `src/novetest/coverage/lcov_parser.py` (primary)
- `src/novetest/coverage/istanbul_parser.py` (이미 정규화됨; assertion 강화 가능)
- 다른 파서들 (inspect 후 결정)
- `tests/unit/coverage/test_lcov_parser.py` 등
- `tests/integration/coverage/` (cargo/istanbul E2E)
- `tests/fixtures/coverage/` (필요시 outside-workspace 픽스쳐 추가)
- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` (amend)

## Definition of done

1. 5개 파서 outside-workspace path 처리 매트릭스 handoff에 명시
2. 비대칭 파서가 `../`-prefixed relpath로 정규화 (시나리오 A)
3. `lcov_warnings` (또는 동등) 운명 결정 + handoff에 근거 명시
4. `decisions/2026-05-15-coverage-facts-json-layout.md` amend (1-2 문장)
5. 단위 테스트: 각 정규화 파서당 outside-workspace 케이스 1-2개
6. 통합 테스트: cargo + istanbul E2E가 정규화된 path 어설션으로 갱신
7. `uv run mypy --strict src/novetest` 클린
8. `uv run pytest -q tests/unit tests/integration` 그린
9. WORKLOG.md 엔트리 (charter 양식)
10. Handoff `agent-comms/handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`
    + DoD bullets believed closed 리스트
11. `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **B2 UX normalization 3팀 병렬 cycle의 1/3**. 같은
cycle에 진행 중:

- Localization팀: metadata shape + file-path absoluteness 정규화
  (`agent-comms/tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`)
- Run팀: 6개 어댑터 `artifact_dir.resolve()` 예방적 하드닝
  (`agent-comms/tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Coverage (본 슬라이스) | `src/novetest/coverage/` + 관련 tests + `decisions/2026-05-15-coverage-facts-json-layout.md` (amend) |
| Localization (페어 1) | `src/novetest/localization/` + 관련 tests |
| Run (페어 2) | `src/novetest/run/adapters/` + 관련 단위 tests only |

### 만지지 말 것

- `cli/output.py::EnvelopeWarning` shape (frozen 2026-06-07)
- `run/types.py::AdapterWarning` shape
- `localization/**`, `run/**`, `regression/**`, `replay/**`
- 다른 cycle/팀 territory

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native 어댑터 변경 아니므로 §2.5 게이트 발동 **안 함**.
일반 host에서 진행 가능. (cargo/istanbul/jacoco/cobertura E2E가
toolchain-gated이지만 그건 기존 테스트의 환경 종속이지 §2.5와 다름.)

## Reference

- `agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md`
  §"Coverage handoff Open Q's" #3 — 원본 deferred 항목
- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`
  §3 — Coverage Facts JSON 명세 (amend 대상)
- `.claude/agents/novetest-coverage-team.md` — 팀 charter

## 추정

- Phase 1 inspect: ~30분-1시간
- Phase 2 harmonize: ~30-50 LOC src
- Phase 3 amend + tests: ~30-50 LOC test + ~5 LOC decision
- Wall time: 2-3 시간
- 단일 cycle, 단일 attempt 예상
