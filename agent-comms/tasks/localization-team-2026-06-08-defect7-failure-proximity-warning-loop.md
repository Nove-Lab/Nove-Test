---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-08
slug: defect7-failure-proximity-warning-loop
related:
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
  - agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md
---

# Task — Defect 7: `failure_proximity` mode formula-mismatch warning loop

## Mission

`failure_proximity` mode에서 사용자가 `--formula` 인자에 ochiai 이외 값을
넣었을 때 발생하는 무한 warning loop를 차단. AI agent가 warning을 보고
재시도해도 같은 warning이 반복 발생하지 않도록 구조적 noop 신호를 한
번만 envelope에 노출.

## Background — self-contained context

수신 팀이 이 대화를 볼 수 없으므로 문제 전체를 자체 포함된 형태로
기술함.

Phase 4 Localization은 세 mode를 가짐: `sbfl_per_test`,
`sbfl_aggregate`, `failure_proximity`. 세 번째인 `failure_proximity`는
coverage 없이도 동작하는 fallback mode이며, **mode 알고리즘 자체가
formula에 무관함** (모든 SBFL formula는 spectrum-based이므로). 그럼에도
engine은 finding에 `formula: "ochiai"`를 placeholder로 반환함.

### Defect 7 시나리오

사용자가 `novetest localization --formula op2` 를 no-coverage fixture에
대해 실행하면:
1. CLI/orchestration이 `requested formula="op2"` vs cached/returned
   `formula="ochiai"` 를 비교 → mismatch
2. mismatch가 cache invalidation을 트리거 → re-derive
3. Re-derive 결과는 다시 `formula="ochiai"` (mode가 formula-agnostic이라
   placeholder 그대로)
4. Warning 다시 emit (mismatch 반복)
5. AI agent가 warning을 보고 재시도하면 1로 돌아감 — **무한 loop**

### Severity / 발견 경로

- Severity: **LOW** (workaround: `--formula` 안 주면 됨; default ochiai로
  단번에 처리됨)
- Trigger: explicit `--formula <non-ochiai>` 인자 + no-coverage fixture
- 발견: Manual Test, 2026-06-01, Phase 4 modes narrative 마감 시
  (`agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md`
  §"Defect 7 (low priority, optional) — `failure_proximity` warning loop")
- AI agent 위험: retry loop 자체는 LOW지만 envelope.warnings 표면이
  AI-consumer 대상이라 명확한 단일 signal이 가치가 큼

### 두 fix 옵션 (Manual Test 추천)

원본 발견 시 두 옵션이 제안됨:
- (a) CLI에서 formula mismatch check를 `mode == "failure_proximity"` 일
  때 skip
- (b) 새로운 distinct warning code (예: `localization-formula-noop-in-mode`)
  emit해서 AI agent가 "이건 fixable misconfig가 아니라 structural noop"
  임을 인지

## PM 권장: 옵션 (b)

권장 근거:
1. **책임 분리**: (a)는 CLI가 mode-aware해짐. CLI는 transport,
   localization은 engine 책임. mode-knowledge가 CLI에 노출되면 향후
   mode 추가 시 두 곳에서 동기화 필요.
2. **AI-consumer signal**: (b)는 `envelope.warnings[]` (2026-06-07
   envelope-warnings-projection slice로 만들어진 surface) 를 활용. AI
   agent가 단일 코드만 보고 "structural noop이라 retry해도 의미 없음"
   판단 가능.
3. **기존 패턴 일치**: `localization-cache-rederived` warning이 이미
   orchestration-derived path로 envelope.warnings에 emit됨. 동일 패턴
   따르기 쉬움.
4. **Forward-compat**: 향후 다른 mode가 추가되어도 동일 warning code
   재사용 가능 (mode-agnostic warning shape).

### Emit 위치 — orchestration 선호

