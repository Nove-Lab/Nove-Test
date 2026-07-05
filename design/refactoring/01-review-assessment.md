# 01 · 리뷰 비판적 평가 (수락/도전/기각 판정)

작성일: 2026-07-05 · 소유: PM(+CEO 승인) · 근거: 독립 적대 재검증(아래 §1)

이 문서는 [`00-charter.md`](00-charter.md) §4 원칙 5("리뷰를 그대로 믿지 않는다")를 집행한 결과다.
2026-07-04 리뷰를 **그대로 수락하지 않고**, load-bearing 주장을 원 소스에 대해 독립적으로 재검증한 뒤
finding별 수락 여부를 판정한다. 로드맵/우선순위는 이 판정을 전제로 [`02-roadmap.md`](02-roadmap.md)가 조직한다.

---

## 1. 재검증 방법론

- **무엇을 재검증했나:** 리뷰의 지지대가 되는 30개 주장 — H 5건(RUN-01/02, ANA-01/02, MOD-01+RUN-15),
  부채 판정 a~e, 리뷰 스스로 `confidence: uncertain`으로 표기했거나 미해결로 남긴 항목(ORC-09/12/13/14, XCT-04,
  MEM-05), 그리고 Top-10을 떠받치는 M 클러스터(ORC-03/04/16/23, RUN-12/13/14, ANA-10/11/13/14, XCT-05/07).
- **어떻게:** 18개 독립 에이전트가 **적대적으로**(주장을 refute하려는 자세로) 인용된 `file:line`을 직접 열어
  검증했다. grep 히트가 아니라 실제 코드 경로 확인을 요구했고, 리뷰가 놓친 가드/도달성/과장/라인드리프트를 탐색했다.
- **결과 요약:** **30건 전부 코드 수준에서 CONFIRMED**(finding 자체가 refute된 건 0). 그러나 심각도·범위·수정방향에서
  **8건의 교정(calibration correction)**이 나왔다(§3). 이는 리뷰가 부실해서가 아니라, 우리가 실제로 손대기 전에
  범위를 정확히 잡기 위한 것이다.

**종합 판정: 리뷰의 실질을 (거의) 전면 수락한다.** 단, 아래 §3의 교정을 반영해서. 이 수락은 리뷰를 신뢰해서가
아니라, 독립 재검증이 리뷰의 근거를 실제로 재현·확인했기 때문에 얻어진 것이다.

---

## 2. 수락 처분 범례

| 처분 | 의미 |
|---|---|
| **accept** | 리뷰의 finding·심각도·수정방향을 그대로 수락. |
| **accept-with-changes** | finding은 유효하나 심각도/범위/수정방향을 교정해서 수락(§3). |
| **gate-on-PM** | finding은 유효하나 "결함 vs 의도된 스펙"이 모호 — 착수 전 PM/스펙 확인 필요. |
| **defer** | 유효하나 선행조건 미충족 또는 스코프 밖 — 후행 웨이브/후속 스코프로 미룸. |
| **reject** | 재검증이 주장을 무효화 — 조치하지 않음. (이번 재검증에서 **해당 없음**.) |

---

## 3. 교정 목록 (리뷰와 우리가 갈리는 지점) — 이 프로그램의 핵심 비판적 산출물

리뷰를 rubber-stamp하지 않았음을 보여주는 8개 지점이다. 각 슬라이스는 이 교정을 반영해 실행한다.

