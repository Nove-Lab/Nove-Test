---
from: novetest-pm-team
to: novetest-regression-team
type: task
status: pending
created: 2026-06-08
slug: fixed-tests-spec
related:
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md
---

# Task — Regression engine `fixed_tests` 명세 정리

## Mission

Manual Test가 발견한 "fail->pass transition인데도 `fixed_tests`가 비어
있는" 케이스가 **의도된 동작인지 버그인지** 판정. 결과에 따라:
- **의도면** -> interface-contract 문서로 명세 강화 + 통합 테스트로
  동작 핀 (same-set transition populate / different-set empty)
- **버그면** -> `fixed_tests` populate 로직 수정 + 통합 테스트로 재현
  + 대칭적으로 `regressed_tests` 점검

## Background — self-contained context

수신 팀이 이 대화를 볼 수 없으므로 문제 전체를 자체 포함된 형태로
기술함.

Regression engine은 두 run의 outcome을 비교해서 transition을 검출함.
출력 facts의 두 면:
- `regressed_tests`: pass->fail로 바뀐 테스트들
- `fixed_tests`: fail->pass로 바뀐 테스트들

### Manual Test 2026-06-01 D6 시나리오 F+ 발견

Phase 4 modes narrative 마감 cycle에서 Manual Test가 발견 (원본:
`agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`
§"Regression engine subtle question (carry-forward to Regression team)"):

> Manual Test noticed during D6 Scenario F+: regression engine returned
> `kind: fact-set` with **empty `regressed_tests` AND empty
> `fixed_tests`** even though run 1 was failing and run 2 was passing (a
> clear pass->fail or fail->pass transition).

### 두 해석

원본 발견자가 제시한 두 가능성:

- **(I) 의도된 동작**: regression engine은 "동일 test 집합"
  안에서만 transition을 검출. run 1과 run 2가 다른 test set이면 양쪽
  모두 empty가 정상.
- **(II) 버그**: `fixed_tests` populate 로직이 fail->pass transition을
  놓침 (또는 `regressed_tests`의 대칭 로직에도 같은 결함이 있을 수 있음).

### 상태

당시 carry-forward로 deferred됨 ("Status: deferred carry-forward, NOT
queued. Out of this cycle's scope (Manual Test was probing D6's status
surface, not the regression engine itself). PM may surface as a
Regression team question when next touching that engine."). 이번 B1
polish cycle에서 surface.

## Scope — 2단계

본 슬라이스는 **Q&A -> Fix or Document** 2단계 구조. 첫 번째 단계에서
판정을 명확히 한 뒤 결과에 따라 두 번째 단계의 작업이 달라짐.

### Phase 1 — Q&A (의도성 판정)

1. **재현**: D6 시나리오 F+에 가까운 fixture/setup 구성. 같은 fixture
   project로 두 번 run, 첫 번째는 fail, 두 번째는 pass. **test set 동일**
   (같은 node_id 집합).
2. **코드 inspection**: `src/novetest/regression/` 안에서 `fixed_tests`
   populate 로직 추적 + test set 비교 로직 추적.
3. **판정**: 위 재현 케이스에서 `fixed_tests`가 비어 있다면 -> 그 path가
   intent인지 결함인지 결론.
   - Intent 판단 근거: 코드 주석, 기존 design doc, 다른 통합 테스트가
     같은 동작을 expectation으로 가지고 있는지 등
   - Bug 판단 근거: 명시적 intent 없음, 또는 명세 doc과 코드 동작이
     모순

### Phase 2 — Fix or Document

**(I) 의도면 — 명세 강화**:
- `design/interace-contract/regression.md` 또는 동등 명세 doc (Regression
  팀 territory)에 동작 명세 추가. 예시 어휘 (보수적):
  > `fixed_tests` populates only when a test with the same node_id
  > transitions fail->pass between two runs. If the test set diverges
  > between runs, transition detection is scoped to the intersection;
  > tests appearing only in one run are not counted as fixed or regressed.
