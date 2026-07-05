# Nove Test — 아키텍처/코드 리뷰 로드맵

작성일: 2026-07-05 · 대상: v0.1.2 태그 이후 `main` HEAD(`d689417`, v0.1.2..HEAD 61커밋) · src ~25.3k LOC

이 문서는 시니어 리뷰가 확정한 findings(H 6 / M 40+ / L 40+)와 부채 판정 `a`~`e`를
**한 팀이 한 사이클에 처리 가능한 슬라이스**로 분해하고, 우선순위·릴리스 타이밍을 배치한다.
개별 findings의 근거(file:line)와 실패 시나리오는 각 finding 문서에 있으며, 이 로드맵은 그 결론을
전제로 조직한다. 로드맵의 배치·순서는 부채 판정 `a`~`e`와 **모순되지 않는다**(§7에 정합 확인).

## 링크 규약 / 경로 주

- finding 링크는 로드맵과 같은 디렉터리의 `findings/` 하위 도메인 파일을 상대 참조한다:
  `ANA-*`→`findings/analysis-engines.md#ana-01`(실존 확인), `RUN-*`→`findings/run.md#run-01`,
  `ORC-*`→`findings/orchestration.md#orc-01`, `MEM-*`→`findings/memory.md#mem-01`,
  `MOD-*`→`findings/models-utils.md#mod-01`, `XCT-*`→`findings/cross-cutting.md#xct-01`.
  앵커는 각 finding 문서의 `<a id="run-01"></a>` 규약(`analysis-engines.md`에서 실측)을 따른다.
- 이 파일은 리뷰 디렉터리 `design/reviews/2026-07-04-codebase-review/roadmap.md`에 위치하여
  `00-summary.md` 및 `findings/` 하위 도메인 파일들과 같은 디렉터리에 공존한다.
  따라서 위의 `findings/<domain>.md#<id>` 상대링크는 같은 디렉터리의 `findings/` 하위 파일로 정상 해석된다.

---

## 0. 요약

- **총 슬라이스: 49개**(릴리스 컷 `S0` 1개 + 수정 슬라이스 48개).
- **릴리스 전 배치: `S0` 단 1개**(소스 무변경 릴리스 컷). 나머지 48개는 전부 v0.1.3 **이후**.
- 웨이브: 릴리스(`S0`) → **W1 즉시**(정확성·안전·데이터 무결성 10개) → **W2 하드닝·중복제거·크로스엔진**(36개) → **W3 대형 구조 리팩터**(2개).
- 부채 정합: `a`(문서 후퇴, 레지스트리 미구현) → `S24`. `b`(레거시 분기 제거) + `d`(dict 디스패치, 하우스 패턴) → `S16`. `c`(제로-수집 warning+passed) → `S4`. `e`(릴리스 선행) → `S0`가 유일한 릴리스-전 슬라이스.

---

## 1. 릴리스 타이밍 (부채 e) — v0.1.3를 **먼저** 컷

부채 판정 `e`에 따라, 대형 리팩터는 반드시 v0.1.3 릴리스 **이후**에 착수한다. HEAD는
CI 10/10 + Manual Test 통과 + agent-comms 5개 채널 전부 비어 있는 **검증된 최청정 지점**이며,
릴리스 비용은 실측 ~30분(2파일 바인딩)이다. 어떤 소스 수정도 이 지점에 얹으면
(a) Linux pre-merge 게이트가 구조적으로 못 잡는 Windows 회귀(직전 2회: `886dc09`, `fdf44d7`)의
잠복 표면을 키우고, (b) anchored-pin 행동 변화와 구조 변화가 한 릴리스에 섞여 사용자 리포트의
이분탐색을 오염시킨다. 따라서 **W1 이하 모든 슬라이스(정확성 버그 포함)는 릴리스 후**로 둔다.
v0.1.3 태그는 이후 리팩터 회귀의 고정 롤백 기준점이 되어 리팩터 자체의 안전성도 높인다.

**S0 · v0.1.3 릴리스 컷** — 팀: release + PM(+CEO 런북) · 크기: S(~30분 + 릴리스노트 반나절) · 선행: 없음 · **배치: 릴리스 전**
> 목표: 검증된 HEAD를 소스 무변경으로 v0.1.3 출하. `pyproject.toml` version `0.1.2→0.1.3` + `uv.lock` 재동기(2파일 커밋) + PM 작성 `design/release-notes/v0.1.3.md`(anchored-pin의 행동 변화 = init pin 생성/bare walk-up/신규 exit·에러코드 `no-engine-detected`·`engine-ambiguous`를 breaking-adjacent로 명시) + CEO 런북 4단계(`release-test.yml` dispatch → 태그 push → draft 확인 → promote).
> findings: 없음(부채 e 판정 — 소스 무변경). 릴리스노트가 유일한 실질 작업.
> 주의: 릴리스에는 아래 W1 버그들(예: `RUN-09` jest 주입, `RUN-01` go 축소)이 **미수정 상태로 실린다**. 전부 v0.1.2에도 이미 존재하는 잠복 결함이라 v0.1.3가 상태를 악화시키지 않는다. 팀이 원하면 이들을 v0.1.3.1 fast-follow로 뽑을 수 있으나, 그 판단은 릴리스 **후** W1 수행 여부일 뿐 릴리스를 게이트하지 않는다.

---

## 2. 슬라이스 분해 (마스터 표)

크기 표기: `S`=반나절 이하 / `1c`=한 사이클 / `1-2c` / `multi`=다중 사이클(계획 별도).

