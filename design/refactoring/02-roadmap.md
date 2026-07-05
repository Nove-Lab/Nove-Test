# 02 · 로드맵 (웨이브·슬라이스·우선순위)

작성일: 2026-07-05 · 소유: PM(+CEO 승인) · 전제: [`01-review-assessment.md`](01-review-assessment.md)의 판정

이 로드맵은 리뷰가 확정하고 우리가 재검증·교정한 finding을 **웨이브 → 슬라이스**로 조직한다.
슬라이스 ID(`S0`–`S48`)는 리뷰 로드맵 ID 공간을 승계하며 의미가 고정된다([`00-charter.md`](00-charter.md) §3).
개별 슬라이스의 **범위·완료후모습·exit criteria**는 `waves/*.md`에, 각 finding의 **근거(file:line)**는
[`../reviews/2026-07-04-codebase-review/findings/`](../reviews/2026-07-04-codebase-review/findings/)에 있다.
살아있는 상태는 [`PROGRESS.md`](PROGRESS.md).

---

## 1. 웨이브 개요와 완료후 모습

| 웨이브 | 테마 | 슬라이스 수 | 완료 시 무엇이 참이 되나 |
|---|---|---|---|
| **W0 릴리스** | v0.1.3 소스무변경 컷 | 1 (S0) | 검증된 HEAD가 태그로 출하되고, `v0.1.3`가 이후 리팩터의 고정 롤백 앵커가 된다. |
| **W1 정확성·안전·데이터무결성** | "초록은 초록을 뜻한다" | 10 (S1–S10) | 조용한 오답(go 축소·JUnit stale·junit/xunit 침묵·Cobertura 소실)과 운영 위험(트리 미종료·툼스톤 부분상태·삭제run head 오보)이 제거된다. |
| **W2 하드닝·중복제거·크로스엔진** | 계약 일관 + 재발 봉쇄 | 36 (S11–S46) | exit/error·outcome 어휘·경로 정규화·reason이 단일 SSoT를 갖고, 관측된 클론이 divergence-guard로 고정된다. 문서가 실물과 일치한다. |
| **W3 대형 구조** | seam 분해 | 2 (S47–S48) | 1973줄 app.py가 관심사별 seam으로, 파생-엔진 합성이 엔진경계 SSoT로 정리된다(선행 seam 슬라이스 뒤). |

**순서 불변:** 정확성(W1)이 구조(W3)를 앞선다. 릴리스(W0)가 W1을 앞선다. 이 순서는 뒤집지 않는다.

---

## 2. 우선순위 순서와 근거

우선순위 = (1) 데이터/사용자-가시 정확성 손상, (2) blast radius, (3) 부채 판정 정합, (4) 비용대비 회수.

