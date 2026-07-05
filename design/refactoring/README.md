# Nove Test — 코드베이스 리팩터링 프로그램

이 디렉터리는 2026-07-04 전문가 리뷰를 입력으로 한 **리팩터링 프로그램의 전략 계획층**이다.
리뷰(입력, 불변 스냅샷)는 [`../reviews/2026-07-04-codebase-review/`](../reviews/2026-07-04-codebase-review/)에 있고,
여기(계획 + 우리의 판단 + 진행)는 그 리뷰를 **비판적으로 소비**한다.

> **핵심 불변식:** 계획 문서(`00`–`02`, `waves/`)는 승인 후 **얼어붙는다**. 상태는 오직
> [`PROGRESS.md`](PROGRESS.md) 한 파일에서만 변한다. 긴 리팩터 기간에도 계획을 안정적으로 읽으려면
> "무엇을 하기로 했나"(계획)와 "지금 어디까지 됐나"(진행)를 절대 섞지 말 것.

---

## 문서 지도

| 파일 | 역할 | 변경성 |
|---|---|---|
| [`00-charter.md`](00-charter.md) | 왜/스코프/원칙/운영모델/DoD/end-state vision | 프로그램 종료까지 고정 |
| [`01-review-assessment.md`](01-review-assessment.md) | **리뷰 비판적 평가** — finding별 수락/도전/기각/재배치 + 독립 재검증 판정 | 평가 완료 후 고정 |
| [`02-roadmap.md`](02-roadmap.md) | 웨이브·슬라이스 마스터 표, 우선순위·근거, 의존 그래프, 릴리스 타이밍 | 승인 후 고정 |
| [`waves/wave-1-correctness.md`](waves/wave-1-correctness.md) | W1 슬라이스별 범위 + 완료 후 모습 + exit criteria | 승인 후 고정 |
| [`waves/wave-2-hardening.md`](waves/wave-2-hardening.md) | W2 상동 | 승인 후 고정 |
| [`waves/wave-3-structural.md`](waves/wave-3-structural.md) | W3 상동 | 승인 후 고정 |
| [`PROGRESS.md`](PROGRESS.md) | **살아있는 상태 보드** — 슬라이스별 상태(미착수/진행/병합/검증) | 상시 갱신 |

리뷰 원문(증거·file:line)은 복제하지 않고 링크한다: 각 finding의 근거는
[`findings/<domain>.md#<id>`](../reviews/2026-07-04-codebase-review/findings/)에 있다.

---

## 독자별 진입점 (reading order)

- **CEO / PM (우선순위·릴리스 판단):**
  `00-charter.md` → `01-review-assessment.md` §요약 → `02-roadmap.md` → `PROGRESS.md`.
- **슬라이스를 실행하는 팀:**
  `02-roadmap.md`에서 자기 슬라이스 ID 확인 → 해당 `waves/*.md`의 슬라이스 상세(범위·end-state·exit) →
  리뷰 `findings/<domain>.md`의 근거 → `PROGRESS.md`에 상태 기록.
- **Main Branch / Manual Test:**
  병합/검증 대상 슬라이스의 `waves/*.md` exit criteria → 기존 `agent-comms/` 핸드오프·검증 프로토콜.
- **신규 기여자:**
  `00-charter.md` → `02-roadmap.md`. **주의:** `foundations.md §5`의 어댑터 레지스트리 서술은 stale이다
  (부채 a). 실제 디스패치는 `run/engine.py`의 if-elif다. 문서를 코드보다 신뢰하지 말 것.

---

## 상태 한눈에

프로그램 단계와 각 슬라이스의 실시간 상태는 **[`PROGRESS.md`](PROGRESS.md)** 가 유일한 정본이다.
이 README와 계획 문서는 상태를 담지 않는다(고정 유지를 위해).

---

## 이 프로그램과 기존 조율 하네스의 관계

- 이 `design/refactoring/` = **전략 계획층**(무엇을·왜·어떤 순서로).
- `agent-comms/{tasks,handoffs,verifications,findings}/` = **실행 조율층**(누가·언제·병합·검증). 기존 프로토콜 그대로.
- `WORKLOG.md`, `agent-comms/history/` = **불변 회고**. 이 프로그램은 이들을 읽되 백패치하지 않는다.
