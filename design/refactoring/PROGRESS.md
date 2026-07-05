# PROGRESS — 리팩터링 프로그램 상태 보드

**이 파일이 프로그램에서 유일하게 상시 갱신되는 문서다.** 계획 문서(`00`–`02`, `waves/`)는 승인 후 얼어붙는다.
슬라이스 상태가 바뀔 때마다 여기만 고친다. 계획 자체를 고치지 말 것(고정 유지가 장기 가독성의 핵심).

최종 갱신: 2026-07-05 · 계획 상태: **초안 승인 대기(CEO)**

---

## 상태 범례

| 상태 | 의미 |
|---|---|
| `☐ not-started` | 미착수 |
| `◐ in-progress` | 팀 worktree 작업 중 |
| `⊕ handed-off` | 핸드오프 제출, Main Branch 병합 대기 |
| `⇢ merged` | main 병합 완료, Manual Test 검증 대기 |
| `✓ verified` | Manual Test 통과 — 종결 |
| `⏸ blocked` | 선행/외부 대기 |
| `⤳ deferred` | 후행 웨이브/후속 스코프로 이동(사유 명시) |
| `PM?` | gate-on-PM — 착수 전 PM/스펙 확인 필요 |

---

## 프로그램 단계

| 웨이브 | 상태 | 비고 |
|---|---|---|
| **W0 릴리스(v0.1.3)** | ☐ not-started | 계획 승인 후 최우선. 소스 무변경. |
| **W1 정확성·안전** | ☐ not-started | W0 태그 확보 후 착수. |
| **W2 하드닝·중복제거** | ☐ not-started | W1 이후. S24/S25 조기. |
| **W3 대형 구조** | ☐ not-started | W1·W2 seam/가드 이후. |

---

## W0 — 릴리스

| ID | 상태 | 슬라이스 | 팀 | 비고 |
|---|---|---|---|---|
| S0 | ☐ | v0.1.3 릴리스 컷 | release+PM | C4: pyproject 1파일 + 릴리스노트(**uv.lock 없음**). |

## W1 — 정확성·안전·데이터무결성

| ID | 상태 | 슬라이스 | 팀 | 비고 |
|---|---|---|---|---|
| S1 | ☐ | 네이티브 타깃 변환 & argv 위생 | run | RUN-01(H) |
| S2 | ☐ | 실행별 리포트 격리 & readiness 정합 | run | RUN-02(H). **C3: Gradle 경험적 확인.** |
| S3 | ☐ | 서브프로세스 수명주기 하드닝 | run | MOD-01(H). **C7: 트리kill+grace 둘 다.** |
| S4 | ☐ | 제로-수집 경고 [부채 c] | run | **C1: go/junit/xunit만; jest/cargo는 이미 typed-error.** |
| S5 | ☐ | Windows 런처 안전 & 메타문자 방어 | run | RUN-09/10. S44 조율. |
| S6 | ☐ | Cobertura 멀티-클래스 병합 | coverage | ANA-01(H) |
| S7 | ☐ | failure_proximity junit/xunit + 가드 | localization | ANA-02(H). S25 권장 선행. |
| S8 | ☐ | 실행 exit/에러코드 계약 수정 | orchestration | ORC-03/04/23. handlers/test.py도. |
| S9 | ☐ | 툼스톤 원자성 | memory | MEM-02 |
| S10 | ☐ | status latest & 파생-플래그 신선도 | orchestration | ORC-16/26 |

## W2 — 하드닝·중복제거·크로스엔진 (S11–S46)

