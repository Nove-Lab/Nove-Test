# Nove Test — 코드베이스 리팩터링 프로그램 헌장 (Charter)

작성일: 2026-07-05 · 소유: PM(+CEO 승인) · 상태: **CEO 승인 완료 (2026-07-05)**
입력 리뷰: [`design/reviews/2026-07-04-codebase-review/`](../reviews/2026-07-04-codebase-review/) (v0.1.2 이후 `main` HEAD 대상, 확정 103건)

---

## 0. 이 문서의 역할

이 헌장은 **리팩터링 프로그램이 어떻게 운영되는가**를 고정한다 — 왜 하는지, 어디까지 하는지,
어떤 원칙으로 판단하는지, 완료를 어떻게 정의하는지. **개별 finding을 수락/기각하는 구체 판단과
우선순위 재배치**는 이 문서가 아니라 [`01-review-assessment.md`](01-review-assessment.md)에 있으며,
그 판단은 리뷰를 그대로 믿지 않고 **원 소스 코드에 대한 독립 적대 재검증**에 근거한다.

문서 지도와 독자별 진입점은 [`README.md`](README.md)에 있다. 이 헌장부터 읽는 것이 맞다.

---

## 1. 배경과 계기

Nove Test는 6개 네이티브 테스트 엔진(pytest/jest/JUnit5/go test/cargo-nextest/xunit)을
`novetest/v1` JSON 엔벨로프로 감싸 AI 에이전트에게 구조화 결과를 제공하는 폴리글롯 오케스트레이션
CLI다. 지배 철학은 **"we wrap engines, never replace them"** 이다.

v0.1.2 태그 이후 61개 커밋이 쌓였고(사용자 가시 기능 3종 + anchored-pin 엔진선택 모델 D1–D7 전체),
그 축적분에 대해 2026-07-04 전문가 리뷰를 받았다. 리뷰는 **출하 가능(shippable), 릴리스를 막는
치명 결함 없음**으로 판정하되, 지배적 위험 패턴을 크래시가 아니라 **"조용한 오답(silent
wrongness)"** — 엔진이 자신 있게 틀린 초록/결과를 내고 사람·AI가 그것을 신뢰하게 만드는 계열 —
로 지목했다. "we wrap engines" 제품에서 이것이 가장 비싼 실패다. 이 프로그램은 그 위험을
우선순위대로 제거한다.

---

## 2. 스코프

### 2.1 In scope

- 리뷰가 확정한 finding들을 **우선순위별 웨이브**로 처리한다(정확성·안전 → 하드닝·중복제거 → 대형 구조).
- 각 슬라이스는 **한 팀이 한 사이클에 처리 가능한 단위**로 쪼개고, 기존 팀 소유권(팀 charter)과 정렬한다.
- 문서-코드 드리프트는 **문서를 실물에 맞게 후퇴(retreat)**시켜 해소한다(코드를 문서의 허구에 맞추지 않는다).
- 중복(clone)은 그 자체가 버그가 아니어도, **이미 드리프트가 관측된 클론**은 SSoT + divergence-guard 테스트로 고정한다.

### 2.2 Out of scope (명시적 비목표)

- **신규 기능 추가.** 이 프로그램은 순수 개선/정정이다. 새 동사·새 엔진·새 엔벨로프 필드는 별도 스코프.
- **7번째 엔진.** 2026-05-25 매트릭스가 6개로 고정. 미스케줄. 이를 전제한 어떤 추상화도 지금은 Simplicity 위반.
- **어댑터 데코레이터 레지스트리.** 부채 (a)/(d) 판정대로 **구현하지 않는다**(§4 원칙 참조).
- **`workspaces` 동사 본체.** 제품 결정 미스케줄. 완결성 테스트만 스코프(리뷰 S46).
- **v1 wire 스키마 rename**(`test_id`→`node_id` 등). 스키마가 v1로 동결. docstring 명시만; 실제 rename은 차기 schema bump 후보.
- **`normalizer.parse_artifacts`의 대규모 adapter-클래스 이관.** 904줄 normalizer + ~6.5k LOC 재편 대비 회수 미정.
- **WORKLOG.md / agent-comms/history 백패치.** 불변 회고 기록. 손대지 않는다.

---

