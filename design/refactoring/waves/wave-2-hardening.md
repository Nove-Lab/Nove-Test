# Wave 2 — 하드닝·중복제거·크로스엔진 정확성

배치: W1 이후 · 슬라이스 36개(S11–S46) · 전제: [`../02-roadmap.md`](../02-roadmap.md)

W2는 **계약을 일관시키고 재발을 봉쇄**한다. W1이 "틀린 결과"를 고쳤다면 W2는 (1) per-엔진 정확성의 남은 M/L,
(2) 이미 드리프트가 관측된 클론을 SSoT+divergence-guard로 고정, (3) 문서-코드 지도 정합을 다룬다.

**per-슬라이스 목표(범위)는 리뷰 로드맵의 각 슬라이스 항목에 이미 상술돼 있다** —
[리뷰 roadmap.md §3 웨이브 W2](../../reviews/2026-07-04-codebase-review/roadmap.md)를 정본으로 참조한다.
이 파일은 W2를 **트랙으로 묶어** 완료후모습·exit criteria·우리의 교정만 얹는다(먼 작업을 지금 재상술하면 stale해짐).

> **조기 배치:** S24(문서 후퇴)·S25(fail-like SSoT)를 W2 앞머리에 둔다. 이후 여러 엔진 슬라이스의 전제(정확한
> 지도 + 단일 outcome 정본)를 세워 병렬 진행 시 충돌을 줄인다.

---

## 트랙 A — 크로스컷 SSoT & 문서 (조기)

- **슬라이스:** S24(문서 후퇴 [부채 a]), S25(fail-like outcome SSoT).
- **완료후모습:** `foundations.md §5` 등 stale 설계 서술이 실물(함수형 adapter + engine.py if-elif + `_READINESS_PROBES`/
  `_ENGINE_MARKER_TABLE` SSoT)과 일치하고, "fail-like outcome" 정본이 `models/`에 단일 존재해 6+ 소비자가 import한다.
- **교정 C6(S25):** `fact_bundle.py:284`의 `"error"` 드리프트는 실재하나 **현행 행동 피해는 이중 게이팅되어 도달
  불가**(어떤 어댑터도 `"error"` 단수 미방출; dotnet이 `error→errored` 정규화). 따라서 S25는 **활성버그 수정이 아니라
  재발방지 SSoT cleanup**으로 실행하고, `"error"` 포함 정책을 그 단일 지점에서 결정.
- **주의(부채 a):** **레지스트리 구현 금지**(charter §4 원칙 3). 문서만 후퇴. S24는 program-close carry-forward #5의
  '미추적 파킹' 해소 — **PM 명시 소유 배정 필요**(무배정 시 재방치).
- **exit criteria:** 정본==각 소비자 집합을 pin하는 divergence-guard 테스트(S25). 신규 기여자가 §5를 읽고 실제 디스패치
  사이트(engine.py)를 찾을 수 있음(S24).

## 트랙 B — Run 하드닝 & 중복제거

- **슬라이스:** S11(jest node_id POSIX), S12(cargo/dotnet 커버리지·타임아웃), S13(공용 헬퍼 추출), S14(pytest env 계약),
  S15(경고 taxonomy·죽은코드), S16(engine=None 제거 + dict 디스패치 [부채 b,d]).
- **완료후모습:** jest node_id가 workspace-relative POSIX(크로스-호스트 regression 복원), 실패-로그 상대경로·escape
  문자셋·subprocess 스켈레톤이 단일 헬퍼로 수렴(escape 3/11/16 발산 소멸), `_invoke_adapter`가 dict 디스패치로 7번째
  엔진 누락을 컴파일/테스트 타임에 차단.
- **교정(S16):** dict 하우스 패턴만(레지스트리 금지). 레거시 분기 제거 시 `engine` 비-옵셔널화 + **단위테스트 갱신**
  동반(프로덕션 도달 불가지만 단위테스트가 진입). `assess_engine_readiness` **존치**(replay 소비). 부수:
  `execute_with_engine_context` docstring(engine.py:116-119, readiness 게이트 허위 주장) 함께 정정.
- **exit criteria:** jest 크로스-호스트 회귀 테스트, 공용 헬퍼 단일 출처 테스트, 어댑터 dict divergence 가드 테스트.

## 트랙 C — Orchestration 하드닝 & 경계

- **슬라이스:** S17(예외 매핑 dedup), S18(run_id 조회 API), S19(D6 읽기 seam & 원자 backfill), S20(타깃식 정규화),
  S21(엔벨로프 POSIX), S22(localization 캐시 이관), S23(compare 뷰 + 프로젝터 통합), S26(추천 합성), S27(reset/init
  엔벨로프), S28(CLI 죽은코드), S46(workspaces 완결성 테스트).
- **완료후모습:** 읽기 동사가 모호/pre-pin 스토어에서 하드실패하지 않고, D6 backfill이 원자적이며, run_id 해석·엔진
  프로젝터·예외 매핑이 단일 출처를 갖고, 엔벨로프 상대경로가 POSIX로 정규화된다.