| # | 대상 | 리뷰의 서술 | 재검증이 밝힌 것 | 처분·반영 |
|---|---|---|---|---|
| C1 | **RUN-12 / 부채 c** (제로-수집) | 제로-수집 3갈래: pytest=errored / **go·junit·xunit·jest=passed** / cargo=예외. 수정: engine.py **단일 사이트** warning으로 "수렴". | **jest는 passed가 아니라 typed-error**(cargo와 동류; report 미생성 시 `AdapterInvocationError` raise, `--passWithNoTests` 없음). 실제 3갈래 = **passed{go,junit,xunit} / errored{pytest exit5} / typed-error{cargo,jest}**. 게다가 engine.py 단일 warning 사이트는 **RunRecord를 생산하는 엔진만** 볼 수 있는데 cargo·jest는 RunRecord 생성 전에 raise하므로 그 사이트가 닿지 못한다. 리뷰의 debt-c 요약 자체도 jest·pytest를 오분류함. | **accept-with-changes** → S4. warning은 "침묵 초록"인 **go/junit/xunit에만** 적용(그게 정확히 문제 집합). cargo/jest는 이미 loud(typed-error)라 별도 조치 불요. S4는 "3갈래 수렴"이 아니라 **"침묵 초록 가시화 + 3갈래를 문서로 명시"**로 재기술. 리뷰의 debt-c 오분류도 정정 기록. |
| C2 | **MEM-05** (손상 레코드가 history 스캔 붕괴) | `[H→미확정]`. H vs M 미해소. | **CONFIRMED이나 심각도 M**(too-high). blast radius는 리뷰가 말한 것보다 **넓다**(healthy run의 memory show/delete도 붕괴). 그러나 **loud**(app.py 최상위 catch가 구조화 cli-error 엔벨로프로 변환)·**복구가능**(파일 1개 삭제)·**무결성 무해**·**트리거 희소**(schema v2 skew는 현재 SCHEMA_VERSION=1이라 불가능). 코드베이스 자신의 H→M 보정 선례(MEM-01/02와 동일 규칙). | **accept, 심각도 M 확정** → Memory 트랙에 **신규 배정**(리뷰는 미스케줄). §4.4 참조. 수정 시 warning에 **손상 파일 경로 포함**(운영자가 grep 없이 찾도록). |
| C3 | **RUN-02** (JUnit stale glob) | "Gradle도 clean 없이는 동일". | Maven 절반은 견고(Surefire는 `mvn test`에서 리포트 미정리 — 확정). **Gradle 절반은 약함**: Gradle Test 태스크는 `build/test-results/test`를 `@OutputDirectory`로 선언하고 non-incremental 실행에서 stale-output 정리를 수행 → 필터 재실행 전에 옛 XML을 지울 개연성. | **accept**(H, Maven 근거로 정당) → S2. 단 **Gradle 절반은 착수 시 경험적 확인 필수** — 없는 문제를 "고치지" 않도록. 가장 깨끗한 수정은 Surefire `reportsDirectory`를 per-run 경로로 리다이렉트(persistent-workspace 의존 자체 제거, dotnet `--results-directory` 방식). |
| C4 | **부채 e / S0** (릴리스 최소 세트) | `pyproject.toml` + **`uv.lock` 재동기 = 2파일 커밋**. | **repo에 `uv.lock`이 없다**(의존성은 pyproject `[dependency-groups]`). 버전 범프는 실질 **1파일(pyproject) + 릴리스노트**. | **accept** → S0. 최소 세트를 "pyproject 1파일 + 릴리스노트"로 정정. |
| C5 | **ORC-12** (compound swallow 파일단위) | 결함(같은 파일 무관 심볼 침묵 삭제). | CONFIRMED. 단 **"결함 vs 의도" 모호**: `compound_resolution`의 선두 docstring(:494-499)은 파일단위 swallow를 **의도로** 서술. 최강 버그 신호는 compound matcher 자신의 `(file, line)` 주석(:256-259)과의 **내부 불일치**. | **gate-on-PM** → S26. 수정 방향(swallow 키를 `(file, primary_line)`로 좁힘)은 타당하나, brief §1/PM이 파일단위가 의도인지 먼저 확인. |
| C6 | **XCT-05** (fail-like outcome 드리프트) | M, "envelope 자기모순" 시나리오. | CONFIRMED(드리프트 실재: `fact_bundle.py:284`만 `"error"` 포함). 단 **현행 행동 피해는 이중 게이팅되어 현재 도달 불가**: (1) 어떤 어댑터도 `"error"` 단수를 emit 안 함(dotnet이 `error→errored` 정규화), (2) `has_failed_tests`는 `summary_counts.failed` 부재 시에만 스캔. | **accept as SSoT/drift cleanup** → S25. "활성 버그 수정"이 아니라 **재발 방지(SSoT + divergence-guard)**로 프레이밍. 심각도는 드리프트 관점 M 유지, 활성버그 관점으론 과대. |
| C7 | **MOD-01** (타임아웃 hang) | cargo nextest를 헤드라인 예시로. | CONFIRMED이나 **hang은 조건부**: 손자가 **우리 파이프 write-end를 상속**해야 성립. cargo/nextest는 per-test 파이프라 killed 후 EOF 도달(→ **orphan만**, hang 아님). 실제 hang 캐리어는 **셸 래핑 런처**(jest `cmd /c npx` Windows가 구체 사례). | **accept**(H 정당 — 발생 시 무한 hang·엔벨로프 미방출) → S3. 수정은 **양쪽 다**: 프로세스 트리 kill(killpg/job object) **+** gather에 grace 타임아웃(파이프 드레인 무한블록 차단). 한쪽만 고치면 나머지 절반이 남음. |
| C8 | **ORC-09** (읽기동사 exit2) | "모호/pre-pin 스토어". | CONFIRMED이나 **트리거가 더 좁다**: `pre-pin AND ambiguous`(단일마커 pre-pin은 조용히 backfill 후 진행, markerless는 unpinned 반환 — 둘 다 exit2 아님). post-D6 스토어는 이 경로 미도달. | **accept**(M, 계약 누출 실재) → S19. 트리거를 정확히 "legacy pre-pin + 모호 마커"로 기술. |