## 3. 운영 모델 (프로그램은 이렇게 굴러간다)

1. **웨이브 구조.** 릴리스(W0) → W1 정확성·안전·데이터무결성 → W2 하드닝·중복제거·크로스엔진 → W3 대형 구조.
   웨이브 순서는 뒤집지 않는다(정확성이 구조 리팩터를 앞선다). 상세는 [`02-roadmap.md`](02-roadmap.md).
2. **안정적 슬라이스 ID.** 리뷰 로드맵의 `S0`–`S48` ID 공간을 **승계**한다. 팀·핸드오프·PROGRESS가 ID로 참조하며
   **ID의 의미는 변하지 않는다.** 재범위·병합·삭제가 필요하면 ID를 재사용하지 말고 [`01-review-assessment.md`](01-review-assessment.md)에
   divergence로 명시한다.
3. **팀 소유권.** 각 슬라이스는 기존 팀 charter(`.claude/agents/novetest-<team>-team.md`)의 소유 경계에 배정된다.
   실행은 기존 다중 에이전트 하네스(worktree → handoff → Main Branch 병합 → Manual Test 검증)를 그대로 쓴다.
4. **살아있는 진행 보드.** 계획 문서(00–02, waves/)는 **승인 후 얼어붙는다.** 진행 상태는 오직
   [`PROGRESS.md`](PROGRESS.md) 한 파일에서만 변한다. 이 분리가 긴 기간에도 계획을 읽을 수 있게 하는 핵심 장치다.
5. **agent-comms 연결.** 이 프로그램의 in-flight 조율(task/handoff/verification/finding)은 기존 `agent-comms/`
   프로토콜을 그대로 쓴다. 이 `design/refactoring/`는 **전략 계획층**이고, `agent-comms/`는 **실행 조율층**이다.
6. **추적성.** 계획 슬라이스 → 리뷰 finding ID → 소스 `file:line`. 리뷰의 근거를 **복제하지 않고 링크**한다.
   finding의 증거는 언제나 [`../reviews/2026-07-04-codebase-review/findings/`](../reviews/2026-07-04-codebase-review/findings/)에 있다.

---

## 4. 판단 원칙 (finding을 수락/기각/재배치할 때의 렌즈)

프로젝트 전역 원칙(`CLAUDE.md`: wrap-not-replace, Simplicity First, Surgical Changes, karpathy-guidelines)에
더해, 이 프로그램은 다음 리팩터-특화 원칙으로 판단한다.

1. **정확성이 구조를 앞선다.** "사용자/AI가 틀린 결과를 신뢰"하거나 "운영 중 hang/OOM/데이터 부분상태"를
   만드는 국소·저비용 수정을 대형 구조 리팩터보다 먼저 한다.
2. **릴리스가 롤백 앵커다.** 검증된 HEAD를 소스 무변경으로 먼저 출하(v0.1.3)한 뒤 리팩터에 착수한다.
   `v0.1.3` 태그는 이후 회귀의 고정 롤백 기준점이 되어 리팩터 자체를 안전하게 만든다.
3. **레지스트리가 아니라 dict 하우스 패턴 + divergence-guard.** 중복 봉쇄는 import-부작용 등록(레지스트리)이
   아니라 **모듈 상수 dict + set-equality 가드 테스트**(`_READINESS_PROBES`가 이미 증명한 패턴)로 한다.
   등록 순서를 암묵 우선순위로 삼는 설계는 2026-07-03 결정이 '설계로 사멸'시킨 two-priority-lists 버그를 부활시킨다.
4. **문서는 후퇴시킨다, 코드를 허구에 맞추지 않는다.** stale 설계 서술은 실물(함수형 adapter + if-elif 디스패치 +
   SSoT dict)에 맞게 다시 쓴다. 미구현 추상화를 "구현해서 문서를 참으로 만드는" 방향은 스코프 밖.
5. **리뷰를 그대로 믿지 않는다.** 모든 load-bearing 주장(H 5건, 부채 a–e, 리뷰 스스로 `uncertain`으로 표기한
   항목, 미해결 MEM-05)은 원 코드에 대한 독립 적대 재검증을 거친다. 재검증 결과가 리뷰와 다르면 **재검증을 따른다.**
