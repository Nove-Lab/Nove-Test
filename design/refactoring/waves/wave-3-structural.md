# Wave 3 — 대형 구조 리팩터

배치: W1·W2의 seam/가드 슬라이스 **이후** · 슬라이스 2개(S47–S48) · 전제: [`../02-roadmap.md`](../02-roadmap.md)

W3은 회수가 '미래 유지비 절감'으로 지연되고 churn 위험이 큰 대형 구조 작업이다. **선행 seam 추출이 끝난 뒤에만**
착수한다 — 먼저 하면 이중작업·머지 충돌·Windows 회귀면 확대를 부른다. 각 슬라이스는 착수 시점에 별도 실행 계획을
세운다(multi-cycle).

---

## S47 · cli/app.py 분해 — orchestration · multi

- **findings:** [ORC-01](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-01)(M, multi-cycle)
- **선행(필수):** S8(exit 계약), S17(예외 매핑), S22(localization 이관), S23(compare 뷰 + 프로젝터 통합). 이들이 이미
  여러 seam을 추출하므로 그 뒤에 착수해야 churn·충돌 최소.
- **범위:** 1973줄 `app.py`를 절단선대로 분해 — argv 진입점군→`cli/entrypoint.py`, per-engine 투영군→`handlers/`,
  localization 캐시정책→orchestration 워크플로, init/reset 리퓨절 빌더→`handlers/onboarding.py`.
- **완료후모습:** 잔여 `app.py`는 `@command` 정의 + 얇은 seam ~700줄대. 한 동사 배선 수정의 blast radius가 파일 전체가
  아니라 해당 handler로 국한된다. transport와 orchestration 관심사가 분리된다.
- **exit criteria:** 분해 후 전체 스위트·스냅샷 green, 각 handler 단위 테스트, app.py 라인수 목표 달성. wire 계약 불변
  (엔벨로프 byte-stability 유지).

## S48 · 파생-엔진 import DAG / orchestration 주입 합성 — cross · multi

- **findings:** [XCT-06](../../reviews/2026-07-04-codebase-review/findings/cross-cutting.md#xct-06)(M, multi-cycle)
- **선행(필수):** S25(fail-like outcome SSoT) + 엔진경계 가드 안정. 가드가 자리잡기 전에 하면 이동 중 회귀 검출이 약해짐
  (엔진경계 가드는 이미 coverage/localization/orchestration 3곳 복제 우회 이력).
- **범위:** cross-engine fact 합성(coverage delta 임베드, regression prior 재가중)을 orchestration이 주입하거나 공유
  selector 하나로 엔진경계 가드를 SSoT화. 소비자는 각 엔진 공개 `__init__` 심볼만 바인딩(내부 서브모듈 직접참조 제거).
- **완료후모습:** 파생 엔진(regression→coverage, localization→coverage+regression)의 직접 import DAG가 정리되고,
  cross-engine 합성이 mediating 계층을 거쳐 D5 엔진경계 가드가 단일 출처를 갖는다. coverage.compare 시그니처 변경이
  두 소비자에 무통제 파급되지 않는다.
- **exit criteria:** 엔진경계 가드 SSoT 테스트, 소비자가 내부 서브모듈을 직접 참조하지 않음(lint/체크), 혼합엔진
  스토어에서 무의미 delta 재발 방지 테스트.

---

## W3 exit criteria (웨이브 전체)

- S47·S48 완료 시 HEAD가 전체 스위트 green + mypy clean + 스냅샷 byte-stability 유지 + CI 매트릭스 통과.
- 대형 파일/DAG 지표 개선(app.py 라인수, import DAG 깊이)이 착수 시 세운 목표를 충족.
- **불변 확인:** 엔벨로프 v1 wire 계약·6엔진 매트릭스·"wrap engines" 경계가 그대로 유지됨(구조만 변경, 계약 무변경).

---

## 프로그램 종료

W3까지 종결되면 [`00-charter.md`](00-charter.md) §5.2의 end-state vision이 충족된다. 프로그램 Definition of Done
(charter §5.1)의 마지막 체크 — [`PROGRESS.md`](PROGRESS.md)의 미결 슬라이스 0 — 을 확인하고, PM이
`agent-comms/history/`에 프로그램 클로즈 회고를 남긴다(이 계획 문서군은 종료 후에도 **불변 참조**로 보존).