| ID | 상태 | 슬라이스 | 팀 | 비고 |
|---|---|---|---|---|
| S11 | ☐ | jest node_id workspace-relative POSIX | run | RUN-13 |
| S12 | ☐ | cargo/dotnet 커버리지·타임아웃 정확성 | run | RUN-05/08/18/20 |
| S13 | ☐ | run/adapters 공용 헬퍼 추출 | run | 선행 S1,S2,S12 |
| S14 | ☐ | pytest 인터프리터/결정론 env 계약 | run | 선행 S24 |
| S15 | ☐ | Run 경고 taxonomy·죽은코드·예외포착 | run | RUN-07/19/21/26 |
| S16 | ☐ | engine=None 제거 + dict 디스패치 [부채 b,d] | run | 선행 S24. 레지스트리 금지. docstring 부수 정정. |
| S17 | ☐ | 실행 예외 매핑 dedup | orchestration | 선행 S8 |
| S18 | ☐ | run_id 해석 + Memory 단건 조회 API | orch+memory | ORC-05 |
| S19 | ☐ | D6 읽기-동사 seam & 원자적 backfill | orch+memory | **C8. D6 표면 — 착수 시 재검증 필수.** |
| S20 | ☐ | 타깃식 정규화(파일시스템 독립) | orchestration | ORC-10 |
| S21 | ☐ | 엔벨로프 Windows 안전 상대경로 | orchestration | ORC-15 |
| S22 | ☐ | CLI→워크플로: 로컬라이제이션 캐시/unlink | orchestration | ORC-07, XCT-02 |
| S23 | ☐ | CLI→워크플로: compare 뷰 + 프로젝터 통합 | orchestration | ORC-06/08 |
| S24 | ☐ | 문서 후퇴 & 구조 동기화 [부채 a] | PM(+팀) | **조기.** 레지스트리 금지. **PM 소유 배정 필요.** |
| S25 | ☐ | fail-like outcome SSoT | orch(+models) | **조기. C6: SSoT/재발방지 cleanup.** |
| S26 | ☐ `PM?` | 추천 합성 정확성 | orchestration | **C5: ORC-12 gate-on-PM.** ORC-13 accept. |
| S27 | ☐ | reset/init 엔벨로프 & 계약 docstring | orchestration | ORC-20/24 |
| S28 | ☐ | CLI 죽은코드 & 스냅샷 가드 | orchestration | ORC-19/22/27 |
| S29 | ☐ | Localization reason 어휘 + formula SSoT | localization | 선행 wire-freeze 전 |
| S30 | ☐ | SBFL 점수 정확성 | localization | ANA-10/11/20 |
| S31 | ☐ | per-test 경로 견고성 | localization | ANA-07/08/18 |
| S32 | ☐ | symbol resolver 캐시 & extent | localization | ANA-21/22 |
| S33 | ☐ | Coverage 요약 dedup + num_statements | coverage | ANA-06/04 |
| S34 | ☐ | JaCoCo 소스셋 경로 + 존재 필터 | coverage | ANA-05 |
| S35 | ☐ | Coverage 가용성/문서 & 죽은 reason | coverage | ANA-16/17 |
| S36 | ☐ | Regression 결정성 & divergence | regression | ANA-25/26, XCT-07 |
| S37 | ☐ | Regression 캐시 견고성 & 중복 node_id | regression | ANA-23/24 |
| S38 | ☐ | Replay readiness & rerun 계수 | replay | ANA-13/14. docstring 부수 정정. |
| S39 | ☐ | Replay 불가용 채널 정책 | replay(+doc) | ANA-03. 선행 S24/정책. |
| S40 | ☐ | Replay 유닛 미러 | replay | ANA-12 |
| S41 | ☐ | Memory 동시성 & 위생 (+MEM-05) | memory | **C2: MEM-05(M) 신규 편입. 손상 파일 경로 warning.** |
| S42 | ☐ | 저장소 손상 exit-5 전파 | memory+orch | XCT-03 |
| S43 | ☐ | Memory 공개 표면 & 레이어 경계 | memory(+cross) | 선행 S24/SSoT |
| S44 | ☐ | 엔진 e2e equip 갭 & skip→fail 게이트 | release(+Main) | multi/infra 별 트랙. S5 조율. |
| S45 | ☐ | models/utils 위생 | models-utils | 선행 S3 |
| S46 | ☐ | workspaces 등록-사이트 완결성 테스트 | orchestration | ORC-11. 동사 본체는 스코프 밖. |

## W3 — 대형 구조

| ID | 상태 | 슬라이스 | 팀 | 비고 |
|---|---|---|---|---|
| S47 | ☐ | cli/app.py 분해 | orchestration | 선행 S8,S17,S22,S23 |
| S48 | ☐ | 파생-엔진 import DAG / 주입 합성 | cross | 선행 S25 + 가드 안정 |

---

## 갱신 방법

1. 슬라이스 상태가 바뀌면 위 표의 상태 셀만 수정(범례 기호 사용).
2. 웨이브 전체가 완료되면 "프로그램 단계" 표의 해당 행을 갱신.
3. 슬라이스를 defer/reject하면 상태를 `⤳`로 바꾸고 비고에 **사유**를 남긴다(침묵 축소 금지 — charter §4 원칙 6).
4. **계획 문서(`00`–`02`, `waves/`)는 여기서 건드리지 않는다.** 스코프 자체가 바뀌면 그건 계획 개정이므로 별도
   결정(agent-comms/decisions/)으로 다루고 이 보드에 반영.