PM 선호는 **orchestration layer** emit (예: workflow handler 또는
relevant orchestration module):
- localization engine은 facts 반환만 (pure)
- "어떤 warning이 envelope에 가야 하는지"는 orchestration 책임
- 기존 `localization-cache-rederived`도 같은 패턴

다만 정확한 emit 위치는 코드 inspect 후 Localization팀이 결정. engine
내부에서 emit하는 게 더 자연스럽다면 그 판단을 존중함 (handoff에 근거
명시 요청).

## Scope

### In scope

- `failure_proximity` mode + non-default formula 조합에서 envelope에
  단일 warning code (`localization-formula-noop-in-mode` 또는 팀 판단의
  단명) 1회 emit
- Formula mismatch가 무한 re-derive loop를 트리거하지 않도록 처리
  (mode-aware skip 또는 warning-after-noop)
- Test 매트릭스 4 조합 단위/통합 테스트로 핀:
  1. `failure_proximity` + default (ochiai): no warning, no mismatch
  2. `failure_proximity` + non-default (op2 또는 임의 non-ochiai):
     warning 1건, no loop
  3. `sbfl_per_test` (또는 sbfl_aggregate) + default: 기존 동작
  4. `sbfl_per_test` (또는 sbfl_aggregate) + non-default: 기존 동작 (해당
     formula로 계산됨)

### Out of scope

- Localization engine 자체의 formula 계산 로직 변경 —
  `failure_proximity`가 placeholder로 `ochiai` 반환하는 것은 그대로 유지
  (이게 변경되면 mode의 algorithmic 정의가 바뀌는 거라 별도 design 결정
  필요)
- 다른 mode (sbfl_per_test, sbfl_aggregate)의 formula 처리 변경
- `cli/output.py::EnvelopeWarning` shape 변경 — 06-07 envelope-warnings-
  projection slice에서 freeze. 재사용만.
- `run/types.py::AdapterWarning` shape 변경 — Run팀 territory, 본 cycle
  미참여.
- v1 metadata bridge 키 (`coverage_unavailable_*`) 정리 — decision
  `2026-06-06-adapter-warning-surface-v1-metadata-channel` §"Notes on
  co-existence"에 따라 post-MVP cleanup cycle 작업.

## 파일 footprint 가이드

- `src/novetest/localization/` — engine 내부 warning emit 검토 또는
  factsheet 메타 추가
- `src/novetest/orchestration/workflows/` — workflow가 formula mismatch
  비교 + warning emit 위치 후보
- `src/novetest/cli/handlers/localization.py` — CLI-level handler 후보
  (이 경로가 mismatch 비교 위치라면)
- `tests/unit/localization/` 또는 `tests/unit/orchestration/` — 단위
  테스트
- `tests/integration/orchestration/` 또는 비슷 — CLI-level 통합 테스트

정확한 파일은 코드 inspect 후 결정. 위 목록은 출발점.

## Implementation guidance

### 1. Warning code 표준화