6. **침묵 축소 금지.** 스코프를 줄이거나(top-N, 샘플링, no-retry) drop한 것이 있으면 계획에 loud하게 명시한다.
   "다 다뤘다"처럼 읽히는 침묵 누락을 만들지 않는다.

---

## 5. 완료 정의(DoD)와 완료 이후의 모습

### 5.1 프로그램 Definition of Done

- W0(릴리스): `v0.1.3` 태그 출하 완료, 태그가 롤백 앵커로 확보됨.
- W1–W3: 각 웨이브의 exit criteria(각 `waves/*.md` 참조)를 충족하고, 그 시점 HEAD가
  전체 스위트 green + mypy clean + CI 매트릭스 통과.
- 수락된 각 finding이 (수정 커밋 | 문서-후퇴 커밋 | 명시적 defer/reject 기록) 중 하나로 **종결 상태**를 가짐
  — [`PROGRESS.md`](PROGRESS.md)에서 미결 슬라이스 0.

### 5.2 완료 이후의 코드베이스 모습 (end-state vision)

프로그램이 끝났을 때 Nove Test는 다음을 만족한다.

- **조용한 오답이 없다.** `novetest run .`이 스위트를 통째로 건너뛰고 초록을 내는 부류(go 축소, JUnit stale
  리포트, junit/xunit failure_proximity 침묵 0건, Cobertura 멀티클래스 소실)가 전부 제거되어, 초록은 초록을 뜻한다.
- **크로스-엔진·크로스-호스트 계약이 일관된다.** exit/error 코드, fail-like outcome 어휘, 상대경로 POSIX 정규화,
  reason 어휘(kebab-case)가 6엔진·모든 동사에서 단일 SSoT를 가진다. AI 소비자가 엔진마다 규칙을 다시 배우지 않는다.
- **운영이 견고하다.** 타임아웃이 프로세스 트리를 종료하고(고아·hang·OOM 없음), 손상 레코드가 히스토리 전체를
  무너뜨리지 않으며, 툼스톤·pin backfill이 원자적이다.
- **드리프트가 재발하지 못한다.** 관측된 클론(escape 문자셋, failing-outcome, formula 이름, 프로젝터 4쌍,
  run_id 해석)이 dict SSoT + divergence-guard로 고정되어, 다음 엔진/동사 추가 시 재복제가 컴파일/테스트 타임에 막힌다.
- **지도가 실물과 일치한다.** `foundations.md §5` 등 stale 설계 서술이 실제 파일 레이아웃·디스패치와 일치하고,
  신규 기여자가 문서를 코드보다 신뢰해도 잘못된 사이트를 편집하지 않는다.
- **구조 부채가 seam으로 정리된다.** 1973줄 `cli/app.py`가 관심사별 seam으로 분해되고, 파생-엔진 합성이
  엔진경계 가드 SSoT를 거친다 — 단, 이 대형 구조 작업은 정확성·seam 슬라이스가 선행된 뒤에만.

**변하지 않는 것:** 엔벨로프 v1 wire 계약(동결), 6엔진 매트릭스, "wrap engines" 경계, 각 엔진의 네이티브 실행 스코프.
이 프로그램은 **행동을 고치고 계약을 일관시키되 계약 자체를 바꾸지 않는다.**

---

## 6. 리스크와 가드레일

- **Windows 회귀 잠복면.** Linux pre-merge 게이트가 구조적으로 못 잡는 계열(직전 2회 post-merge 검출:
  `886dc09`, `fdf44d7`). W1의 경로/런처 슬라이스는 Windows CI 레인 부재를 전제로 S44(엔진 e2e equip)와 조율한다.
- **D6(2026-07-03 최신 결정) 표면.** ORC-09/14/25, XCT-04는 구현 완결성이 가장 유동적 — 슬라이스 착수 시 재검증 필수.
- **대형 리팩터의 churn.** S47(app.py 분해)/S48(import DAG)은 seam 추출 슬라이스가 선행돼야 이중작업·충돌을 피한다.
- **릴리스에 버그 수정 끼워넣기 유혹.** 금지. W1 버그는 v0.1.2에도 이미 존재하므로 v0.1.3가 상태를 악화시키지 않는다.
  릴리스는 소스 무변경(W0), 수정은 그 뒤.
