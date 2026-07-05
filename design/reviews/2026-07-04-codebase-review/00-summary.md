# Nove Test — 코드베이스 아키텍처/코드 리뷰: 경영 요약

작성일: 2026-07-05 · 대상: v0.1.2 태그 이후 `main` HEAD(`d689417`, `v0.1.2..HEAD` 61커밋) · src ~25.3k LOC
동반 문서: 슬라이스·웨이브·릴리스 배치는 `roadmap.md`(이 파일과 같은 디렉터리), 개별 근거(file:line)는 `findings/` 하위 도메인 파일.

---

## 1. 경영 요약

**전체 건강도: 출하 가능(shippable). 릴리스를 막는 치명 결함은 없다.** 베이스라인은 리뷰 착수 전 전체 테스트 스위트 green + mypy clean으로 확인되었고(리뷰 프로토콜상 재실행하지 않음), HEAD는 CI 10/10(dispatch run 28675082033) + Manual Test 통과 + agent-comms 5개 채널 전부 공백의 **검증된 최청정 지점**이다(2026-07-04 program-close). 확정된 어떤 High도 "정지 중 데이터 파손" 또는 "릴리스 차단" 부류가 아니며, Top-10의 모든 H는 v0.1.2에도 이미 존재하는 잠복 결함이다. 즉 v0.1.3는 상태를 악화시키지 않는다.

리뷰의 지배적 위험 패턴은 크래시가 아니라 **"조용한 오답(silent wrongness)"** — 엔진이 자신 있게 틀린 초록/결과를 내고 사람 또는 AI 에이전트가 그것을 신뢰하게 만드는 계열이다. 이것이 "we wrap engines, never replace them" 제품에서 가장 비싼 실패다.

**최대 위험 4개(전부 Top-10 H):**