- 권장 code: `localization-formula-noop-in-mode` (단명, 카테고리 명확)
- 팀 판단에 따라 더 짧은 alternative 가능; handoff에 근거 명시.
- Warning shape (`EnvelopeWarning` 또는 동등 — 06-07 patterns 참조):
  - `code`: 위 문자열
  - `message`: AI-readable 한 줄 (예: "Formula 'op2' is a no-op in
    failure_proximity mode; engine always returns 'ochiai' placeholder.
    Re-running with a different formula will not produce different
    results.")
  - `details`: `{requested_formula: str, returned_formula: str, mode: str}`

### 2. Mismatch check + warning emit 흐름

- 현재 codebase에서 "formula mismatch가 re-derive를 트리거하는" 위치
  파악 (grep 시작점: `formula`, `mismatch`, `re-derive`, `rederive`,
  `localization-cache-rederived`)
- `mode == "failure_proximity"` 일 때:
  - re-derive 트리거 skip
  - 대신 위 warning 1회 emit
- `mode != "failure_proximity"` 일 때: 기존 동작 그대로

### 3. Warning emit 횟수 — "1회"의 정의

같은 invocation 안에서는 1회. 사용자가 같은 명령을 다시 실행하면 다시
emit되는 것은 정상 (cache 동작에 따라). 핵심은:
- **무한 loop 없음** (같은 invocation 안에서 mismatch -> re-derive ->
  mismatch -> ... 가 안 됨)

### 4. Test 매트릭스

단위 테스트 (4 조합 + cache 동작):
- `test_failure_proximity_default_formula_no_warning`
- `test_failure_proximity_non_default_formula_emits_noop_warning_once`
- `test_sbfl_default_formula_unchanged_behavior`
- `test_sbfl_non_default_formula_unchanged_behavior`
- `test_failure_proximity_non_default_formula_no_rederive_loop`
  (cache state pre/post 호출 검증)

통합 테스트 (CLI subprocess):
- no-coverage fixture (예: 기존 `tests/fixtures/projects/`에서 적합한
  것; 없으면 minimal 추가) 대상으로 `novetest localization --formula op2`
  → envelope.warnings에 `localization-formula-noop-in-mode` 1건 + exit
  code 정상

## Definition of done

1. `failure_proximity` mode + non-default formula 호출 시
   envelope.warnings에 noop warning code 1건 emit (단일 invocation 안에서)
2. 동일 invocation 안에서 mismatch -> re-derive -> mismatch 무한 loop
   발생 안 함 (단위 테스트로 명시 검증)
3. mode != `failure_proximity` 일 때 기존 동작 unchanged (4 formula ×
   2 sbfl mode 기존 단위 테스트 그대로 그린)
4. 통합 테스트: no-coverage fixture + `--formula op2` CLI subprocess
   호출 → envelope.warnings 검증
5. 단위 테스트 매트릭스 위 5개 그린
6. `uv run mypy --strict src/novetest` 클린
7. `uv run pytest -q tests/unit tests/integration` 그린
8. WORKLOG.md 엔트리 추가 (charter 양식 준수)
9. Handoff 작성 `agent-comms/handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
   + "DoD bullets believed closed" 리스트 명시
10. `python3 tools/regen_comms_index.py` 실행 + INDEX 변경 스테이지

## Cross-team coordination — parallel cycle

본 슬라이스는 **B1 critical polish 2팀 병렬 cycle의 1/2**. 같은 cycle에
진행 중:
- Regression팀: `fixed_tests` 명세 정리
  (`agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 만지는 디렉토리 |
|---|---|
| Localization (본 슬라이스) | `src/novetest/localization/` + `src/novetest/orchestration/workflows/` + (선택) `src/novetest/cli/handlers/localization.py` + 관련 tests |
| Regression (페어 슬라이스) | `src/novetest/regression/` + 관련 tests + 명세 doc |

두 슬라이스 file footprint는 완전 분리됨. 06-07 envelope-warnings +
cobertura-derive parallel pair 패턴의 반복.

### 만지지 말 것 (다른 cycle에서 닫힘)

- `cli/output.py::EnvelopeWarning` shape — 06-07 envelope-warnings-
  projection으로 freeze. 재사용 OK, shape 변경 금지.
- `run/types.py::AdapterWarning` shape — Run팀 territory, 본 cycle 미참여
- `run/adapters/**` — Run팀 territory
- `coverage/**` — Coverage팀 territory, 본 cycle 무관
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
  §"Defect 7" — 원래 발견 + 두 fix 옵션
- `agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
  §"Notes on co-existence" — envelope.warnings v2 surface 명세
- `agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md`
  §"Adapter-warning surface — final v1 scorecard" — projection 패턴
- `.claude/agents/novetest-localization-team.md` — 팀 charter

## 추정

- Scope: ~20-40 LOC src + ~30-50 LOC test
- Wall time: 1-2 시간
- 단일 cycle, 단일 attempt 예상
