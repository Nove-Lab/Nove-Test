# Wave 1 — 정확성·안전·데이터무결성

배치: v0.1.3 릴리스(W0) **직후** · 슬라이스 10개(S1–S10) · 전제: [`../02-roadmap.md`](../02-roadmap.md)

W1은 **"초록은 초록을 뜻한다"** 를 회복한다. 조용한 오답(사용자·AI가 틀린 결과를 신뢰)과 운영 위험
(hang/OOM/데이터 부분상태)을 국소·저비용으로 제거한다. 각 슬라이스는 범위(scope) · 완료후모습(end-state) ·
exit criteria를 갖는다. finding 근거는 리뷰 [`findings/`](../../reviews/2026-07-04-codebase-review/findings/).

> **W0 선행(릴리스):** W1 착수 전 `v0.1.3`가 태그로 확보돼 있어야 한다(롤백 앵커). 릴리스 최소 세트 = `pyproject.toml`
> version `0.1.2→0.1.3`(1파일; **`uv.lock` 없음 — C4**) + PM 작성 `design/release-notes/v0.1.3.md`(anchored-pin 행동
> 변화 = init pin/bare walk-up/신규 exit·에러코드를 breaking-adjacent로 명시) + CEO 런북(release-test dispatch →
> 태그 push → draft 확인 → promote). **W1 버그는 v0.1.3에 미수정 상태로 실린다**(전부 v0.1.2에도 존재, 상태 악화 없음).

---

## S1 · 네이티브 타깃 변환 & argv 위생 — run · 1c