**부수 발견(리뷰에 없던, 재검증 중 확인된 stale docstring 2건):**
- `execute_with_engine_context`(run/engine.py:116-119) docstring이 "assess_engine_readiness로 게이트한다"고
  주장하나 본문은 호출 안 함 — **RUN-25와 ANA-13 두 에이전트가 독립 확인**. S16(또는 S38 착수 시) 함께 정정.

---

## 4. 클러스터별 수락 요약

### 4.1 H findings (5) — 전부 accept

| ID | 재검증 | 처분 | 배치 |
|---|---|---|---|
| RUN-01 (go 무증상 축소) | CONFIRMED·H agree | accept | S1 / W1 |
| RUN-02 (JUnit stale) | CONFIRMED·H agree | accept(C3: Gradle 경험적 확인) | S2 / W1 |
| ANA-01 (Cobertura 멀티클래스) | CONFIRMED·H agree | accept | S6 / W1 |
| ANA-02 (junit/xunit failure_proximity 침묵) | CONFIRMED·H agree | accept | S7 / W1 |
| MOD-01+RUN-15 (서브프로세스 트리) | CONFIRMED·H/M agree | accept(C7: 트리kill+grace 둘 다) | S3 / W1 |

리뷰의 "silent wrongness가 지배적 위험"이라는 지배 논지는 재검증으로 **뒷받침된다**. 이 5건 중 4건이
"초록인데 초록이 아니다" 계열이고, 국소·저비용 수정이면서 회수가 즉각적이다.

### 4.2 부채 판정 a~e — 전부 accept(부분 교정)

- **(a) 레지스트리 문서 후퇴, 구현 금지** — accept. 재검증: 레지스트리는 엔진-지식 7사이트 중 **1곳만** 기계적 제거,
  나머지(normalizer 사다리 포함)는 잔존. "one PR, one file"은 어느 설계에서도 과장. `_READINESS_PROBES`가 이미
  절반의 dict 하우스 패턴을 증명. **문서만 후퇴**(S24), 코드는 dict 하우스 패턴(S16).
- **(b) 레거시 `execute(engine=None)` 제거** — accept. 재검증: 프로덕션 도달 불가(호출자 2곳 명시 pair 전달),
  단 **단위테스트가 진입**하므로 제거 시 파라미터 비-옵셔널화 + 단위테스트 갱신 동반. `assess_engine_readiness`는 replay가
  소비하므로 **존치**. → S16.