- 통합 테스트 2 케이스 핀:
  1. Same test set + fail->pass transition -> `fixed_tests` non-empty
  2. Different test set (한 test가 run 2에서 사라짐) -> `fixed_tests`
     empty (또는 intersection 적용 시 그 안의 transition만)
- Manual Test가 본 D6 시나리오 F+가 어느 케이스에 해당하는지 명세 문서
  + handoff에 명시

**(II) 버그면 — 수정 + 대칭성 점검**:
- `fixed_tests` populate 로직 수정 (구체 변경은 코드 살펴본 뒤 결정)
- 통합 테스트 추가: D6 시나리오 F+ 재현 + populate 검증
- **대칭성 점검**: `regressed_tests`도 같은 patterned 결함이 있는지
  확인. pass->fail transition도 정확히 검출되는지 추가 통합 테스트로 핀
- 만약 `regressed_tests`도 결함이 있으면 같이 수정 (single cycle scope
  안에서)

## 파일 footprint 가이드

- `src/novetest/regression/` — 로직 점검 + 가능성 있는 수정
- `design/interace-contract/regression.md` 또는 비슷 — 명세 강화 시
  (Regression팀 charter `.claude/agents/novetest-regression-team.md`의
  "owned files" 섹션 우선 확인)
- `tests/fixtures/projects/` — 재현 fixture 추가 가능성 (Regression팀
  territory 안에서)
- `tests/integration/regression/` — 통합 테스트
- `tests/unit/regression/` — 단위 테스트

## Implementation guidance

### 1. 재현 fixture

- Manual Test가 본 D6 시나리오 F+에 가까운 setup. 기존
  `tests/fixtures/projects/` 안의 fixture로 충분히 재현 가능한지 먼저
  확인 (예: `pytest-failing` 또는 비슷한 것). 부족하면 minimal 새 fixture
  하나 추가 (Regression팀 territory).
- 재현 절차 (예시 흐름):
  1. fixture run 1: 어떤 test가 fail
  2. fixture 코드 수정 (또는 setup 변경)으로 같은 test가 pass
  3. fixture run 2: 같은 test가 pass
  4. `novetest regression compare <run1> <run2>` -> `fixed_tests` 확인

### 2. 코드 inspection 시작점

- `src/novetest/regression/`의 transition 검출 함수
- Grep 시작점: `fixed_tests`, `regressed_tests`, `transition`,
  `outcome.*comp`, `node_id.*comp`
- test set 비교 로직 — 어떻게 "동일 test set" 또는 "intersection"을
  정의하는지

### 3. 판정 후

- 의도면: **명세 어휘는 보수적으로**. 현재 동작을 그대로 기술. 향후
  변경 여지를 남기되 현재 contract를 명확히.
- 버그면: 수정 최소 surface로. populate 로직 한 함수 수정에 집중.
  대칭성 점검은 추가 테스트로 (또 다른 결함이 발견되면 그 결함도 같이
  수정 — 단, 결함 범위가 본 slice scope를 넘으면 별도 question/follow-up
  cycle로 분리).

### 4. Handoff 결론 어휘

Handoff에 다음 두 항목 반드시 명시:
1. **판정**: "intent" 또는 "bug" 한 단어 명시 + 근거 (코드 path 인용
   또는 명세 doc 인용)
2. **D6 시나리오 F+ 해석**: 위 판정 기준으로 Manual Test가 본 케이스가
   어떻게 해석되는지

## Definition of done

### Phase 1 (Q&A) DoD

1. D6 시나리오 F+ 재현 가능한 fixture/integration setup 구성 (기존
   fixture 활용 또는 minimal 새 fixture 추가)
2. `fixed_tests` populate 로직 코드 inspection 완료 — handoff에 코드
   path + 분석 결과 명시