| 순위 | 슬라이스 | 근거 | 재검증 반영 |
|---|---|---|---|
| 0 | **S0** | 검증 지점을 롤백 앵커로 먼저 고정. 소스 무변경이라 Windows 회귀면 0 추가. | C4: 1파일(pyproject)+릴리스노트. |
| 1 | **S1, S2** | Top-10 H. `run .` 축소 + JUnit stale = 사용자가 틀린 답 신뢰. 국소 수정. | C3: S2 Gradle 절반 경험적 확인. |
| 2 | **S6, S7** | Top-10 H(coverage/localization). 멀티클래스 소실 + junit/xunit 침묵. 파생-사실 오염. | S7은 no-coverage 폴백 한정(ANA-02 caveat) — 여전히 기본 실행 경로. |
| 3 | **S8** | Top-10 M×3. errored 오분류 + 이중접두 코드 = AI가 exit/ok 오독. wire 계약 위반. | handlers/test.py:83-85에도 동일 — 단일 헬퍼로 수렴. |
| 4 | **S3** | H. 타임아웃 시 트리 미종료 → hang/OOM/고아. 단일 지점. | C7: 트리kill + gather grace 타임아웃 **둘 다**. |
| 5 | **S9, S10** | 데이터 무결성/오보. 툼스톤 부분상태 + 삭제run head. S 크기, 즉시. | — |
| 6 | **S4, S5** | 제로-수집(부채 c) + Windows 주입/배치(RCE·Windows). | C1: S4는 go/junit/xunit 침묵초록 가시화 + 3갈래 문서화(수렴 아님). S5는 Windows 레인 부재로 S44 조율. |
| 7 | **S25, S24** | 크로스컷 SSoT 조기화 + 문서 후퇴. 이후 엔진 슬라이스의 drift를 컴파일/테스트 타임에 차단. | C6: S25는 SSoT/재발방지 cleanup 프레이밍(현행 활성버그 아님). |
| 8 | **S11–S23, S26–S46** | 하드닝·중복제거·per-엔진 정확성. 국소 M/L. | C5: S26(ORC-12) gate-on-PM. C8: S19(ORC-09) 트리거 정밀화. C2: **MEM-05를 Memory 트랙에 신규 배정**. |
| 9 | **S44** | equip 갭(carry-forward #4). multi/infra 별 트랙. | — |
| 10 | **S47, S48** | 대형 구조. seam 추출 슬라이스 선행 필수. | — |

**정확성이 리팩터를 앞선다.** W1 10개는 전부 "틀린 결과 신뢰" 또는 "운영 중 hang/OOM/부분상태" 계열의
국소·저비용·즉시회수. 대형 리팩터(S47/S48)는 회수가 지연되고 churn 위험이 커 최후미.
**중복제거는 중간대**: 그 자체는 버그 아니나 이미 드리프트가 관측된 클론(escape 문자셋 3/11/16,
fail-outcome `"error"` 유입, formula 이름, 프로젝터 4쌍)을 SSoT+guard로 고정해 다음 엔진/동사 추가 때 재복제를 예방.

---

## 3. 마스터 슬라이스 표

크기: `S`=반나절↓ / `1c`=한 사이클 / `1-2c` / `multi`=다중(계획 별도). 배치: W0/W1/W2/W3.
"교정"은 [`01-review-assessment.md`](01-review-assessment.md) §3의 C1–C8, MEM-05 신규 배정.

| ID | 이름 | 팀 | 크기 | 선행 | 배치 | 주요 finding | 교정 |
|---|---|---|---|---|---|---|---|
| S0 | v0.1.3 릴리스 컷 | release+PM | S | — | W0 | 부채 e | **C4** |
| S1 | 네이티브 타깃 변환 & argv 위생 | run | 1c | — | W1 | RUN-01(H), RUN-22 | |
| S2 | 실행별 리포트 격리 & readiness 정합 | run | 1c | — | W1 | RUN-02(H), RUN-14 | **C3** |
| S3 | 서브프로세스 수명주기 하드닝 | run | 1c | — | W1 | RUN-15/MOD-01(H), RUN-27/MOD-02 | **C7** |
| S4 | 제로-수집 경고(warning+passed) | run | S | — | W1 | RUN-12 [부채 c] | **C1** |
| S5 | Windows 런처 안전 & 메타문자 방어 | run | 1c | S44 조율 | W1 | RUN-09, RUN-10 | |
| S6 | Cobertura 멀티-클래스 병합 | coverage | 1c | — | W1 | ANA-01(H) | |
| S7 | failure_proximity junit/xunit + divergence 가드 | localization | 1c | S25(권장) | W1 | ANA-02(H) | |
| S8 | 실행 exit/에러코드 계약 수정 | orchestration | 1c | — | W1 | ORC-03, ORC-04, ORC-23 | |
| S9 | 툼스톤 원자성 | memory | S | — | W1 | MEM-02 | |
| S10 | status latest & 파생-플래그 신선도 | orchestration | S | — | W1 | ORC-16, ORC-26 | |
| S11 | jest node_id workspace-relative POSIX | run | 1c | — | W2 | RUN-13 | |
| S12 | cargo/dotnet 커버리지·타임아웃 정확성 | run | 1c | — | W2 | RUN-05/08/18/20 | |
| S13 | run/adapters 공용 헬퍼 추출 | run | 1-2c | S1,S2,S12 | W2 | RUN-04/06/17/23 | |
| S14 | pytest 인터프리터/결정론 env 계약 | run | 1c | S24 | W2 | RUN-11, RUN-24 | |
| S15 | Run 경고 taxonomy·죽은코드·예외포착 | run | S | — | W2 | RUN-07/19/21/26 | |
| S16 | 레거시 engine=None 제거 + dict 디스패치 | run | S-M | S24 | W2 | RUN-25 [부채 b,d] + docstring 부수 | |
| S17 | 실행 예외 매핑 dedup | orchestration | 1c | S8 | W2 | ORC-02, ORC-21 | |
| S18 | run_id 해석 + Memory 단건 조회 API | orch+memory | 1c | — | W2 | ORC-05 | |
| S19 | D6 읽기-동사 seam & 원자적 backfill | orch+memory | 1c+ | — | W2 | ORC-09, XCT-04, ORC-14, ORC-25 | **C8** |
| S20 | 타깃식 정규화(파일시스템 독립) | orchestration | S | — | W2 | ORC-10 | |
| S21 | 엔벨로프 Windows 안전 상대경로 | orchestration | S | — | W2 | ORC-15 | |
| S22 | CLI→워크플로: 로컬라이제이션 캐시/unlink | orchestration | 1c | — | W2 | ORC-07, XCT-02 | |
| S23 | CLI→워크플로: compare 뷰 + 프로젝터 통합 | orchestration | 1c | — | W2 | ORC-06, ORC-08 | |
| S24 | 문서 후퇴 & 구조 동기화 | PM(+팀) | S-M | — | W2(조기) | XCT-01, RUN-03/16, ORC-17/XCT-11 [부채 a] | |
| S25 | fail-like outcome SSoT | orch(+models) | 1c | — | W2(조기) | XCT-05 | **C6** |
| S26 | 추천 합성 정확성 | orchestration | 1c | — | W2 | ORC-12, ORC-13, ORC-18 | **C5** |
| S27 | reset/init 엔벨로프 & 계약 docstring | orchestration | S | — | W2 | ORC-20, ORC-24 | |
| S28 | CLI 죽은코드 & 스냅샷 가드 | orchestration | S | — | W2 | ORC-19/22/27 | |
| S29 | Localization reason 어휘 + formula SSoT | localization | 1c | wire-freeze 전 | W2 | ANA-09, ANA-19 | |
| S30 | SBFL 점수 정확성 | localization | 1c | — | W2 | ANA-10, ANA-11, ANA-20 | |
| S31 | per-test 경로 견고성 | localization | 1c | — | W2 | ANA-07, ANA-08, ANA-18 | |
| S32 | symbol resolver 캐시 & extent | localization | S | — | W2 | ANA-21, ANA-22 | |
| S33 | Coverage 요약 dedup + num_statements | coverage | 1c | — | W2 | ANA-06, ANA-04 | |
| S34 | JaCoCo 소스셋 경로 + 존재 필터 | coverage | 1c | — | W2 | ANA-05 | |
| S35 | Coverage 가용성/문서 & 죽은 reason | coverage | S | — | W2 | ANA-16, ANA-17 | |
| S36 | Regression 결정성 & divergence | regression | 1c | — | W2 | ANA-25, ANA-26, XCT-07 | |
| S37 | Regression 캐시 견고성 & 중복 node_id | regression | 1c | — | W2 | ANA-23, ANA-24 | |
| S38 | Replay readiness & rerun 계수 | replay | 1c | — | W2 | ANA-13, ANA-14 + docstring 부수 | |
| S39 | Replay 불가용 채널 정책 | replay(+doc) | 1c | S24/정책 | W2 | ANA-03 | |
| S40 | Replay 유닛 미러 | replay | 1c | — | W2 | ANA-12 | |
| S41 | Memory 동시성 & 위생 (+MEM-05) | memory | 1c | — | W2 | MEM-01/03/04, **MEM-05** | **C2** |
| S42 | 저장소 손상 exit-5 전파 | memory+orch | 1c | — | W2 | XCT-03 | |
| S43 | Memory 공개 표면 & 레이어 경계 | memory(+cross) | 1c | S24/SSoT | W2 | XCT-12, XCT-13 | |
| S44 | 엔진 e2e equip 갭 & skip→fail 게이트 | release(+Main) | multi | infra | W2/W3 트랙 | XCT-08/09/10/14, ANA-15 | |
| S45 | models/utils 위생 | models-utils | S | S3 | W2 | MOD-03/04/05 | |
| S46 | workspaces 등록-사이트 완결성 테스트 | orchestration | 1c | — | W2 | ORC-11 | |
| S47 | cli/app.py 분해 | orchestration | multi | S8,S17,S22,S23 | W3 | ORC-01 | |
| S48 | 파생-엔진 import DAG / 주입 합성 | cross | multi | S25 + 가드 안정 | W3 | XCT-06 | |

> MEM-05는 리뷰가 미스케줄로 남긴 것을 재검증(M 확정)으로 **S41에 신규 편입**했다(C2).

---

## 4. Quick wins (반나절 이하, 선행 의존 없음)

팀 여유 사이클에 독립 cherry-pick 가능(단, **전부 v0.1.3 이후** — 부채 e):
**S4·S9·S10·S15·S20·S21·S27·S28·S32·S35·S45** (슬라이스 통째 quick).
개별 finding 단위 quick-win 목록은 리뷰 로드맵 §5 참조(그대로 유효).

---

## 5. 지금 하면 손해인 것 (착수 금지 / 선행조건 대기)

[`00-charter.md`](00-charter.md) §2.2(비목표)와 정합:

1. **어댑터 데코레이터 레지스트리 도입** — 부채 a/d 반대편. dict 하우스 패턴(S16)만, 레지스트리 금지. 문서는 후퇴(S24).
2. **`normalizer.parse_artifacts` 대규모 adapter-이관** — 904줄+6.5k LOC 재편 대비 회수 미정. S16은 engine.py 사다리 한정.
3. **S47(app.py 분해)을 릴리스 전/seam 전에** — Windows 회귀면 확대 + S8/S17/S22/S23 seam과 이중작업. 릴리스 후 + seam 후만.
4. **S48(import DAG)을 엔진경계 가드 안정 전에** — S25 SSoT 선행 필수.
5. **`workspaces` 동사 본체** — 제품 결정 미스케줄. 완결성 테스트(S46)만.
6. **v1 wire rename**(`test_id`→`node_id`) — 스키마 동결. docstring 명시(S45)만.
7. **v0.1.3에 W1 버그수정 끼워넣기** — 금지. 릴리스는 소스 무변경(S0), 수정은 그 뒤 W1.

---

## 6. 릴리스 전/후 배치 요약

- **릴리스 전:** `S0`만(소스 무변경).
- **릴리스 직후 W1(10):** S1–S10. `v0.1.3` 태그를 롤백 앵커로 확보한 상태에서 착수. 일부를 v0.1.3.1 fast-follow로
  승격 가능(팀 판단, 릴리스 비게이트).
- **W2(36):** S11–S46. S24/S25를 앞머리 조기 배치.
- **W3(2):** S47·S48 — 선행 seam/가드 슬라이스 이후.

부채 정합: (a)=S24(문서만), (b)+(d)=S16, (c)=S4(**C1 교정**), (e)=S0(**C4 교정**). 어떤 배치도 판정 a~e와 모순되지 않는다.