1. **RUN-01 — `novetest run .`의 무증상 축소.** go 어댑터가 디렉터리/nodeid 타깃을 변환 없이 넘겨, 하위 패키지에 테스트가 있는 전형적 Go 모듈에서 루트 패키지만 비재귀 실행 → 전체 스위트를 건너뛰고 `status=passed`로 보고(가짜 초록). 대칭으로 `./subdir`·`pkg::Test`는 가짜 빌드실패가 된다. cargo/dotnet은 `directory` 가드로 회피하나 go에는 그 가드가 없다.
2. **RUN-02 — JUnit stale 리포트.** JUnit 어댑터만 영속 워크스페이스 리포트 디렉터리를 정리 없이 glob → 이전/필터 실행의 stale `TEST-*.xml`을 현재 실행 결과로 보고. 이번에 돌지 않은 유령 테스트가 RunRecord를 오염시키고 Regression/Localization의 baseline·재가중을 유령 위에 세운다.
3. **ANA-02 — junit·xunit failure_proximity 이미 침묵 파손.** 기본 실행(`--coverage` 미지정)에서 junit/xunit 실패 run의 `novetest localization`이 `resolve_failure_text`의 엔진 튜플 누락으로 **항상 0건**을 낸다(시뮬레이션1이 예측한 드리프트가 실현된 증거). 크래시가 아니라 침묵 퇴화라 pre-merge 게이트가 못 잡는다.
4. **ANA-01 — Cobertura 멀티-클래스 커버리지 소실.** 같은 filename의 다중 `<class>`가 병합 없이 서로 덮어써, 멀티타입 `.cs`(C# 관용) 커버리지가 조용히 사라진다 → `percent_covered`/`num_statements` 과소보고, 이를 소비하는 coverage/regression/localization이 잘못된 커버리지를 사용.

(추가로, 타임아웃 시 프로세스 트리 미종료로 손자 테스트 프로세스·JVM·testhost가 고아로 잔존하고 무한 hang/OOM 표면을 만드는 **RUN-15/MOD-01**(H, 동일 결함 교차수록)이 운영 신뢰성 계열의 최상위 위험이다.)

**권고 방향:**

- **릴리스 선행(부채 e).** 검증된 HEAD를 소스 무변경으로 v0.1.3 먼저 출하한다(`S0` — 2파일 버전 범프 + 릴리스노트, 실측 ~30분). 대형 리팩터나 버그 수정을 61커밋 위에 먼저 얹으면 Linux pre-merge가 구조적으로 못 잡는 Windows 회귀 표면(직전 2회 post-merge 검출)을 키우고 bisect를 오염시킨다. v0.1.3 태그는 이후 리팩터의 고정 롤백 기준점이 된다.
- **릴리스 직후 W1(정확성·안전·데이터 무결성 10개).** 네이티브 타깃 변환·argv 위생(S1), 실행별 리포트 격리(S2), 서브프로세스 수명주기 하드닝(S3), 제로-수집 경고(S4=부채 c), Windows 런처 안전(S5), Cobertura 병합(S6), failure_proximity junit/xunit(S7), 실행 exit/에러코드 계약(S8), 툼스톤 원자성(S9), status latest 신선도(S10).
- **문서 후퇴는 하되 레지스트리는 구현하지 않는다(부채 a/d).** 남은 중복 사다리는 `_READINESS_PROBES`가 이미 증명한 dict 하우스 패턴 + divergence-guard로 접는다(S16). 대형 구조 리팩터(app.py 1973줄 분해 S47, import DAG 재설계 S48)는 seam 추출 슬라이스 뒤 W3로 미룬다.

정량: 확정 findings 103건(도메인 헤더 직접집계 기준 **H 5 / M ~54 / L ~44**; 로드맵 요약은 서브프로세스 결함 RUN-15/MOD-01 교차수록으로 H 6으로 집계), 미확정 2, 검증 기각 3(§5 참조).

---

## 2. 전 저장소 심각도 Top-10

| 순위 | ID | 심각도 | 제목 | 한 줄 시나리오 | 크기 |
|---|---|---|---|---|---|
| 1 | [RUN-01](findings/run.md#run-01) | H | go 어댑터가 디렉터리/nodeid 타깃을 변환 없이 넘겨 `novetest run .`이 루트 패키지만 실행(무증상 축소), `./subdir`·`pkg::Test`는 가짜 빌드실패 | 하위 패키지 Go 모듈에서 `run .` → 루트만 비재귀 실행 → 스위트 통째 건너뛰고 `passed` 보고 | 1-cycle |
| 2 | [RUN-02](findings/run.md#run-02) | H | JUnit 어댑터만 영속 리포트 디렉터리를 정리 없이 glob → 이전/필터 실행의 stale `TEST-*.xml`을 현재 결과로 보고 | 전체 실행 후 `run BarTest`(필터) → 나머지 49개 stale XML을 현재 run 결과로 집계·baseline 오염 | 1-cycle |
| 3 | [RUN-12](findings/run.md#run-12) | M | 제로-수집(0 테스트) 처리가 엔진별 3갈래: pytest=errored / go·junit·xunit·jest=passed / cargo=예외 | 아무 것도 수집 안 되는 타깃을 실행 시 같은 사건이 엔진에 따라 성공/에러/도구실패로 제각기 보고 | 1-cycle |
| 4 | [ANA-02](findings/analysis-engines.md#ana-02) | H | junit·xunit가 failure_proximity localization에서 이미 침묵 파손(예측 드리프트 실현) | 기본 실행의 junit/xunit 실패 run에 `localization` → `resolve_failure_text` 엔진 누락으로 항상 0건 finding | 1-cycle |
| 5 | [ORC-04](findings/orchestration.md#orc-04) | M | run/test가 `status==errored` 런을 exit1·ok=False(도구 실패)로 오분류 — 계약상 사용자 결과인데 Nove Test 실패로 표기 | pytest 수집 에러로 errored된 스위트가 정상 정규화·영속됐는데도 envelope는 exit1·ok=False | quick-win(≤반나절) |
| 6 | [ORC-03](findings/orchestration.md#orc-03) | M | run/test의 엔진-미준비 에러코드가 이중접두 `engine-engine-missing`으로 방출 — 계약 토큰과 불일치 | 계약대로 `errors[0].code=="engine-missing"`로 분기하는 에이전트가 절대 매치 못 해 '알 수 없는 실패'로 오분류 | quick-win |
| 7 | [ANA-01](findings/analysis-engines.md#ana-01) | H | Cobertura: 같은 filename의 다중 `<class>`가 서로 덮어써 멀티타입 `.cs` 커버리지가 조용히 소실 | 한 `.cs`에 두 타입 → `filename="Ops.cs"` `<class>` 2개가 충돌, 앞 타입 라인 통째 누락·과소보고 | 1-cycle |
| 8 | [RUN-13](findings/run.md#run-13) | M | jest node_id가 절대 파일경로를 내장 — 크로스-호스트 regression 매칭 붕괴 및 Windows 역슬래시 유입 | 로컬 baseline vs CI candidate에서 절대경로 접두가 달라져 union-walk가 전 테스트를 removed+added로 오판 | 1-cycle |
| 9 | [RUN-14](findings/run.md#run-14) | M | dotnet readiness의 test-csproj 필터가 어댑터와 발산('test'만 vs tests/test/specs/spec) — ready 후 다른 csproj 실행 | `Z.Test`(xunit)+`A.Specs`(xunit 없음) 레이아웃에서 readiness=ready인데 어댑터가 A.Specs 실행 → 0 테스트/실패 | quick-win(≤반나절) |
| 10 | [ORC-16](findings/orchestration.md#orc-16) | M | status가 tombstone된 최신 run을 `latest_run_reference`로 노출 — 삭제한 run을 현재 head로 오보 | `run --coverage` → `memory delete <R>` → `status`가 tombstone된 R을 그대로 latest로 선택 | quick-win(≤반나절) |

> 링크 규약: `findings/<domain>.md#<id>`(이 파일과 같은 디렉터리의 `findings/` 하위 파일 상대참조). 앵커는 각 finding 문서의 `<a id="run-01"></a>` 규약을 따른다. **Top-10 링크 10건을 전수 재클릭 검증했다: `run.md`(RUN-01/02/12/13/14) · `analysis-engines.md`(ANA-01·ANA-02) · `orchestration.md`(ORC-03/04/16) 모두 대상 파일의 `<a id>` 앵커 도달까지 실측 확인 — 10/10 도달.** Top-10의 순위·심각도·제목·시나리오는 확정 입력 그대로다. 전체 산출물 인벤토리는 §6 참조.

---

## 3. 알려진 부채 5건 판정 (a~e) — 검증자 이견 없음(전 5건 contested=false)

### 부채 a — 어댑터 데코레이터 레지스트리 (문서 vs 실물)
**판정: `foundations.md §5`의 decorator-registry/NativeAdapter Protocol 서술을 현행 실물(함수형 adapter 6개 `*_adapter.py` + `engine_selector._ENGINE_MARKER_TABLE` SSoT + `readiness._READINESS_PROBES` dict)에 맞게 재작성하되, 레지스트리는 구현하지 않는다.**
근거: 7번째 엔진 추가 시 편집해야 하는 엔진-지식 사이트는 7곳인데 레지스트리는 그중 `engine.py` if-사다리 **1곳만** 기계적으로 제거한다(나머지 6곳은 잔존하거나 904줄 normalizer + ~6.5k LOC adapter 재편 조건부). `foundations.md:475`의 "Adding a seventh ecosystem is one PR, one file"은 어느 설계에서도 성립 못 하는 과장이다. 코드는 이미 절반이 레지스트리(readiness는 pair-키 dict + divergence guard `test_engine_selector.py:202-213`)이며, 등록 순서를 암묵 우선순위로 삼으면 2026-07-03 결정이 '설계로 사멸'시킨 two-priority-lists 버그가 부활한다. 7번째 엔진은 미스케줄이므로 지금 구현은 Simplicity First 위반. (구조 표의 `base.py`/`pytest_.py` 등 파일명도 실물과 광범위 불일치.)
크기: 문서 후퇴 단독 **S**(반나절); 조건부 dict 슬라이스 동반 **M**(1-2일). → 로드맵 `S24`.

### 부채 b — 레거시 `execute(engine=None)` 분기
**판정: 프로덕션 호출자 2곳(`run.py:115`, `test.py:196`)이 모두 명시 `(ecosystem, engine)` pair를 전달하고 `resolve_execution_engine`에 None 반환 경로가 없으므로, `engine=None` 분기는 도달 불가능한 죽은 코드이며 지금 제거 가능하다.**
근거: 전제 태스크(anchored-init-and-verb-resolution)는 이미 main 병합 완료(`WORKLOG.md:34`가 "execute now ALWAYS receives an explicit pair" 기록, :36에 핸드오프 통지). `select_native_engine`은 동반 삭제 가능하나 `assess_engine_readiness`는 `replay/engine.py:71`이 소비하므로 **존치**(과잉삭제 금지). 설계 문서 2곳 + 테스트 3파일 동기화 필요.
크기: **S**(반나절, src ~50-70줄 + 테스트). → 로드맵 `S16`(부채 d와 배칭).

### 부채 c — 제로-수집(0 테스트)이 `passed`로 새는 문제
**판정: 제로-수집이 `status:passed`/`ok:true`/`exit0`로 새는 것은 scratchpad 사본에서 저장소 무오염으로 실측 재현된 실재 결함이며, 권고 수정은 `engine.py` 단일 사이트에 `zero-tests-collected` `AdapterWarning`을 추가하는 것(warning + passed 유지)이다.**
근거: 동일 사건이 엔진별 3갈래 — pytest(exit4 경로)·go·junit·xunit는 `passed`, cargo·jest는 typed error. 신규 status 도입(옵션①)은 status 값-도메인 파괴적 변경(M, decisions 절차 필요), 에러 승격(옵션②)은 go의 "no test files"·junit의 의도적 clean-empty-run과 충돌해 "wrap engines, never replace" 위반(M~L). 권고 ③은 envelope 스키마·exit code·persisted record 불변(2026-06-06 warning 채널 재사용), CLI 배선 0.
크기: **S**. → 로드맵 `S4`.

### 부채 d — `_invoke_adapter` 6-branch if-사다리
**판정: 사다리 교체는 단독으로도 정당하되 데코레이터 레지스트리가 아니라 `_READINESS_PROBES` 하우스 패턴(모듈 상수 dict + divergence-guard 테스트)으로 가야 하며, 부채 b의 legacy 분기 제거와 한 슬라이스로 배칭한다.**
근거: 6개 `run_*` entrypoint 시그니처가 균일(`test_target, *, artifact_dir, timeout, collect_coverage`)해 dict화가 순수 기계적(45줄→~15줄). 실질 이득은 가독성이 아니라 **정적 봉쇄** — 7번째 엔진 어댑터 누락을 현재의 런타임 `EngineNotSupportedError` 대신 readiness와 동일한 set-equality guard로 컴파일/테스트 타임에 차단. coverage/localization의 엔진명 스위치는 타 팀 소유·의미론 상이(포맷별 파서 선택/로그 해석)라 메가테이블 통합은 비권장. 레지스트리는 import 부작용 등록·정적 추적성 악화로 폐쇄 6종 세트에서 이득 없음.
크기: **S**(engine.py 단독; normalizer.py 동반 시 diff 100줄 미만). → 로드맵 `S16`.

### 부채 e — 릴리스 타이밍 vs 대규모 리팩터
**판정: 릴리스 전 최소 세트는 `pyproject.toml` 버전 범프(0.1.2→0.1.3) + `uv.lock` 재동기(2파일 커밋) + PM 작성 `design/release-notes/v0.1.3.md` + CEO 런북 4단계뿐이고, 대규모 리팩터는 반드시 v0.1.3 릴리스 후에 착수한다.**
근거: v0.1.2 이후 61커밋(comms 43/docs 5/소스 13)에 사용자 가시 기능 3종 + anchored-pin D1–D7 전체가 이미 미출하 상태로 실려 있고, HEAD는 CI 10/10 + Manual Test 통과 + comms 5채널 공백의 검증 지점, 릴리스 비용 실측 ~30분. 리팩터를 먼저 얹으면 (a) Linux pre-merge가 구조적으로 못 잡는 Windows 회귀 표면 확대(직전 2회 post-merge 검출), (b) 행동/구조 변화 혼재로 사용자 리포트 bisect 오염. v0.1.3 태그는 이후 리팩터의 고정 롤백 기준점이 된다. program-close 팔로업 5건은 전부 "NOT scheduled·비차단".
크기: 릴리스 최소 세트 **S**(반나절, 릴리스노트가 유일한 실질 작업); 후속 리팩터는 대형·다중 슬라이스(범위 밖). → 로드맵 `S0`(유일한 릴리스-전 슬라이스).

---

## 4. 읽는 순서 안내 (독자별 진입점)

- **경영진 / PM(우선순위·릴리스 판단):** 이 `00-summary.md` §1 → `roadmap.md`(웨이브·슬라이스 배치, §1 릴리스 타이밍) → 부채 e / `S0`.
- **Run 팀:** `findings/run.md`(27건, H2) + `findings/models-utils.md`(MOD-01/02 = RUN-15/27의 미러) → 로드맵 `S1`–`S5`, `S11`–`S16`.
- **Coverage / Localization / Regression / Replay(분석엔진) 팀:** `findings/analysis-engines.md`(26건, H2) → 로드맵 `S6`, `S7`, `S12`, `S29`–`S40`.
- **Orchestration 팀:** `findings/orchestration.md`(27건) + `findings/cross-cutting.md`의 관련 항목(XCT-02/04/05/06) → 로드맵 `S8`, `S10`, `S17`–`S28`, `S46`–`S47`.
- **Memory 팀:** `findings/memory.md`(확정 4 + 미확정 1) + `findings/cross-cutting.md` XCT-03/12/13 → 로드맵 `S9`, `S18`–`S19`, `S41`–`S43`.
- **아키텍트 / 문서 소유(PM):** `findings/cross-cutting.md`(14건, 팀 경계 항목만) + 부채 a·d → 로드맵 `S24`, `S25`, `S48`.
- **신규 기여자:** 이 요약 → `roadmap.md` → 관심 도메인 finding. **주의:** `foundations.md §5`의 decorator-registry 서술은 stale(부채 a) — 실제 디스패치는 `engine.py:149-204`의 if-elif다. 문서를 코드보다 신뢰하지 말 것.

---

## 5. 검증 방법론 (투명성)

- **멀티에이전트 시니어 리뷰:** 도메인별 조사 에이전트(run / analysis-engines / orchestration / memory / models-utils / cross-cutting) + 알려진 부채 판정 에이전트 + 로드맵·요약 종합 에이전트가 병렬로 조사하고 상호 교차참조했다.
- **finding별 적대 검증(adversarial verification):** 모든 주장은 조사 세션에서 `Read`로 직접 연 repo 상대경로 `file:line` 인용을 요구했다. grep 히트만으로는 증거로 인정하지 않았고, 완전히 확인 못 한 항목은 `confidence:"uncertain"`으로 표기했다(예: RUN-10 Windows `.cmd` exec 실패 모드, dotnet zero-match 시 VSTest native exit code — 미장비 호스트라 코드 경로만 확인). 부채 c는 scratchpad 사본에서 **저장소 무오염으로 실측 재현**(`native_exit_code:4`/`total:0`/`status:passed`/`ok:true`/exit 0).
- **통계(기각 포함):** 원시 102건 + 갭 스윕 보강 → 검증 대상 113건 → **확정 103 / 미확정 2 / 검증 기각 3 / 검증기 도구오류로 유실 5**(103+2+3+5=113으로 정합). 미확정 2건 = `MEM-05`([H→미확정] 손상/미래스키마 레코드가 history 스캔을 붕괴), `MOD-06`(frozen dataclass `__hash__` TypeError). 검증 기각 3건은 재현 불가로 드롭. **유실 5건**은 적대 검증 단계에서 StructuredOutput 재시도 상한(5회)을 초과해 판정을 받지 못한 항목으로, 미검증 상태라 "확정 근거만 수록" 규율에 따라 본 보고서에서 제외했다(침묵 누락 방지 차원에서 수치로 명시).
- **확정 도메인 분포:** run 27(H2/M13/L12), orchestration 27, analysis-engines 26(H2/M13/L11), cross-cutting 14(M9/L5), models-utils 5(H1/M1/L3), memory 4(확정; M2/L2, 별도 미확정 1) — 6개 도메인 파일 전부 앵커·헤더 정합을 실측 검증했다(`orchestration.md` 포함, orc-01..orc-27 유니크·연속 확인). H는 서브프로세스 수명주기 결함이 RUN-15(M)/MOD-01(H)로 교차수록되어 도메인 헤더 합산과 전역 distinct 카운트에 미세 차이가 있다(직접집계 H 5, 로드맵 요약 H 6).
- **베이스라인:** 리뷰 착수 전 전체 테스트 스위트 green + mypy clean 확인됨(리뷰 프로토콜상 재실행 금지). HEAD는 CI 10/10 + Manual Test 통과.
- **stale 문서 경계 규율:** `foundations.md §318/§475`의 decorator-registry 서술은 미구현이며 실제 디스패치는 `engine.py:149-204`의 if-elif다(XCT-01 / 부채 a). 리뷰는 문서를 코드보다 신뢰하지 않았다.

---

## 6. 산출물 인벤토리 (최종 상태)

이 리뷰의 산출물은 전부 `design/reviews/2026-07-04-codebase-review/` 아래에 정착했다(총 8개 md):

| 파일 | 내용 | 확정 / 미확정 |
|---|---|---|
| `00-summary.md` | 이 경영 요약 · Top-10 · 부채 a~e 판정 | — |
| `roadmap.md` | 슬라이스·웨이브·릴리스 배치 | — |
| `findings/run.md` | Run 엔진 + 6개 네이티브 어댑터 | 27 / 0 |
| `findings/orchestration.md` | Orchestration + CLI | 27 / 0 |
| `findings/analysis-engines.md` | Coverage · Regression · Localization · Replay | 26 / 0 |
| `findings/memory.md` | Memory 엔진 + Project Store | 4 / 1 |
| `findings/models-utils.md` | Models + Utils | 5 / 1 |
| `findings/cross-cutting.md` | 팀 경계를 넘는 항목만 | 14 / 0 |

모든 finding 앵커는 도메인 파일 내에서 유니크하며(충돌 없음), 이 요약의 Top-10 링크(10건)와 `roadmap.md`의 finding 링크(103건)는 전수 앵커 도달을 실측 검증했다. 합계: 확정 103 / 미확정 2.