| ID | 이름 | 팀 | 크기 | 선행 | 배치 |
|---|---|---|---|---|---|
| S0 | v0.1.3 릴리스 컷 | release+PM | S | — | 릴리스 전 |
| S1 | 네이티브 타깃 변환 & argv 위생 | run | 1c | — | W1 |
| S2 | 실행별 리포트 격리 & readiness 정합 | run | 1c | — | W1 |
| S3 | 서브프로세스 수명주기 하드닝 | run | 1c | — | W1 |
| S4 | 제로-수집 경고(warning+passed) [부채 c] | run | S | — | W1 |
| S5 | Windows 런처 안전 & 메타문자 주입 방어 | run | 1c | — | W1 |
| S6 | Cobertura 멀티-클래스 병합 | coverage | 1c | — | W1 |
| S7 | failure_proximity junit/xunit 커버리지 + divergence 가드 | localization | 1c | S25(권장) | W1 |
| S8 | 실행 exit/에러코드 계약 수정 | orchestration | 1c | — | W1 |
| S9 | 툼스톤 원자성 | memory | S | — | W1 |
| S10 | status latest & 파생-플래그 신선도 | orchestration | S | — | W1 |
| S11 | jest node_id workspace-relative POSIX | run | 1c | — | W2 |
| S12 | cargo/dotnet 커버리지·타임아웃 정확성 | run | 1c | — | W2 |
| S13 | run/adapters 공용 헬퍼 추출(실패로그·서브프로세스 스켈레톤) | run | 1-2c | S1,S2,S12(soft) | W2 |
| S14 | pytest 인터프리터/결정론 env 계약 | run | 1c | S24(soft) | W2 |
| S15 | Run 경고 taxonomy · 죽은 코드 · readiness 예외 포착 | run | S | — | W2 |
| S16 | 레거시 engine=None 분기 제거 + dict 디스패치 [부채 b,d] | run | S-M | S24(soft) | W2 |
| S17 | 실행 예외 매핑 dedup | orchestration | 1c | S8 | W2 |
| S18 | run_id 해석 + Memory 단건 조회 API | orchestration+memory | 1c | — | W2 |
| S19 | D6 읽기-동사 seam & 원자적 backfill | orchestration+memory | 1c(+) | — | W2 |
| S20 | 타깃식 정규화(파일시스템 독립) | orchestration | S | — | W2 |
| S21 | 엔벨로프 Windows 안전 상대경로 | orchestration | S | — | W2 |
| S22 | CLI→워크플로 이관: 로컬라이제이션 캐시/unlink | orchestration | 1c | — | W2 |
| S23 | CLI→워크플로 이관: compare 뷰 + outcome 프로젝터 통합 | orchestration | 1c | — | W2 |
| S24 | 문서 후퇴 & 구조 동기화 [부채 a] | PM(+팀) | S-M | — | W2(조기) |
| S25 | fail-like outcome SSoT | orchestration(+models) | 1c | — | W2 |
| S26 | 추천 합성 정확성(compound swallow, citation round-trip) | orchestration | 1c | — | W2 |
| S27 | reset/init 엔벨로프 & 계약 docstring | orchestration | S | — | W2 |
| S28 | CLI 죽은 코드 & 스냅샷 가드 | orchestration | S | — | W2 |
| S29 | Localization reason 어휘 + formula-name SSoT | localization | 1c | wire-freeze 전 | W2 |
| S30 | SBFL 점수 정확성 | localization | 1c | — | W2 |
| S31 | per-test 경로 견고성 | localization | 1c | — | W2 |
| S32 | symbol resolver 캐시 & extent | localization | S | — | W2 |
| S33 | Coverage 요약 dedup + num_statements 의미 | coverage | 1c | — | W2 |
| S34 | JaCoCo 소스셋 경로 + 존재 필터 | coverage | 1c | — | W2 |
| S35 | Coverage 가용성/문서 & 죽은 reason | coverage | S | — | W2 |
| S36 | Regression 결정성 & divergence(타이브레이크) | regression(+utils/memory) | 1c | — | W2 |
| S37 | Regression 캐시 견고성 & 중복 node_id | regression | 1c | — | W2 |
| S38 | Replay readiness & rerun 계수 | replay | 1c | — | W2 |
| S39 | Replay 불가용 채널 정책 | replay(+정책 doc) | 1c | S24/정책 | W2 |
| S40 | Replay 유닛 미러 | replay | 1c | — | W2 |
| S41 | Memory 동시성(run+reset) & 위생 | memory | 1c | — | W2 |
| S42 | 저장소 손상 exit-5 전파 | memory+orchestration | 1c | — | W2 |
| S43 | Memory 공개 표면 & 레이어 경계 | memory(+cross) | 1c | S24/SSoT | W2 |
| S44 | 엔진 e2e equip 갭 & skip→fail 게이트 & perf NFR | release(+Main) | multi | infra | W2/W3 트랙 |
| S45 | models/utils 위생 | models-utils | S | S3(MOD-05) | W2 |
| S46 | workspaces 등록-사이트 완결성 테스트 | orchestration | 1c | — | W2 |
| S47 | cli/app.py 분해 | orchestration | multi | S8,S17,S22,S23 | W3 |
| S48 | 파생-엔진 import DAG / orchestration 주입 합성 | cross | multi | S25 + 경계가드 안정 | W3 |

---

## 3. 슬라이스 상세 (findings 링크 · 목표)

### 웨이브 W1 — 즉시(정확성·안전·데이터 무결성)