3. **판정 결과** ("intent" 또는 "bug") handoff에 명확히 결론 + 근거

### Phase 2 DoD — 판정에 따라

**의도 (I)면**:
- 4a. 명세 doc (interface-contract/regression.md 또는 Regression팀
   territory의 동등 위치) 에 동작 명세 추가
- 5a. 통합 테스트 2 케이스 핀: same-set transition populate /
   different-set behavior
- 6a. 단위 테스트로 transition 검출 로직 그린

**버그 (II)면**:
- 4b. `fixed_tests` populate 로직 수정
- 5b. 통합 테스트: D6 시나리오 F+ 재현 -> `fixed_tests` non-empty 검증
- 6b. `regressed_tests` 대칭성 점검 — 별도 통합 테스트 (pass->fail
   transition 정확 검출). 결함이면 같이 수정 또는 follow-up question
   filed
- 7b. 단위 테스트로 populate 로직 그린

### 공통 DoD

7. `uv run mypy --strict src/novetest` 클린
8. `uv run pytest -q tests/unit tests/integration` 그린
9. WORKLOG.md 엔트리 추가 (charter 양식 준수)
10. Handoff 작성 `agent-comms/handoffs/regression-team-2026-06-08-fixed-tests-spec.md`
    + "DoD bullets believed closed" 리스트 명시 + 판정 결과 명시
11. `python3 tools/regen_comms_index.py` 실행 + INDEX 변경 스테이지

## Cross-team coordination — parallel cycle

본 슬라이스는 **B1 critical polish 2팀 병렬 cycle의 2/2**. 같은 cycle에
진행 중:
- Localization팀: Defect 7 `failure_proximity` warning loop
  (`agent-comms/tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 만지는 디렉토리 |
|---|---|
| Regression (본 슬라이스) | `src/novetest/regression/` + 관련 tests + 명세 doc |
| Localization (페어 슬라이스) | `src/novetest/localization/` + `src/novetest/orchestration/workflows/` + (선택) `src/novetest/cli/handlers/localization.py` + 관련 tests |

두 슬라이스 file footprint는 완전 분리됨. 06-07 envelope-warnings +
cobertura-derive parallel pair 패턴의 반복.

### 만지지 말 것 (다른 cycle에서 닫힘 또는 다른 팀 territory)

- `cli/output.py::EnvelopeWarning` shape — 06-07 envelope-warnings-
  projection으로 freeze. 재사용 OK, shape 변경 금지.
- `run/types.py::AdapterWarning` shape — Run팀 territory
- `run/adapters/**` — Run팀 territory
- `localization/**` — 페어 슬라이스 territory
- `coverage/**` — Coverage팀 territory
- v1 metadata bridge 키 (`coverage_unavailable_*`) — post-MVP cleanup
  cycle 작업 (decision 명시)

### Main Branch merge 순서

알파벳 순서로 FF-merge: **localization -> regression** (단순 결정 규칙;
어느 쪽이 먼저 끝나도 순서는 같음).

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native 어댑터 src + 통합 테스트를 동시 터치하지 **않음**
→ §2.5 게이트 발동 안 함. 일반 host에서 진행 가능.

## Reference

- `agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`
  §"Regression engine subtle question (carry-forward to Regression team)"
  — 원래 발견 + 두 해석
- `.claude/agents/novetest-regression-team.md` — 팀 charter, owned files
  명세
- 기존 regression interface contract / workflow docs — Regression팀
  charter가 가리키는 위치

## 추정

- Phase 1 (Q&A): ~30분-1시간 (재현 + inspection)
- Phase 2 (수정 또는 명세):
  - 의도면: ~30-50 LOC test + ~10-30 LOC docs (가벼움)
  - 버그면: ~20-50 LOC src + ~50-100 LOC test (적당함)
- Wall time: 2-3 시간 (판정 포함)
- 단일 cycle, 단일 attempt 예상