- **findings:** [RUN-01](../../reviews/2026-07-04-codebase-review/findings/run.md#run-01)(H), RUN-22(L)
- **범위:** `target_expression`을 엔진별 올바른 argv로 변환. go의 directory/`.`/nodeid를 `./<rel>/...` ·
  `<pkg> -run '^<Test>$'`로 분해해 `novetest run .`의 무증상 축소 제거(cargo:269/dotnet:1046의 directory 가드와 정합).
  pytest/jest/cargo argv에 `--` 분리자를 넣어 `-`선두 타깃의 플래그 오소비 차단.
- **완료후모습:** `novetest run .`이 하위 패키지 테스트까지 실행하고, 실행 안 된 스위트를 `passed`로 보고하지 않는다.
  bare `novetest run`과 `novetest run .`의 동작이 일치한다. 6엔진 모두 dash-선두 타깃을 positional로 못박는다.
- **exit criteria:** go 하위패키지 픽스처에서 `run .`이 재귀 실행됨을 검증하는 회귀 테스트 + `run ./pkg`가 가짜
  빌드실패 대신 정상 실행. 전체 스위트 green.

## S2 · 실행별 리포트 격리 & readiness 정합 — run · 1c

- **findings:** [RUN-02](../../reviews/2026-07-04-codebase-review/findings/run.md#run-02)(H), RUN-14(M)
- **범위:** JUnit 어댑터가 실행 전 스테이징 리포트 디렉터리를 비우거나 `mtime>started_ms` 필터로 stale `TEST-*.xml`
  차단 — 가장 깨끗한 형태는 Surefire `reportsDirectory`를 per-run artifact_dir로 리다이렉트(persistent-workspace
  의존 제거, dotnet `--results-directory` 방식). dotnet readiness의 test-csproj 필터를 어댑터 `_detect_test_project`와
  동일 토큰(`tests/test/specs/spec`)·정렬로 SSoT화.
- **⚠ 교정 C3:** **Gradle 절반은 착수 시 경험적 확인 필수.** Gradle Test 태스크는 `build/test-results/test`를
  `@OutputDirectory`로 선언해 non-incremental 실행 시 stale-output을 스스로 정리할 개연성 → 없는 문제를 "고치지" 말 것.
  Maven 절반(Surefire 미정리)은 확정 결함.
- **완료후모습:** 전체 실행 후 필터 재실행이 이전 실행의 유령 테스트를 현재 결과로 보고하지 않는다. readiness=ready면
  어댑터가 반드시 같은 csproj를 실행한다(발산 0).
- **exit criteria:** Maven full→filtered 시퀀스에서 stale XML 미유입 회귀 테스트. dotnet readiness↔어댑터 csproj 선택
  일치 divergence 테스트. Gradle 실동작 확인 노트 첨부.

## S3 · 서브프로세스 수명주기 하드닝 — run · 1c

- **findings:** [RUN-15](../../reviews/2026-07-04-codebase-review/findings/run.md#run-15)/[MOD-01](../../reviews/2026-07-04-codebase-review/findings/models-utils.md#mod-01)(H), RUN-27/MOD-02(M)
- **범위:** `utils/asyncio_subprocess.run_subprocess`가 타임아웃 시 프로세스 **트리** 전체 종료(POSIX
  `start_new_session=True`+`os.killpg`; Windows job object/`taskkill /T`; SIGTERM→유예→SIGKILL). stdout/stderr 캡처에
  바이트 상한(초과 truncate+플래그).
- **⚠ 교정 C7:** **양쪽 다 고쳐야 한다.** (1) 트리 kill(고아 방지=RUN-15), **그리고** (2) line-72 gather에 grace
  타임아웃(파이프 드레인 무한블록 차단=MOD-01 hang). hang은 손자가 우리 파이프 write-end를 상속할 때만 발생(jest
  `cmd /c npx` Windows가 구체 캐리어; cargo는 orphan-only). 한쪽만 고치면 나머지 절반이 남는다.
- **완료후모습:** 타임아웃이 손자 테스트 프로세스·JVM·testhost·node 워커를 남기지 않고, run_subprocess가 파이프
  드레인으로 무한 블록되지 않으며, 폭주 출력이 오케스트레이터를 OOM으로 몰지 않는다.
- **exit criteria:** 타임아웃 시 프로세스 트리 종료를 검증하는 테스트(플랫폼 가능 범위) + gather grace 타임아웃 단위
  테스트 + 캡처 상한 truncate 플래그 테스트.

## S4 · 제로-수집 경고(warning+passed) — run · S · [부채 c]

- **findings:** [RUN-12](../../reviews/2026-07-04-codebase-review/findings/run.md#run-12)(M)
- **범위:** `engine.py` normalize 직후 **단일 사이트**에서 `not record.test_results and status=="passed"`일 때
  `AdapterWarning(code="zero-tests-collected")` 추가. envelope 스키마·exit code·persisted record 불변(2026-06-06
  warning 채널 재사용).
- **⚠ 교정 C1:** 이 warning은 **RunRecord를 생산하는 엔진만** 닿는다 → 실제 침묵 초록인 **go/junit/xunit**에 적용되고
  그게 정확히 문제 집합이다. **jest·cargo는 RunRecord 생성 전 typed-error(AdapterInvocationError) raise**라 이 사이트가
  못 닿고, 이미 loud하므로 조치 불요. pytest는 exit5→errored(별건). 따라서 S4는 리뷰가 말한 "3갈래 수렴"이 아니라
  **"침묵 초록 가시화 + 3갈래를 문서로 명시"**다. 리뷰 debt-c 요약의 jest/pytest 오분류도 정정 기록.
- **완료후모습:** go/junit/xunit의 "아무것도 실행 안 됨"이 `passed`로만 조용히 나가지 않고 `zero-tests-collected`
  warning을 동반한다. 제로-수집의 엔진별 3갈래 동작이 문서로 명시된다(신규 status·에러 승격은 이 슬라이스 밖).
- **exit criteria:** go/junit/xunit 빈-타깃 실행이 warning을 방출하는 테스트 + 제로-수집 동작 표 문서화 + jest/cargo가
  이미 typed-error임을 확인하는 주석/테스트.

## S5 · Windows 런처 안전 & 메타문자 주입 방어 — run · 1c

- **findings:** [RUN-09](../../reviews/2026-07-04-codebase-review/findings/run.md#run-09)(M, RCE·Windows), RUN-10(M)
- **범위:** jest `cmd /c` 경로에서 미검증 target의 `&|<>^%"` 메타문자를 usage 오류로 반려(또는 node로 `jest.js` 직접
  exec). junit이 `mvn.cmd/gradle.bat/gradlew`를 `cmd /c` 경유 실행(jest `_npx_launcher` 패턴) + `-Dtest`/`--tests`
  주입 방어.
- **주의:** Windows CI에 junit 레인이 없어 미검출 표면 → **S44(엔진 e2e equip)와 조율**. 침묵 축소 금지: 검증 못 한
  Windows 경로는 그렇게 명시.
- **완료후모습:** 신뢰불가 target(악성 repo 테스트명/파일명)이 Windows 셸 메타문자로 RCE를 유발하지 못하고, junit
  런처가 Windows 배치 셰임을 정상 실행한다.
- **exit criteria:** 메타문자 target 반려 테스트 + (가능 시) Windows junit 런처 경로 검증 또는 미검증 명시 노트.

## S6 · Cobertura 멀티-클래스 병합 — coverage · 1c

- **findings:** [ANA-01](../../reviews/2026-07-04-codebase-review/findings/analysis-engines.md#ana-01)(H)
- **범위:** `cobertura_parser`가 동일 `file_path`의 다중 `<class>`를 덮어쓰지 말고 executed/missing 라인을 합집합
  병합(executed 우선) + per-file summary 재계산. 멀티-XML(per-test forward-compat) last-wins와 충돌하지 않게 **단일
  파싱 세션 내 동일 file_path** 기준 병합.
- **완료후모습:** 멀티타입 `.cs`(C# 관용)의 커버리지가 마지막 타입만 남지 않고 전 타입 라인을 보존한다.
  `percent_covered`/`num_statements`가 네이티브 line-rate와 일치한다.
- **exit criteria:** 파일당 동일 filename `<class>` 2개 회귀 픽스처 + 병합 검증 테스트(현 테스트는 멀티-XML만 커버).

## S7 · failure_proximity junit/xunit 커버리지 + divergence 가드 — localization · 1c

- **findings:** [ANA-02](../../reviews/2026-07-04-codebase-review/findings/analysis-engines.md#ana-02)(H) · 선행 S25 권장
- **범위:** `resolve_failure_text` inline 튜플에 junit/xunit 추가(로그경로 1차 + inline fallback hybrid 분기) +
  `_ENGINE_REGEX_TABLE`에 JUnit(`at pkg.Cls.m(File.java:NN)`)·xUnit 스택 정규식 추가. 두 리스트를
  `list_supported_engine_pairs()` 대비 검증하는 divergence 테스트 신설(readiness `test_engine_selector.py:202-213`
  패턴 복제).
- **주의(ANA-02 caveat):** 이 침묵 파손은 **no-coverage 폴백 모드**(기본 실행) 한정 — `--coverage` 시 정상 SBFL로
  라우팅. 여전히 기본 실행 경로라 H 정당. 오도성 parse_warning("failure_reference empty")도 실제 원인(엔진 미지원)으로 정정.
- **완료후모습:** 기본 실행의 junit/xunit 실패 run에 대한 `localization`이 항상 0건을 내지 않는다. 7번째 엔진 누락이
  테스트 타임에 차단된다.
- **exit criteria:** junit/xunit 실패 run의 failure_proximity가 비어있지 않은 finding을 내는 테스트 + divergence 가드 테스트.

## S8 · 실행 exit/에러코드 계약 수정 — orchestration · 1c

- **findings:** [ORC-03](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-03), [ORC-04](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-04), [ORC-23](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-23)(M/M/L)
- **범위:** `app.py:606/1674`의 이중접두 `engine-engine-missing` 제거(`code=exc.readiness.state`). `errored` 런을
  exit1/ok=False에서 `failed` 계열(ok=True, exit3)로 재분류. status→(ok,exit) 매핑을 단일 헬퍼로 추출해 `run_cmd`와
  `handlers/test.py`(**:83-85에도 동일 버그**)가 공유. markerless 토큰을 D7 표준으로 정렬.
- **완료후모습:** AI 에이전트가 `errors[0].code=="engine-missing"`으로 엔진부재를 정확히 분기하고, `errored`
  스위트를 "Nove Test 도구 실패"가 아니라 사용자 결과로 읽는다. run/test 두 동사가 동일하게 분류한다.
- **exit criteria:** 코드 토큰 계약 테스트(이중접두 부재) + errored→(ok=True,exit3) 테스트 + run/test 대칭 테스트.

## S9 · 툼스톤 원자성 — memory · S

- **findings:** [MEM-02](../../reviews/2026-07-04-codebase-review/findings/memory.md#mem-02)(M)
- **범위:** `store.py` 툼스톤을 rename-후-mutate에서 **mutate-후-단일-rename**으로 뒤집어, 크래시 시
  status/tombstoned_at 불변식 위반 부분상태 제거.
- **완료후모습:** delete 도중 크래시해도 툼스톤 레코드가 `tombstoned_at=None`·원본 status로 고착되지 않는다
  (MemoryEntry 불변식 유지, 재삭제 no-op 고착 소멸).
- **exit criteria:** rename 이전 크래시 시뮬레이션에서 불변식 유지 확인 테스트.

## S10 · status latest & 파생-플래그 신선도 — orchestration · S

- **findings:** [ORC-16](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-16), [ORC-26](../../reviews/2026-07-04-codebase-review/findings/orchestration.md#orc-26)(M/L)
- **범위:** `build_status_view`의 latest 선택에서 tombstone 제외(live 최신을 head로). `test_target_in_store`
  memory_entry가 regression/localization 파생 후 재조회되도록 리프레시 지점 일원화.
- **완료후모습:** `memory delete <최신>` 후 `status`가 삭제된 run을 head로 오보하지 않고, 방금 파생한 결과가
  `*_available` 플래그에 즉시 반영된다.
- **exit criteria:** delete 후 status latest가 live run을 가리키는 테스트 + 파생 직후 플래그 신선도 테스트.

---

## W1 exit criteria (웨이브 전체)

- S1–S10 전부 병합·Manual Test 검증 완료.
- 그 시점 HEAD가 전체 스위트 green + mypy clean + CI 매트릭스 통과.
- 5개 H(RUN-01/02, ANA-01/02, MOD-01) 각각에 대해 "조용한 오답/무한 hang이 재현되지 않음"을 보이는 회귀 테스트 존재.
- (선택) 팀 판단으로 일부 슬라이스를 `v0.1.3.1` fast-follow로 승격 — 릴리스 비게이트.
