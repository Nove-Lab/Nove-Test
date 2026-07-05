---
from: novetest-pm-team
to: all
type: decision
status: active
created: 2026-07-05
slug: refactoring-program-launch
related:
  - design/refactoring/README.md
  - design/reviews/2026-07-04-codebase-review/00-summary.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Decision: 코드베이스 리팩터링 프로그램 착수

2026-07-04 전문가 리뷰(`design/reviews/2026-07-04-codebase-review/`, 확정 103건)를
입력으로 한 **리팩터링 프로그램을 착수한다.** 이 문서는 프로그램의 조율-계층 진입점(anchor)이다 —
새 세션(특히 PM)이 pre-flight에서 이걸 보고 "지금 트랙 = 리팩터링"임을 바로 파악하도록 남긴다.

## 진입점 (여기부터 읽어라)

**`design/refactoring/README.md`** 가 전 계획의 네비게이션 허브이며 독자별 진입 순서를 안내한다.
- `00-charter.md` — 왜/스코프/원칙/DoD/완료후모습
- `01-review-assessment.md` — 리뷰 **비판적 평가**(수락/기각/8개 교정 C1–C8)
- `02-roadmap.md` — 웨이브 + 슬라이스 마스터 표(S0–S48) + 우선순위
- `waves/wave-1~3.md` — 슬라이스별 범위·완료후모습·exit criteria
- `PROGRESS.md` — **살아있는 상태 보드(프로그램에서 유일하게 상시 갱신되는 파일)**

## 어떻게 결정됐나

리뷰를 그대로 수락하지 않았다. load-bearing 주장 30개(H 5 + 부채 a~e + uncertain 항목 + 미해결
MEM-05 + Top-10 M)를 18개 적대 에이전트가 원 소스 대비 재검증 → **30/30 CONFIRMED**, 기각 0,
**8개 교정(C1–C8)** + MEM-05 H→M 확정·신규 배정. 상세는 `01-review-assessment.md`.

## 바인딩 제약 (실행 시 준수)

1. **웨이브 순서 고정:** W0 릴리스(v0.1.3, 소스무변경) → W1 정확성(S1–S10) → W2 하드닝(S11–S46) → W3 구조(S47–S48). 뒤집지 않는다.
2. **첫 업무 = W0** (부채 e: 릴리스 선행, `v0.1.3` 태그를 롤백 앵커로). 릴리스 최소 세트 = `pyproject.toml` 1파일 범프(**`uv.lock` 없음**) + `design/release-notes/v0.1.3.md` + CEO 런북.
3. **어댑터 데코레이터 레지스트리 구현 금지**(부채 a/d) — dict 하우스 패턴 + divergence-guard.
4. **슬라이스 ID(S0–S48)는 의미 고정.** 재범위·병합·삭제는 `01-review-assessment.md`에 divergence로 명시.
5. **계획 문서는 얼린다.** 진행 상태는 `PROGRESS.md`에서만 변경.
6. **gate-on-PM 항목:** S26(ORC-12) — 착수 전 "결함 vs 의도 스펙" 확인 필요.

## 현재 상태 / 다음 액션

- 계획은 **draft PR #2**(브랜치 `worktree-refactor-plan`)에 있음. **PR #2 merge 시 리뷰+계획+이 결정이
  함께 `main`에 안착**하고 그때부터 어느 환경이든 fresh clone으로 바로 파악 가능.
- 실행 착수(W0)는 CEO 최종 go 후. 착수 시 이 결정을 참조해 `agent-comms/tasks/`로 S0을 배정.