- **교정 C8(S19):** ORC-09 트리거는 정확히 **legacy pre-pin AND 모호 마커**(단일마커 pre-pin·markerless는 exit2
  아님). **D6는 2026-07-03 최신 결정 표면 — 착수 시 구현 완결성 재검증 필수**(ORC-14/25, XCT-04 포함).
- **교정 C5(S26):** ORC-12(compound swallow 파일단위)는 **gate-on-PM** — `compound_resolution` 선두 docstring이
  파일단위를 의도로 서술하므로, swallow 키를 `(file, primary_line)`로 좁히기 전 brief §1/PM 확인. ORC-13(citation
  round-trip)은 accept(NFR-ORCH-002 위반 실재).
- **exit criteria:** 읽기 동사 seam 분리 테스트, run_id 단건 조회 API 테스트, 프로젝터 단일 출처 테스트, workspaces
  등록 완결성 테스트(신규 동사 본체는 스코프 밖 — 테스트만).

## 트랙 D — 분석 엔진 정확성 (Coverage/Localization/Regression/Replay)

- **슬라이스:** S29(reason 어휘·formula SSoT), S30(SBFL 점수), S31(per-test 견고성), S32(symbol resolver), S33(coverage
  요약 dedup), S34(JaCoCo 경로), S35(coverage 가용성/문서), S36(regression 결정성), S37(regression 캐시), S38(replay
  readiness·rerun 계수), S39(replay 불가용 채널), S40(replay 유닛 미러).
- **완료후모습:** SBFL이 dstar2 랭킹 반전(ANA-10)과 spectra outcome 오분류(ANA-11)를 고치고, replay가 기록 엔진을
  정확히 게이트하며 폐기 rerun을 은닉하지 않고, coverage 요약·percent 관례가 단일 구현, reason 어휘가 kebab-case로 통일,
  regression 정렬이 run_id 2차 tiebreak로 결정적이 된다.
- **주의:** ANA-10은 비기본 formula(dstar2) 한정, ANA-11은 기본 ochiai 영향이나 유계 희석 — 둘 다 accept(M). S38 착수 시
  `execute_with_engine_context` docstring 부수 정정(트랙 B S16과 조율).
- **exit criteria:** SBFL 점수 정확성 단위 테스트(denom==0 & ef>0 → 최대 의심; passing 정의 SSoT), replay 유닛 미러
  (S40), regression 결정성 tiebreak 테스트.

## 트랙 E — Memory 무결성 & 레이어 경계

- **슬라이스:** S41(동시성 & 위생 **+ MEM-05**), S42(저장소 손상 exit-5), S43(공개 표면 & 레이어 경계), S45(models/utils
  위생).
- **완료후모습:** run+reset 경합으로 run이 조용히 유실되지 않고, 손상 record.json이 히스토리 전체를 무너뜨리지 않으며
  (**MEM-05, C2**), 손상이 read 경로에서 exit-5로 정확 전파되고, 파생 엔진이 Memory 공개 표면만 바인딩한다.
- **교정 C2(S41):** **MEM-05(리뷰 미스케줄)를 M으로 확정해 신규 편입.** `_iter_all_records`/`_read_record`에 per-record
  격리(파싱 실패 스킵 + warning, targeted 경로는 loud 유지). warning에 **손상 파일 경로 포함**(운영자가 grep 없이 찾도록).
- **exit criteria:** 손상 레코드 1건이 memory list/show(타 run)/regression/localization를 죽이지 않고 격리됨을 보이는
  테스트, exit-5 전파 테스트, 공개 경로 import lint/체크.

## 트랙 F — CI/Equip 갭 (별 트랙, multi/infra)

- **슬라이스:** S44(엔진 e2e equip 갭 & skip→fail 게이트 & perf NFR).
- **완료후모습:** go/cargo/dotnet/java 셀(최소 1 OS)이 CI에 추가되거나 장착 셀에서 skip→fail 승격 가드가 서서, 조용한
  skip 퇴화가 가시화되고 perf NFR이 required-but-generous로 시행된다.
- **주의:** carry-forward #4(equip 갭 3사이클 연속)의 근본 해소 트랙. CI 매트릭스 변경이라 별 트랙 진행. **S5(Windows
  junit 레인)과 조율.**
- **exit criteria:** skip 카운트 상·하한 assert, 장착 셀에서 실 e2e 상시 실행, perf 하드 실패선.

---

## W2 exit criteria (웨이브 전체)

- S11–S46 각 슬라이스가 (수정 커밋 | 문서-후퇴 | defer/reject 기록)로 종결.
- 관측된 클론 클래스(escape 문자셋, fail-like outcome, formula 이름, 프로젝터 4쌍, run_id 해석)가 divergence-guard로 고정.
- 그 시점 HEAD가 전체 스위트 green + mypy clean + CI 매트릭스 통과.
- S24/S25 조기 완료로 이후 슬라이스의 지도·SSoT 전제가 확보됨.