- **(c) 제로-수집 warning** — **accept-with-changes(C1)**. → S4. §3 C1 참조.
- **(d) `_invoke_adapter` dict 디스패치** — accept. 재검증: 6개 `run_*` 시그니처 균일 확인, dict화 순수 기계적.
  guard 테스트는 readiness(pair-키)와 완전 동일 복붙은 아니고 engine_name 투영 필요. **레지스트리 아님**. → S16.
- **(e) 릴리스 선행** — **accept(C4)**. 재검증: pyproject 여전히 0.1.2, v0.1.2..HEAD 소스 13커밋이 CI-검증 지점부터
  **바이트 동일**(소스 무변경 릴리스는 Windows 회귀면 0 추가). `uv.lock` 없음 → 1파일. → S0.

### 4.3 검증된 M 클러스터 — 전부 accept(2건 교정)

- **Orchestration 계약**: ORC-03(이중접두)·ORC-04(errored 오분류; handlers/test.py:83-85에도 동일)·ORC-16(tombstone
  latest)·ORC-23(D7 토큰) — 전부 accept, S8/S10에서 단일 헬퍼로 수렴. ORC-03/23은 한 수정.
- **추천 합성**: ORC-12 — **gate-on-PM(C5)**; ORC-13 — accept(round-trip 실제 파손, NFR-ORCH-002 위반) → S26.
- **D6 읽기표면**: ORC-09(**C8**)·ORC-14·XCT-04 — accept, 원자 write + 읽기경로 backfill 생략 → S19. **D6는 최신 결정
  표면이라 착수 시 재검증 필수**(charter §6).
- **크로스-호스트/엔진**: RUN-13(jest 절대경로)·RUN-14(dotnet readiness 발산) — accept → S11/S2.
- **SBFL 정확성**: ANA-10(dstar2 denom 반전; 비기본 formula)·ANA-11(spectra outcome 분할; 기본 ochiai 영향이나 유계
  희석) — accept → S30.
- **Replay**: ANA-13(readiness 게이트가 틀린 엔진)·ANA-14(폐기된 rerun 은닉) — accept → S38.
- **드리프트**: XCT-05(**C6**, SSoT cleanup으로 프레이밍)·XCT-07(ULID 비결정 정렬) — accept → S25/S36.

### 4.4 재검증하지 않은 나머지 findings (~73건 M/L)

Top-10·부채·uncertain 밖의 M/L findings(다수의 dead-code 제거, 문서 드리프트, 위생 중복)은 이번 라운드에서
개별 재검증하지 않았다. 근거: (1) 대부분 grep 기반의 저위험·기계적 증거(dead code, docstring 드리프트)라 오탐
비용이 낮고, (2) 각 슬라이스 **착수 시점에 소유 팀이 재확인**하는 것이 더 효율적이며, (3) 리뷰의 검증 규율(모든
주장에 `file:line` + `검증 노트`, uncertain 자진 표기)이 이 계층에선 충분히 신뢰할 만하다. **이들은 "무조건 수락"이
아니라 "슬라이스 착수 시 소유 팀이 확인 후 수락"**이다 — charter §4 원칙 5의 집행을 슬라이스 단위로 위임한 것.

신규 배정 1건: **MEM-05(M)** — 리뷰가 미스케줄로 남긴 것을 재검증이 M으로 확정해 Memory 트랙에 넣는다(§3 C2).

---

## 5. 한 줄 결론

리뷰는 **형식(모든 주장에 file:line·실패시나리오·자진 uncertain 표기)과 실질(30/30 재검증 통과) 모두에서 신뢰할
만하다.** 우리는 그것을 신뢰가 아니라 **재현으로** 수락하며, 8개 교정(C1–C8)과 1개 신규 배정(MEM-05)을 반영해
[`02-roadmap.md`](02-roadmap.md)로 실행한다. 기각(reject)은 없다 — 재검증이 어떤 finding도 무효화하지 못했다.