**S1 · 네이티브 타깃 변환 & argv 위생** — run · 1c · 선행 없음
- findings: [RUN-01](findings/run.md#run-01)(H), [RUN-22](findings/run.md#run-22)(L)
- 목표: `target_expression`을 엔진별 올바른 argv로 변환. go의 directory/nodeid를 `./<rel>/...`·`<pkg> -run '^<Test>$'`로 분해해 `novetest run .`의 무증상 축소를 제거하고, pytest/jest/cargo에 `--` 분리자를 넣어 `-`선두 타깃이 플래그로 소비되지 않게 못박는다.

**S2 · 실행별 리포트 격리 & readiness 정합** — run · 1c · 선행 없음
- findings: [RUN-02](findings/run.md#run-02)(H), [RUN-14](findings/run.md#run-14)(M)
- 목표: JUnit 어댑터가 실행 전 스테이징 리포트 디렉터리를 비우거나 `mtime>started_ms` 필터로 stale `TEST-*.xml`을 차단(다른 5개 어댑터와 동일한 per-run 격리). dotnet readiness의 test-csproj 선택 필터를 어댑터 `_detect_test_project`와 동일 토큰·정렬로 SSoT화해 "ready 후 다른 csproj 실행" 발산을 제거.

**S3 · 서브프로세스 수명주기 하드닝** — run · 1c · 선행 없음
- findings: [RUN-15](findings/run.md#run-15)/[MOD-01](findings/models-utils.md#mod-01)(H, 동일 결함), [RUN-27](findings/run.md#run-27)/[MOD-02](findings/models-utils.md#mod-02)(M, 동일 결함)
- 목표: `utils/asyncio_subprocess.run_subprocess`가 타임아웃 시 프로세스 **트리** 전체를 종료(POSIX `start_new_session=True`+`os.killpg`, Windows job object/`taskkill /T`; SIGTERM→유예→SIGKILL). stdout/stderr 캡처에 바이트 상한(초과 truncate+플래그) 도입. 손자 프로세스 고아화·파이프 EOF 무한 hang·폭주 출력 OOM을 함께 봉쇄.

**S4 · 제로-수집 경고(warning+passed)** [부채 c] — run · S · 선행 없음
- findings: [RUN-12](findings/run.md#run-12)(M)
- 목표: 부채 c 권고안 ③. `engine.py:139-146` normalize 직후 **단일 사이트**에서 `not record.test_results and status=="passed"`일 때 `AdapterWarning(code="zero-tests-collected")`를 warnings에 추가. envelope 스키마·exit code·persisted record 불변(2026-06-06 warning 채널 재사용). 신규 status 도입·에러 승격은 이 슬라이스 밖(§5 참조).

**S5 · Windows 런처 안전 & 메타문자 주입 방어** — run · 1c · 선행 없음
- findings: [RUN-09](findings/run.md#run-09)(M, RCE·Windows), [RUN-10](findings/run.md#run-10)(M)
- 목표: jest `cmd /c` 경로에서 미검증 target의 `&|<>^%"` 메타문자를 usage 오류로 반려(또는 node로 `jest.js` 직접 exec 전환). junit이 `mvn.cmd/gradle.bat/gradlew`를 `cmd /c` 경유로 실행하도록 jest `_npx_launcher` 패턴 적용 + `-Dtest`/`--tests` 주입 방어. Windows CI에 junit 레인이 없어 미검출 표면이므로 S44와 조율.

**S6 · Cobertura 멀티-클래스 병합** — coverage · 1c · 선행 없음
- findings: [ANA-01](findings/analysis-engines.md#ana-01)(H)
- 목표: `cobertura_parser`가 동일 `file_path`의 다중 `<class>`를 덮어쓰지 말고 executed/missing 라인을 합집합 병합(executed 우선) + per-file summary 재계산. 멀티타입 `.cs` 파일 커버리지 소실 제거. 파일당 `<class>` 2개 회귀 픽스처 추가.

**S7 · failure_proximity junit/xunit 커버리지 + divergence 가드** — localization · 1c · 선행: S25 권장
- findings: [ANA-02](findings/analysis-engines.md#ana-02)(H)
- 목표: `resolve_failure_text` inline 튜플에 junit/xunit 추가(`("pytest","jest","junit","xunit")`) + `_ENGINE_REGEX_TABLE`에 JUnit/xUnit 스택 정규식 추가. 두 리스트를 `list_supported_engine_pairs()` 대비 검증하는 divergence 테스트를 localization에 신설(readiness의 `test_engine_selector.py:202-213` 패턴 복제)해 7번째 엔진 누락 재발을 테스트 타임에 차단.

**S8 · 실행 exit/에러코드 계약 수정** — orchestration · 1c · 선행 없음
- findings: [ORC-03](findings/orchestration.md#orc-03)(M), [ORC-04](findings/orchestration.md#orc-04)(M), [ORC-23](findings/orchestration.md#orc-23)(L)
- 목표: `app.py:606/1674`의 이중접두 `engine-engine-missing` 제거(`code=exc.readiness.state`). `errored` 런을 exit1/ok=False(도구 실패)에서 `failed` 계열(ok=True, exit3)로 재분류. status→(ok,exit) 매핑을 단일 헬퍼로 추출해 `run_cmd`/`handlers/test.py`가 공유. markerless 실행 분기의 토큰을 D7 표준(`no-engine-detected`/`engine-missing`)으로 정렬.

**S9 · 툼스톤 원자성** — memory · S · 선행 없음
- findings: [MEM-02](findings/memory.md#mem-02)(M)
- 목표: `store.py`의 tombstone을 rename-후-mutate에서 mutate-후-단일-rename으로 뒤집어, 크래시 시 status/tombstoned_at 불변식 위반 부분상태를 제거.

**S10 · status latest & 파생-플래그 신선도** — orchestration · S · 선행 없음
- findings: [ORC-16](findings/orchestration.md#orc-16)(M), [ORC-26](findings/orchestration.md#orc-26)(L)
- 목표: `build_status_view`의 latest 선택에서 tombstone 제외(삭제된 run을 head로 오보 방지). `test_target_in_store` memory_entry가 regression/localization 파생 후 재조회되도록 리프레시 지점 일원화(stale 파생 플래그 제거).

### 웨이브 W2 — 하드닝 · 중복제거 · 크로스엔진 정확성

**S11 · jest node_id workspace-relative POSIX** — run · 1c · 선행 없음
- findings: [RUN-13](findings/run.md#run-13)(M)
- 목표: jest suite name을 workspace-relative `.as_posix()`로 정규화해 node_id 접두에 사용(절대경로·Windows 역슬래시 유입 제거, 크로스-호스트 regression 매칭 복원). 회귀 테스트 추가.

**S12 · cargo/dotnet 커버리지·타임아웃 정확성** — run · 1c · 선행 없음
- findings: [RUN-05](findings/run.md#run-05)(M), [RUN-08](findings/run.md#run-08)(M), [RUN-18](findings/run.md#run-18)(L), [RUN-20](findings/run.md#run-20)(L)
- 목표: cargo 커버리지 모드에서도 빌드실패를 먼저 진단(`saw_test_started` False+rc!=0 → 컴파일 실패). dotnet caller timeout을 restore/probe/version 사전단계로 전파(하드코딩 300/30/10을 `min()` 클램프). dotnet 보조 서브프로세스에 `_build_child_env` 정화 적용. go `-timeout`을 서브프로세스 타임아웃보다 작게 두어 그레이스풀 자체-덤프 복원.

**S13 · run/adapters 공용 헬퍼 추출** — run · 1-2c · 선행: S1,S2,S12(soft)
- findings: [RUN-04](findings/run.md#run-04)(M), [RUN-06](findings/run.md#run-06)(M), [RUN-17](findings/run.md#run-17)(L), [RUN-23](findings/run.md#run-23)(L)
- 목표: `run/adapters/_harness.py`(가칭)에 (a) `safe_failure_log_name(name, extra_chars=())` 단일 구현(Windows 예약문자 union 기본), (b) `failure_path.relative_to(artifact_dir).as_posix()` 정규화, (c) 빈 버퍼 실패로그 생성/등록 규칙 통일, (d) native_dir 준비 + timed run_subprocess + stdout/stderr 아티팩트 기록 스켈레톤을 모으고 6개 어댑터가 호출. 선행 슬라이스에서 어댑터 본문이 안정된 뒤 dedup해 merge churn 최소화.

**S14 · pytest 인터프리터/결정론 env 계약** — run · 1c · 선행: S24(soft)
- findings: [RUN-11](findings/run.md#run-11)(M), [RUN-24](findings/run.md#run-24)(L)
- 목표: target/.venv 우선 인터프리터 해석(존재 시) + `PYTHONHASHSEED=0`/`CI=1`/`FORCE_COLOR` 정책을 `_build_child_env`에 반영하고 자식 `PYTHONPATH` 제거. 구현 불가/불필요로 판정되면 대신 `foundations.md §3:186-187`을 실태에 맞게 정정(S24와 배칭). 배포 모드(standalone vs pipx-into-venv)에 따라 심각도가 갈리므로 배포 계약과 함께 판단.

**S15 · Run 경고 taxonomy · 죽은 코드 · readiness 예외 포착** — run · S · 선행 없음
- findings: [RUN-07](findings/run.md#run-07)(M), [RUN-19](findings/run.md#run-19)(L), [RUN-21](findings/run.md#run-21)(L), [RUN-26](findings/run.md#run-26)(L)
- 목표: dotnet의 두 Coverlet warning kind를 `"engine-misconfigured"`(readiness-state 토큰과 충돌) 대신 고유 slug로 분리. dead code `_slugify_for_coverlet`·`_glob_jacoco_xml` 제거(또는 후자는 Maven 인라인 글로빙을 헬퍼로 통합). go/cargo/pytest probe의 `run_subprocess`를 dotnet과 동일하게 `(OSError, FileNotFoundError)` 포착해 engine-misconfigured로 격하(TOCTOU crash 방지).

**S16 · 레거시 engine=None 분기 제거 + dict 디스패치** [부채 b,d] — run · S-M · 선행: S24(soft)
- findings: [RUN-25](findings/run.md#run-25)(L)
- 목표: 부채 b — `engine.py`의 `engine=None` auto-detect 분기 삭제(프로덕션 호출자 2곳 모두 명시 pair 전달, 도달 불가 확인). `select_native_engine` 동반 삭제, `assess_engine_readiness`는 replay가 소비하므로 **존치**(과잉 삭제 금지). 부채 d — `_invoke_adapter`의 6-branch if-사다리를 `readiness._READINESS_PROBES` **하우스 패턴**(모듈 상수 dict + divergence-guard 테스트)으로 접음. **데코레이터 레지스트리 도입 금지**(§5·부채 a/d 참조). normalizer.py 사다리는 시그니처 정규화가 필요하면 분리 가능. 같은 파일 이중 터치를 피하려 두 부채를 한 슬라이스로 배칭.

**S17 · 실행 예외 매핑 dedup** — orchestration · 1c · 선행: S8
- findings: [ORC-02](findings/orchestration.md#orc-02)(M), [ORC-21](findings/orchestration.md#orc-21)(L)
- 목표: `run_cmd`/`test_cmd`의 verbatim 복붙된 3개 except(EngineAmbiguous/EngineNotReady/AdapterInvocation)를 `_map_execution_exception(command, exc)->(Envelope,int)` 공유 헬퍼로 수렴(EngineAmbiguous TOCTOU 분기 흡수). 포괄 catch가 동사명을 보존하고 RunEngineError 계열을 구조적으로 매핑(EngineNotSupported→exit4).

**S18 · run_id 해석 + Memory 단건 조회 API** — orchestration+memory · 1c · 선행 없음
- findings: [ORC-05](findings/orchestration.md#orc-05)(M)
- 목표: Memory에 `find_entry_by_run_id(store, run_id)` 공개 API 추가, CLI 4중 복제(memory_show/delete/_resolve_run_reference/inspect)를 이 호출(또는 공유 `_resolve_run_reference`)로 대체. not-found 엔벨로프 문자열을 단일 상수화.

**S19 · D6 읽기-동사 seam & 원자적 backfill** — orchestration+memory · 1c(+) · 선행 없음
- findings: [ORC-09](findings/orchestration.md#orc-09)(M), [XCT-04](findings/cross-cutting.md#xct-04)(M), [ORC-14](findings/orchestration.md#orc-14)(M), [ORC-25](findings/orchestration.md#orc-25)(L)
- 목표: 읽기 전용 동사(status/memory list/inspect)가 모호/pre-pin 스토어에서 exit2 하드 실패하지 않도록 seam 분리(EngineAmbiguousError는 실행 동사가 `resolve_execution_engine`에서만 만남). D6 backfill 쓰기를 Memory 소유 원자적 temp-write+rename으로 바꾸고 읽기 경로에서는 backfill 생략. inspect의 regression 파생-부수효과를 status와 동일하게 캐시-전용으로 맞추거나 계약 docstring 정정. **주의: D6는 2026-07-03 최신 결정 표면 — 구현 완결성이 가장 불확실하므로 슬라이스 착수 시 재검증 필수.**

**S20 · 타깃식 정규화(파일시스템 독립)** — orchestration · S · 선행 없음
- findings: [ORC-10](findings/orchestration.md#orc-10)(M)
- 목표: `normalize_target_expression`의 else(비존재) 분기에도 lexical canonicalization 적용(`..` collapse 포함)해 파일시스템 존재 여부와 무관하게 안정된 키 산출. regression baseline 시리즈 분열 제거. Windows-dotdotdot fast-follow(`fdf44d7`) 계보의 잔여 표면.

**S21 · 엔벨로프 Windows 안전 상대경로** — orchestration · S · 선행 없음
- findings: [ORC-15](findings/orchestration.md#orc-15)(M)
- 목표: `run.py:125`·`test.py:209`의 `str(Path(p).relative_to(store.path))`를 `.as_posix()` 정규화로 교체(Wave-1이 이미 채택한 패턴). record.json·run 엔벨로프의 backslash 유출 제거. `store_run_evidence` 상대화 주석도 정정.

**S22 · CLI→워크플로 이관: 로컬라이제이션 캐시/unlink** — orchestration · 1c · 선행 없음
- findings: [ORC-07](findings/orchestration.md#orc-07)(M), [XCT-02](findings/cross-cutting.md#xct-02)(M)
- 목표: cli에 상주하는 ~230줄 localization 캐시 무효화 정책(파일 unlink + 재파생 + failure_proximity 예외처리)을 orchestration의 localization 워크플로 핸들러로 이관. cli는 (outcome, warning) 튜플만 받아 envelope로 투영. `localization_findings_path`의 CLI import 제거. cli→orchestration 방향이라 사이클 없음, 단일 팀.

**S23 · CLI→워크플로 이관: compare 뷰 + outcome 프로젝터 통합** — orchestration · 1c · 선행 없음
- findings: [ORC-06](findings/orchestration.md#orc-06)(M), [ORC-08](findings/orchestration.md#orc-08)(M)
- 목표: top-level `compare` verb의 regression+coverage 인라인 합성을 `build_compare_view(store, baseline, target)` 워크플로로 이관(coverage delta 이중노출 정리). cli/app.py와 inspect.py에 이중 정의된 엔진 outcome 프로젝터 4쌍을 orchestration 중립 모듈로 이동해 단일 출처화. 둘 다 Orchestration 단일 팀.

**S24 · 문서 후퇴 & 구조 동기화** [부채 a] — PM(+팀) · S-M · 선행 없음 · **조기 권장**
- findings: [XCT-01](findings/cross-cutting.md#xct-01)(M), [RUN-03](findings/run.md#run-03)(M), [RUN-16](findings/run.md#run-16)(L), [ORC-17](findings/orchestration.md#orc-17)/[XCT-11](findings/cross-cutting.md#xct-11)(L)
- 목표: 부채 a — `foundations.md §5` 트리(:322-440)와 "Adapter registry"(:448-475) 의사코드를 실물(함수형 adapter 6개 `*_adapter.py`, 빈 `adapters/__init__.py`, `engine.py` if-elif 디스패치, `_READINESS_PROBES`·`_ENGINE_MARKER_TABLE` SSoT)로 재작성. **레지스트리는 구현하지 않는다.** cargo 계약(`interace-contract/run.md:78,82`, `workflows/run.md:31,77`)을 nextest 단독 경로로 갱신 + Open Q#3 해소 표기. dotnet per-test 모순(`engine-adapters.md:506-508`)을 2026-06-05 Amendment(aggregate-effective-default)에 정렬. `CLAUDE.md:42`·`foundations.md:421`의 `mcp/`를 '(Phase 7, 미구현)'으로 표기. **소유권 위험: 이 stale 서술은 program-close carry-forward #5로 '미추적 파킹' 상태 — PM 배정 없이는 재방치되므로 명시 소유 지정 필요.**

**S25 · fail-like outcome SSoT** — orchestration(+models) · 1c · 선행 없음
- findings: [XCT-05](findings/cross-cutting.md#xct-05)(M)
- 목표: `models/`에 `FAIL_LIKE_OUTCOMES: frozenset[str]` 단일 정본을 두고 localization 3곳·replay·regression·`fact_bundle`·normalizer의 인라인 튜플을 전부 import로 통합. `fact_bundle`의 `"error"` 포함 여부를 이 단일 지점에서 정책 결정. 정본==각 소비자 집합을 pin하는 divergence-guard 테스트 추가. S7(failure_proximity 멤버십)과 조율.

**S26 · 추천 합성 정확성** — orchestration · 1c · 선행 없음
- findings: [ORC-12](findings/orchestration.md#orc-12)(M), [ORC-13](findings/orchestration.md#orc-13)(M), [ORC-18](findings/orchestration.md#orc-18)(L)
- 목표: `compound_resolution`의 swallow 판정 키를 파일 단위에서 `(file, primary_line)`/`(file, symbol)`로 좁혀 같은 파일의 무관한 심볼 추천 침묵 삭제 제거(스펙이 파일 단위 의도면 PM 확인). `_coverage_gap_citations`가 `related_finding_id`(entry_index)를 selector에 실어 round-trip 복원. 문서 §3 citation shape를 코드 실제(per-run finding_id + rank/file/primary_line selector)로 정합(ORC-13과 한 커밋).

**S27 · reset/init 엔벨로프 & 계약 docstring** — orchestration · S · 선행 없음
- findings: [ORC-20](findings/orchestration.md#orc-20)(L), [ORC-24](findings/orchestration.md#orc-24)(L)
- 목표: reset 성공 data에 init과 동형 `pinned_engine` 추가(byte-stability 스냅샷 갱신 시 additive 필드로 기록). reset docstring의 'still recoverable' 문구를 rename 이전 실패로 한정하고 step6 rmtree 실패는 staging orphan임을 primitive 계약과 일치.

**S28 · CLI 죽은 코드 & 스냅샷 가드** — orchestration · S · 선행 없음
- findings: [ORC-19](findings/orchestration.md#orc-19)(L), [ORC-22](findings/orchestration.md#orc-22)(L), [ORC-27](findings/orchestration.md#orc-27)(L)
- 목표: 스텁 등록 클러스터(`_make_stub`/`_register_flat_stub`/`_register_group_stub` + 'Remaining stubs' 주석 + 도달불가 `--output` 분기 + 고아 `not_implemented_envelope` import)와 `indent_block` dead code 제거. 통합 스냅샷 strip allowlist를 스키마 파생 또는 동기화 가드 테스트로 보강.

**S29 · Localization reason 어휘 + formula-name SSoT** — localization · 1c · 선행: wire-freeze 전
- findings: [ANA-09](findings/analysis-engines.md#ana-09)(M), [ANA-19](findings/analysis-engines.md#ana-19)(L)
- 목표: localization 5개 REASON 상수를 kebab-case로 정렬(`missing-derived-facts` 등)해 6엔진 reason 어휘 통일(wire freeze 전이 적기). tombstoned 개념 분산(`run-tombstoned`/`tombstoned-original`/`run_not_analyzable`) 표준화 검토. formula 이름 집합을 `sbfl/__init__`(또는 models)의 canonical `FORMULA_NAMES` 단일 상수로 통합.

**S30 · SBFL 점수 정확성** — localization · 1c · 선행 없음
- findings: [ANA-10](findings/analysis-engines.md#ana-10)(M), [ANA-11](findings/analysis-engines.md#ana-11)(M), [ANA-20](findings/analysis-engines.md#ana-20)(L)
- 목표: DStar denom==0 & ef>0 위치를 점수 0이 아니라 최대 의심으로 처리(정규화 전 finite-max sentinel). spectra 이진 outcome 분할을 aggregate와 동일한 `outcome=="passed"`로 정의하고 xfailed/skipped/xpassed 제외(passing 정의 SSoT). op2/dstar2 alternate_scores를 formula별 min-max 정규화(또는 raw 비교불가 명시).

**S31 · per-test 경로 견고성** — localization · 1c · 선행 없음
- findings: [ANA-07](findings/analysis-engines.md#ana-07)(M), [ANA-08](findings/analysis-engines.md#ana-08)(M), [ANA-18](findings/analysis-engines.md#ana-18)(L)
- 목표: per-test 디스패치를 `try/except SpectraBuildError`로 감싸 `LocalizationUnavailable(REASON_NO_COVERAGE)` 반환(엔진 total 계약 유지, cli-error/exit1 누출 차단). per-test도 truncate 전 선택공식 점수>0 필터 적용(aggregate와 동일, 잡음 제거). 모듈/results docstring을 3-way 모드 라우팅 실태로 정정.

**S32 · symbol resolver 캐시 & extent** — localization · S · 선행 없음
- findings: [ANA-21](findings/analysis-engines.md#ana-21)(L), [ANA-22](findings/analysis-engines.md#ana-22)(L)
- 목표: 파스 캐시 키에 `st_mtime_ns`(또는 size) 포함(또는 MVP '프로세스 수명=1요청' 전제를 주석으로 못박고 Phase 7 무효화/LRU 조건 명시). 함수 extent 시작점을 `decorator_list[0].lineno`로 낮춰 데코레이터 줄 포함.

**S33 · Coverage 요약 dedup + num_statements 의미** — coverage · 1c · 선행 없음
- findings: [ANA-06](findings/analysis-engines.md#ana-06)(M), [ANA-04](findings/analysis-engines.md#ana-04)(M)
- 목표: `coverage/_summary.py`에 `percent_covered(num,covered)`+`aggregate_summary(files)` 단일 구현을 두고 4개 파서 위임(empty→100.0 관례·missing 재계산을 한 곳으로). num_statements 계약 의미를 스키마 수준에서 '문 수'로 확정하고 라인기반 파서 관행을 문서/필드로 명시(또는 istanbul을 라인수로 통일).

**S34 · JaCoCo 소스셋 경로 + 존재 필터** — coverage · 1c · 선행 없음
- findings: [ANA-05](findings/analysis-engines.md#ana-05)(M)
- 목표: 단기 — 파생 file_path 디스크 존재 필터를 junit derive 경로에도 적용(비존재는 metadata 경고). 근본 — `src/main/java` 하드코딩 대신 워크스페이스 소스셋 탐지/`<sources>`로 해석. 최소한 v1 지원 범위(표준 Java 레이아웃) 명시.

**S35 · Coverage 가용성/문서 & 죽은 reason** — coverage · S · 선행 없음
- findings: [ANA-16](findings/analysis-engines.md#ana-16)(L), [ANA-17](findings/analysis-engines.md#ana-17)(L)
- 목표: availability/derive docstring에서 go-test를 coverage_json 목록에서 제거하고 'coverage_profile 미구현(unavailable)'으로 정정(`_COVERAGE_ARTIFACT_KEYS` 동기화 주석). `REASON_INCOMPARABLE_GRANULARITY`를 실제 방출하도록 구현하거나 compare docstring의 'flag incomparable' 서술+미사용 상수 제거(문서·코드 수렴).

**S36 · Regression 결정성 & divergence(타이브레이크)** — regression(+utils/memory) · 1c · 선행 없음
- findings: [ANA-25](findings/analysis-engines.md#ana-25)(L), [ANA-26](findings/analysis-engines.md#ana-26)(L), [XCT-07](findings/cross-cutting.md#xct-07)(M)
- 목표: `created_at` 동률 시 run_id 2차 tiebreak로 엄격 순서 정의(오도성 `(engine=)` suffix 제거). `check_regression_availability`(any-sibling)를 `resolve_baseline_for_run`(strictly-older+same-engine)과 동일 술어로 정렬(또는 위임)하고 docstring 미존재 소비자 주장 정정. XCT-07 — `memory/store.py` 두 정렬에 run_id 2차 키 추가(동일-ms ULID 비결정성 제거). carry-forward #7 수렴 지점.

**S37 · Regression 캐시 견고성 & 중복 node_id** — regression · 1c · 선행 없음
- findings: [ANA-23](findings/analysis-engines.md#ana-23)(L), [ANA-24](findings/analysis-engines.md#ana-24)(M)
- 목표: `compare_runs`에서 `get_regression_facts` 파싱/스키마 예외를 `missing-derived-facts`로 강등해 derive 폴백(자가치유). node_id 딕셔너리화의 동일 node_id 중복을 명시 병합 정책(fail-우선 + 경고, 또는 인덱스 접미)으로 가시화. regression/replay 공통 패턴이라 공유 헬퍼화 고려.

**S38 · Replay readiness & rerun 계수** — replay · 1c · 선행 없음
- findings: [ANA-13](findings/analysis-engines.md#ana-13)(M), [ANA-14](findings/analysis-engines.md#ana-14)(M)
- 목표: replay readiness 게이트를 '우선순위 1위 자동감지'가 아니라 기록 엔진에 `probe_engine(...ecosystem, engine_name)`로 정확히 게이트, anchored-pin pinned 규약과 일치(engine.py:117-119 stale docstring 정정). 파싱 불가 rerun(AdapterInvocationError)을 버리지 말고 errored로 계수(reruns_total/분류 왜곡 제거).

**S39 · Replay 불가용 채널 정책** — replay(+정책 doc) · 1c · 선행: S24/정책
- findings: [ANA-03](findings/analysis-engines.md#ana-03)(M)
- 목표: '실행형 동사(run/test/replay)=엔진 부재 exit4 / 순수 읽기형(coverage/regression/localization)=불가용 exit0 data' 규칙을 계약 문서에 명문화하거나, replay도 불가용을 data 채널로 통일하고 exit는 별도 필드로. 4개 파생엔진 불가용 채널 정책을 한 표로 고정.

**S40 · Replay 유닛 미러** — replay · 1c · 선행 없음
- findings: [ANA-12](findings/analysis-engines.md#ana-12)(M)
- 목표: `tests/unit/replay/test_engine.py` 추가 — run 경로를 stub한 채 reruns 루프·ReplayUnavailable 분기·classify+persist tail을 격리 유닛으로 검증(현재 실 pytest 스폰 통합 테스트로만 커버).

**S41 · Memory 동시성(run+reset) & 위생** — memory · 1c · 선행 없음
- findings: [MEM-01](findings/memory.md#mem-01)(M), [MEM-03](findings/memory.md#mem-03)(L), [MEM-04](findings/memory.md#mem-04)(L)
- 목표: `store_run_evidence`가 mkdir 전 store.json 존재를 재확인해 wipe rename과의 경합으로 인한 조용한 run 유실/고아 스켈레톤 방지(워크스페이스 어드바이저리 락 검토). init/reset 진입 시 `.novetest.deleting.*` staging 잔재 best-effort 재수확. `stored_at`을 record.json 영속 필드로 기록(mtime 의존 제거, 툼스톤 시 원값 보존).

**S42 · 저장소 손상 exit-5 전파** — memory+orchestration · 1c · 선행 없음
- findings: [XCT-03](findings/cross-cutting.md#xct-03)(M)
- 목표: `memory/store.py::_read_record`가 json/구조 오류를 `ProjectStoreCorruptError`로 감싸 던지고(project_store가 store.json에 하는 방식과 일치), cli read 동사들이 이를 `EXIT_STORAGE`로 매핑. exit-5 의미론을 해석 seam 밖에서도 방어(두 팀 걸침).

**S43 · Memory 공개 표면 & 레이어 경계** — memory(+cross) · 1c · 선행: S24/SSoT
- findings: [XCT-12](findings/cross-cutting.md#xct-12)(L), [XCT-13](findings/cross-cutting.md#xct-13)(L)
- 목표: 파생 엔진 27개 import를 `from novetest.memory import ...` 공개 경로로 통일(내부 store/project_store 직접참조 금지, `__all__` 명시 배제 + lint/리뷰 체크). `list_supported_engine_pairs` 지원쌍 상수를 `models/`(또는 공유 config)로 승격해 memory→run 상향 import 제거(부채 a/d의 SSoT 승격과 조율).

**S44 · 엔진 e2e equip 갭 & skip→fail 게이트 & perf NFR** — release(+Main) · multi · 선행: infra
- findings: [XCT-08](findings/cross-cutting.md#xct-08)(M), [XCT-09](findings/cross-cutting.md#xct-09)(M), [XCT-10](findings/cross-cutting.md#xct-10)(L), [XCT-14](findings/cross-cutting.md#xct-14)(L), [ANA-15](findings/analysis-engines.md#ana-15)(M)
- 목표: CI 매트릭스에 go/cargo/dotnet/java 셀(최소 1 OS) 추가하거나 장착 셀에서 skip→fail 승격 가드(`NOVETEST_REQUIRE_ENGINES`) + skip 카운트 상·하한 assert로 조용한 skip 퇴화 가시화. `test_junit_jacoco_derive.py`(java-gated) 또는 실 JaCoCo 골든 픽스처 추가. perf NFR을 required-but-generous(천장 2~3배 하드 실패선)로 승격. CI 미실행 픽스처 유지비를 엔진 셀 추가와 묶어 정리. **carry-forward #4(equip 갭 3사이클 연속) 근본 해소 트랙.**

**S45 · models/utils 위생** — models-utils · S · 선행: S3(MOD-05)
- findings: [MOD-03](findings/models-utils.md#mod-03)(L), [MOD-04](findings/models-utils.md#mod-04)(L), [MOD-05](findings/models-utils.md#mod-05)(L)
- 목표: 3개 모델 계약 테스트를 `tests/unit/models/` 미러로 이동(또는 미러 규칙 완화 문서화). `test_id==node_id` 동일성을 각 모델/계약 문서 docstring에 명시(v1 wire 동결이라 실제 rename은 차기 schema bump 후보). `asyncio_subprocess`를 run/ 하위로 이동하거나 'Run-owned infra' 주석 명시(S3에서 이미 손대므로 함께).

**S46 · workspaces 등록-사이트 완결성 테스트** — orchestration · 1c · 선행 없음
- findings: [ORC-11](findings/orchestration.md#orc-11)(M)
- 목표: cli/app 트리 순회로 등록된 command 토큰을 수집해 `registry._RENDERERS` 키 집합 + `command_surface` name 집합과 정확 일치하는지 assert하는 완결성 테스트 추가(두 침묵 등록 사이트 `registry.py:55`·`command_surface.py:66`을 테스트 타임에 loud화). **신규 `workspaces` 동사 본체는 제품 결정(미스케줄) — 이 슬라이스는 테스트만.**

### 웨이브 W3 — 대형 구조 리팩터 (릴리스·seam 슬라이스 이후)

**S47 · cli/app.py 분해** — orchestration · multi · 선행: S8,S17,S22,S23
- findings: [ORC-01](findings/orchestration.md#orc-01)(M, multi-cycle)
- 목표: 1973줄 `app.py`를 절단선대로 분해 — argv 진입점군→`cli/entrypoint.py`, 투영군→`handlers/` per-engine, localization 캐시정책→orchestration 워크플로, init/reset 리퓨절 빌더→`handlers/onboarding.py`. 잔여 app.py는 @command 정의 + 얇은 seam ~700줄대. **선행 슬라이스(S8/S17/S22/S23)가 이미 여러 seam을 추출하므로 그 뒤에 착수해야 churn·충돌 최소.**

**S48 · 파생-엔진 import DAG / orchestration 주입 합성** — cross · multi · 선행: S25 + 경계가드 안정
- findings: [XCT-06](findings/cross-cutting.md#xct-06)(M, multi-cycle)
- 목표: cross-engine fact 합성(coverage delta 임베드, regression prior 재가중)을 orchestration이 주입하거나 공유 selector 하나로 엔진경계 가드를 SSoT화. 소비자는 각 엔진 공개 `__init__` 심볼만 바인딩(내부 서브모듈 직접참조 제거). **엔진경계 가드가 S25 등으로 안정된 뒤 착수.**

---

## 4. 우선순위 순서와 근거

순위는 (1) 데이터/사용자-가시 정확성 손상 여부, (2) blast radius(다운스트림 오염 vs 국소), (3) 부채 판정과의 정합, (4) 비용 대비 회수로 매겼다.

| 순위 | 슬라이스 | 근거 요지 |
|---|---|---|
| 1 | S1, S2 | Top-10 H. `novetest run .`이 루트 패키지만 실행(무증상 축소)·JUnit이 stale XML을 현재 결과로 보고 — 둘 다 **사용자가 틀린 답을 신뢰**하게 만드는 정확성 손상. 국소 수정. |
| 2 | S6, S7 | Top-10 H(coverage/localization). 멀티타입 `.cs` 커버리지 조용한 소실 + junit/xunit failure_proximity 이미 침묵 파손(시뮬레이션1 드리프트 실현). 파생-사실 오염. |
| 3 | S8 | Top-10 M×2. `errored`를 도구 실패로 오분류(계약상 사용자 결과) + 이중접두 에러코드 — AI 에이전트 소비자가 exit/ok를 오독. wire 계약 위반. |
| 4 | S3 | H. 타임아웃 시 손자 프로세스 고아화·무한 hang·OOM — 국소지만 운영 신뢰성 직격. asyncio_subprocess 단일 지점. |
| 5 | S9, S10 | 데이터 무결성/오보. 툼스톤 부분상태 고착 + 삭제된 run을 head로 노출. S 크기, 즉시. |
| 6 | S4, S5 | 제로-수집 3갈래(부채 c, warning으로 가시화) + Windows 주입/배치 실행(RCE·Windows). S5는 Windows CI 레인 부재로 미검출 표면이라 S44와 조율. |
| 7 | S25, S24 | 크로스컷 SSoT 조기화(fail-like outcome 정본) + 문서 후퇴(부채 a). 조기에 하면 이후 엔진 슬라이스의 drift를 컴파일/테스트 타임에 막고, 문서-코드 불일치 사고(2026-06-25급) 재발을 차단. |
| 8 | S11–S23, S26–S43, S45–S46 | 하드닝·중복제거·per-엔진 정확성. 국소 M/L. 중복제거 슬라이스(S13/S18/S23/S25)는 '7번째 엔진/신규 동사' 시 재복제 클래스를 정적으로 봉쇄. |
| 9 | S44 | equip 갭(carry-forward #4) — multi/infra. 근본 해소지만 CI 매트릭스 변경이라 별 트랙. |
| 10 | S47, S48 | 대형 구조 리팩터. seam 추출 슬라이스가 선행돼야 churn 최소. §5의 'now 하면 손해' 조건 충족 후. |

문단 근거: **정확성이 리팩터를 앞선다.** W1의 10개는 전부 "사용자/에이전트가 잘못된 결과를 신뢰"하거나 "운영 중 hang/OOM/데이터 부분상태"를 만드는 부류로, 국소·저비용 수정이면서 회수가 즉각적이다. 반면 대형 리팩터(S47 app.py 분해, S48 import DAG)는 회수가 '미래 유지비 절감'으로 지연되고 churn 위험이 크므로 뒤로 민다. **중복제거는 중간대**에 배치했다: 그 자체로 버그는 아니지만(현행도 정확·테스트됨) 이미 드리프트가 관측된 클론들(escape 문자셋 3/11/16 발산, failing-outcome에 `"error"` 유입, engine_selector/readiness 두 우선순위 리스트 전례)을 SSoT+divergence-guard로 고정해 **다음 엔진/동사 추가 때의 재복제를 예방**하는 값이 있어, 관련 정확성 슬라이스와 같은 웨이브에 둔다. **문서 후퇴(S24)와 SSoT(S25)를 W2 앞머리에 조기 배치**한 이유는, 그것이 이후 여러 엔진 슬라이스의 전제(정확한 지도 + 단일 outcome 정본)를 세워 병렬 진행 시 상호 충돌을 줄이기 때문이다.

---

## 5. Quick wins (반나절 이하)

아래는 **단독으로 반나절 이하**로 끝나는 슬라이스/항목이다. 팀 여유 사이클에 독립적으로 뽑아도 선행 의존이 없다.

**슬라이스 단위(S 크기, 통째로 quick):**
- **S4**(제로-수집 warning, 부채 c 권고 ③ — engine.py 단일 사이트) · **S9**(툼스톤 원자성) · **S10**(status latest + 파생 플래그) · **S15**(warning slug 분리 + dead code 2건 + readiness 예외 포착) · **S20**(타깃식 lexical 정규화) · **S21**(엔벨로프 as_posix) · **S27**(reset pinned_engine + docstring) · **S28**(CLI dead code + 스냅샷 가드) · **S32**(symbol resolver 캐시/extent) · **S35**(coverage 문서 + 죽은 reason) · **S45**(models/utils 위생)

**더 큰 슬라이스에 묶였지만 개별 cherry-pick 가능한 quick-win findings:**
- Run: [RUN-03](findings/run.md#run-03)(cargo 문서), [RUN-04](findings/run.md#run-04)(as_posix ×4), [RUN-05](findings/run.md#run-05), [RUN-17](findings/run.md#run-17), [RUN-19](findings/run.md#run-19), [RUN-20](findings/run.md#run-20), [RUN-21](findings/run.md#run-21), [RUN-24](findings/run.md#run-24), [RUN-25](findings/run.md#run-25), [RUN-26](findings/run.md#run-26)
- Orchestration: [ORC-02](findings/orchestration.md#orc-02), [ORC-03](findings/orchestration.md#orc-03), [ORC-05](findings/orchestration.md#orc-05), [ORC-17](findings/orchestration.md#orc-17), [ORC-18](findings/orchestration.md#orc-18)
- Analysis: [ANA-07](findings/analysis-engines.md#ana-07), [ANA-08](findings/analysis-engines.md#ana-08), [ANA-13](findings/analysis-engines.md#ana-13), [ANA-16](findings/analysis-engines.md#ana-16), [ANA-17](findings/analysis-engines.md#ana-17), [ANA-23](findings/analysis-engines.md#ana-23), [ANA-25](findings/analysis-engines.md#ana-25), [ANA-26](findings/analysis-engines.md#ana-26)
- Memory/Models/Cross: [MEM-03](findings/memory.md#mem-03), [MEM-04](findings/memory.md#mem-04), [MOD-04](findings/models-utils.md#mod-04), [MOD-05](findings/models-utils.md#mod-05), [XCT-10](findings/cross-cutting.md#xct-10), [XCT-11](findings/cross-cutting.md#xct-11)

주: quick-win이라도 **전부 v0.1.3 이후**다(부채 e — 릴리스 전 소스 무변경).

---

## 6. 지금 하면 손해인 리팩터 (선행조건/불확실성)

부채 판정 `a`~`e`와 정합하는, **현재 착수 시 순손실**인 작업들:

1. **어댑터 데코레이터 레지스트리 도입** (부채 a/d 반대편) — `foundations.md:475`의 "Adding a seventh ecosystem is one PR, one file"는 어느 설계에서도 성립하지 않는 과장이다. 7번째 엔진은 미스케줄(2026-05-25 매트릭스 6개 고정, Vitest/Open Q#7 미결)이고, 레지스트리는 엔진-지식 7개 사이트 중 1곳만 기계적으로 제거한다. 등록 순서를 암묵 우선순위로 삼으면 2026-07-03 결정이 '설계로 사멸'시킨 two-priority-lists 버그 클래스가 부활한다. **올바른 형태는 dict 하우스 패턴(S16)이며 레지스트리는 아니다.** 문서는 후퇴(S24)만.

2. **`normalizer.parse_artifacts`의 adapter-클래스 이관** (부채 a 조건부) — 904줄 normalizer + 6개 어댑터 ~6.5k LOC 재편 churn 대비 회수(7번째 엔진)가 미정. S16의 dict화는 `engine.py` 사다리에 한정하고 이 대규모 재편은 착수하지 않는다.

3. **cli/app.py 대분해(S47)를 릴리스 전 또는 seam 추출 전에** — 1973줄 파일을 릴리스 전에 건드리면 부채 e가 경고한 Windows 회귀 잠복 표면을 키우고 bisect를 오염시킨다. 또한 S8/S17/S22/S23이 이미 여러 seam을 뽑아내므로, 그 전에 통분해하면 이중 작업·충돌이 난다. **릴리스 후 + seam 슬라이스 후**에만.

4. **파생-엔진 import DAG 재설계(S48)를 엔진경계 가드 안정화 전에** — cross-engine 합성 이관은 multi-cycle 구조 변경이라, fail-like outcome SSoT(S25)와 각 엔진 경계 가드가 자리잡기 전에 하면 이동 중 회귀 검출이 약해진다. 엔진경계 가드가 이미 3곳 복제 우회 사이트를 낳은 이력(coverage/localization/orchestration)을 감안하면 SSoT 선행이 필수.

5. **신규 `workspaces` 동사 본체 구현(ORC-11)** — 제품 결정 미스케줄. 총비용 추정 src ~7파일(2 신규) + test ~5 + 문서 ~10파일이고 2개 침묵 등록 사이트를 동반한다. 지금은 **완결성 테스트(S46)만** 값이 있고 동사 본체는 CEO/PM 스코프 결정 전까지 미착수.

6. **v1 wire 필드 rename(`test_id`→`node_id` 통일, MOD-04)** — 스키마 v1 동결 상태라 실제 rename은 schema bump가 필요하다. 지금은 docstring 명시(S45)만; 차기 스키마 정리 시 후보 등록.

7. **v0.1.3 릴리스에 W1 버그 수정을 끼워 넣기** (부채 e) — 검증된 HEAD에 소스를 얹으면 릴리스가 불특정 fast-follow 루프로 지연되고, 행동 변화가 릴리스에 섞여 이분탐색을 오염시킨다. W1 버그는 v0.1.2에도 이미 존재하므로 v0.1.3가 상태를 악화시키지 않는다. **릴리스는 소스 무변경(S0)으로 먼저, 버그 수정은 그 뒤 W1.**

---

## 7. 릴리스 전/후 배치 요약 (부채 e 정합)

- **릴리스 전(v0.1.3 태그 이전): `S0`만.** 소스 무변경 릴리스 컷. HEAD가 CI 10/10·Manual Test 통과·comms 5채널 공백의 검증 지점이므로 그대로 출하.
- **릴리스 직후 W1(10개, 정확성·안전·데이터 무결성):** S1 S2 S3 S4 S5 S6 S7 S8 S9 S10. v0.1.3 태그를 롤백 기준점으로 확보한 상태에서 착수. 원하면 이 중 일부를 v0.1.3.1 fast-follow로 승격 가능(팀 판단, 릴리스 비게이트).
- **W2(36개):** 하드닝·중복제거·per-엔진 정확성·문서 후퇴·SSoT. S24/S25를 앞머리에 조기 배치.
- **W3(2개):** S47(app.py 분해)·S48(import DAG) — 선행 seam/가드 슬라이스 이후.

정합 확인: 부채 `a`(레지스트리 미구현, 문서 후퇴)=S24, `b`+`d`(레거시 분기 제거+dict 하우스 패턴)=S16, `c`(warning+passed)=S4, `e`(릴리스 선행, 대형 리팩터 후행)=S0가 유일 릴리스-전 + S47/S48이 최후미. 이 로드맵의 어떤 배치도 판정 `a`~`e`와 모순되지 않는다.
