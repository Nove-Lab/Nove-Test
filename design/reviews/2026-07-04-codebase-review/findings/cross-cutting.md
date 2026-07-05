# 크로스커팅 (팀 경계를 넘는 항목만) findings

스코프: 단일 엔진/팀 내부로 닫히지 않고 둘 이상의 팀·계층·트랜스포트 경계를 가로지르는 구조·계약·문서·CI 항목만. 집계 — 확정 14건(H 0 / M 9 / L 5), 미확정 0건.

## 확정 findings

<a id="xct-01"></a>
### XCT-01 [M] foundations §5 구조 트리·어댑터 레지스트리 서술이 실제 파일 레이아웃과 대량 불일치
- **근거**: `design/implementation-plan/foundations.md:318` — :318은 "Native engine adapters via decorator-based registry behind a NativeAdapter Protocol"라 하고 :448-475는 `_REGISTRY`/`@register` 코드를 제시하나, 실제 디스패치는 `src/novetest/run/engine.py:149-204`의 if-elif이고 `adapters/`에 base.py나 레지스트리 __init__가 없다. §5 파일 트리 다수가 실파일과 어긋남: :358 `pytest_.py`/:362 `cargo.py` → 실제 `*_adapter.py`; :418-419 `utils/paths.py`,`utils/logging.py` → 실제 `utils/path_utils.py`이고 logging.py 부재; :331-332 `cli/target.py`,`cli/identity.py` → 실제 cli는 handlers/+renderers/, identity는 orchestration/onboarding/identity.py; :337 `workflows/integrated_test.py` → test.py; :347 `orchestration/eligibility.py` 부재(anchor_resolution.py 존재); :366-369 `memory/run_repository.py`,`tombstone.py` 부재; :375-382 `coverage/parsers/*` 서브디렉토리 부재(flat); :386 `regression/latest_baseline.py` 부재; :396 `localization/modes.py` 부재; :399-401 replay `replay.py/reconstruct_context.py/classify.py` → engine.py/context.py/classifier.py; :414 `models/migrations.py` 부재. 또한 :294는 현재시제로 `upgrade_run_record` 마이그레이션을 서술하나 find/grep 공집합.
- **실패 시나리오**: delivery-phasing.md:24가 "Project skeleton matching foundations.md#5-project-structure"로 §5를 레이아웃 권위로 지시한다. 이를 권위 소스로 삼은 에이전트가 adapters/base.py, coverage/parsers/lcov.py, models/migrations.py 같은 미존재 경로를 열거나, 디스패치를 decorator registry로 오모델링(실제 engine.py:149-204 if-elif)한다. 2026-06-25 문서-코드 불일치 사고 이력이 이 부류 드리프트의 실제 사고 전례.
- **권고**: §5 트리(322-440)와 §"Adapter registry"(448-475)를 실제 `*_adapter.py` + engine.py if-elif 디스패치로 재작성하고, :294 migrations 현재시제 서술을 'schema v1 frozen, 마이그레이션 미구현'으로 정정. 최소한 §5 상단에 '지도는 참고용, engine.py가 실 디스패치 SSoT' 캐비앗 추가. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 전부 직접 Read 확인. adapters/__init__.py는 빈 파일, run/ 전체에 _REGISTRY/@register/NativeAdapter 히트 0, base.py 부재; 실 디스패치는 engine.py:149-204 if-elif. 대상이 런타임 미소비 설계문서라 H 아닌 M(드리프트·오모델링 위험).

<a id="xct-02"></a>
### XCT-02 [M] CLI 트랜스포트가 localization 엔진 소유 디렉토리를 직접 unlink + 캐시무효화 도메인 로직 보유
- **근거**: `src/novetest/cli/app.py:1390` — :43 `from novetest.localization.persistence import localization_findings_path`는 localization/__init__.py 공개 __all__(106-135)에 없는 엔진 내부 모듈 reach-in. `_rederive_if_cache_overrode_flags`(:1278-1400)가 Defect-5 캐시무효화 규칙과 Defect-7 failure_proximity placeholder carve-out(:1372-1383)을 담고, :1390에서 `localization_findings_path(store, run_id).unlink(missing_ok=True)`로 `<store>/localization/findings/run_<id>/localization_findings.json`(persistence.py:5,36)을 직접 삭제 후 :1391에서 derive_localization_findings 재호출. docstring :1185는 이를 'the orchestration layer invalidates the cache'라 부르나 물리적으로 cli/에 상주. foundations.md:289 'peer 엔진 디렉토리 reach-in 금지', :492 'no business logic in cli/'.
- **실패 시나리오**: localization 팀이 온디스크 레이아웃(findings 파일명/구조, 또는 캐시 정책 자체) 리팩터 시 CLI의 하드코딩 unlink 경로가 stale 파일을 남기거나 엉뚱한 경로를 삭제 — 엔진은 계약대로 동작하는데 트랜스포트가 뒤에서 FS를 훼손. 또한 Phase 7 MCP 트랜스포트는 이 캐시무효화 정책을 재사용 불가(cli/app.py에만 존재)해 재구현해야 하고 두 트랜스포트가 발산.
- **권고**: 캐시무효화를 localization 엔진 공개 API(derive에 force 인자 추가 또는 invalidate_localization_findings(store, run_id))로 흡수하고, explicit-flag 판별 정책은 orchestration/workflows 로컬라이제이션 워크플로로 이관. CLI는 파싱→워크플로 호출→직렬화만 남기고 localization_findings_path import 제거. **(예상 크기: 1-cycle)**
- **검증 노트**: 계층 위반·reach-in write는 코드상 명백(confirmed). 현재 canonical helper·missing_ok=True·직후 재파생으로 완화돼 활성 데이터손상은 없고 장래 리팩터·MCP 발산 위험이라 M.

<a id="xct-03"></a>
### XCT-03 [M] 저장소 손상(record.json 파손)이 read 계열 동사에서 exit 5가 아닌 exit 1·cli-error로 누출
- **근거**: `src/novetest/memory/store.py:277` — 모든 read 동사(memory list/show/delete, coverage show/diff, regression compare/latest, localization, inspect, compare, replay)는 list_run_history/retrieve_run_evidence/_resolve→_read_record로 수렴하고, _read_record(:275-277)는 json.loads(raw)를 무방어 호출. 파손 JSON의 JSONDecodeError는 어느 핸들러에서도 미포착(핸들러는 RunEvidenceNotFoundError/ProjectStoreCorruptError만 catch)되어 main() 광역 except(app.py:1964-1973)로 떨어져 code='cli-error', exit 1(EXIT_GENERIC). 대조: 해석 seam의 ProjectStoreCorruptError는 app.py:169-177에서 EXIT_STORAGE(5)/store-corrupt로 정확 매핑.
- **실패 시나리오**: 디스크의 record.json 손상(부분 기록/수동 편집) 상태에서 `novetest memory show <id>`/`novetest inspect <id>` → json.loads가 JSONDecodeError → exit 1, message는 원시 파이썬 예외 문자열. 동일 손상 부류가 store.json/pin이면 exit 5·store-corrupt, run record.json이면 exit 1·cli-error로 갈려 exit 5 계약이 read 경로에서 무효.
- **권고**: _read_record가 json/구조 오류를 ProjectStoreCorruptError로 감싸도록(project_store.py가 store.json에 이미 하는 방식) 하고, read 동사들이 이 예외를 EXIT_STORAGE로 매핑. memory raise 타이핑 + cli catch 두 팀이 걸려 cross-cutting. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 전부 실재·일치. store.json 파손은 project_store.py:334-339에서 ProjectStoreCorruptError로 명시 래핑되나 record.json 파손 경로는 무방어 — 같은 손상 부류의 exit 5 vs exit 1 비대칭이 코드상 성립.

<a id="xct-04"></a>
### XCT-04 [M] 보편 읽기 해석 seam이 D6 backfill로 store.json을 비원자적으로 rewrite — 읽기 동사가 스토어 오염 가능
- **근거**: `src/novetest/orchestration/anchor_resolution.py:155` — resolve_workspace가 legacy 단일-마커 스토어에서 set_pinned_engine을 호출(:155), resolve_execution_engine도 동일(:191). set_pinned_engine은 project_store.py:313-318 경유 :357 `metadata_path.write_text(...)` 단일 비원자 쓰기(docstring :295-297도 'single write_text' 명시). 이 seam(_require_store)은 status(app.py:688) 등 순수 읽기 동사가 모두 경유.
- **실패 시나리오**: legacy pin-less 스토어에서 `novetest status`(읽기 전용)→resolve_workspace→set_pinned_engine→write_text가 store.json truncate 후 재기록. 이 사이 SIGKILL/전원차단(원자 rename 없음)이나 병렬 읽기 동사 write_text 인터리브 시 store.json이 torn 상태가 되고 다음 동사가 _read_metadata에서 ProjectStoreCorruptError→store-corrupt(exit 5). 읽기 전용 동사가 스토어를 손상시키는 불변식 위반.
- **권고**: D6 backfill 쓰기를 (a) 원자 temp-write+rename으로 전환(memory 소유 _write_metadata), (b) 읽기 전용 동사 경로에서는 backfill 지연/생략(실 pin 필요한 init/execution 동사에서만 write)하도록 seam 분리. 최소한 원자 쓰기 보강은 모든 store.json write에 이득. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 실재·일치. detach 경로는 :421에서 원자 rename을 쓰나 backfill write_text는 비원자. 노출이 pin 백필 전 1회 마이그레이션으로 한정되고 torn write 저확률이라 M.

<a id="xct-05"></a>
### XCT-05 [M] "failing outcome" 집합이 6+개 사이트에 흩어져 정의되고 1곳이 이미 드리프트("error" 추가)
- **근거**: `src/novetest/orchestration/recommendation/fact_bundle.py:284` — '실패 판정 outcome'이 독립 정의: localization/failure_proximity.py:70, derive.py:101, retrieval.py:32, replay/classifier.py:55, regression/compare.py:66 모두 frozenset({"failed","errored"}); run/normalizer.py 인라인 튜플 다수(164,208,288,329,+703,755,833,895). 그런데 fact_bundle.py:284 `_is_fail_outcome`만 `{"failed","error","errored"}`로 세 번째 철자 "error"를 추가 포함 — 나머지 전부와 불일치. 정본 vocabulary는 models/test_result.py:24가 `passed|failed|skipped|xfailed|xpassed|errored`("error" 없음)로 명시하며 enum-lock 안 함을 선언.
- **실패 시나리오**: test_result.py:24가 outcome을 enum-lock 안 하므로 신규/방어파싱 엔진이 "error"(단수)를 emit하는 순간: recommendation은 _is_fail_outcome이 실패로 계수→has_failed_tests=True→실패-계열 추천 발동. 반면 같은 run을 localization/derive.py:169-170의 _FAILED_OUTCOMES는 미포함→LocalizationUnavailable(no-failed-tests), regression·replay도 미포함. 결과: 같은 run에 대해 "실패했다"(추천)와 "실패 0개"(localization/regression)가 동시 방출되는 envelope 자기모순. 한 정의만 고쳐 vocabulary 확장 시 나머지 5곳 누락 드리프트가 구조적으로 보장됨.
- **권고**: models/test_result.py(또는 models 공용)에 `FAIL_LIKE_OUTCOMES: frozenset[str]` 단일 정본을 두고 6+개 소비자가 전부 import. fact_bundle의 "error" 포함 여부는 이 지점에서 정책 결정. 정본==각 소비자 집합 pin하는 divergence-guard 테스트 추가(engine_selector 레지스트리 guard와 동형). **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 전부 Read 확인. normalizer 인라인 튜플은 인용 4곳보다 많은 8곳으로 '흩어짐' 더 강하게 성립. 완전 자기모순은 신규 엔진 "error" emit + summary_counts.failed 누락 이중 조건에 게이팅(현재 가설)이나, 이미 발생한 드리프트라는 핵심 사실이 확정되어 M.

<a id="xct-06"></a>
### XCT-06 [M] 파생 엔진 간 직접 import DAG (regression→coverage, localization→coverage+regression) — 합성이 orchestration 밖에서 발생
- **근거**: `src/novetest/regression/compare.py:572` — regression/compare.py:30이 coverage.compare.compare_coverage_facts를 import해 :572에서 호출(CoverageDelta 임베드); retrieval.py:30이 coverage.compare.SCHEMA_VERSION import. localization/derive.py:39-40이 coverage.retrieval/results, :80-82가 regression.compare.resolve_baseline_for_run·regression.results·regression.retrieval import. 컴파일타임 DAG: coverage ← regression ← localization, coverage ← localization. orchestration/ 하위에 compare_coverage_facts/_maybe_coverage_change 호출 0건이라 합성이 orchestration 밖에서 발생.
- **실패 시나리오**: coverage.compare 시그니처/의미(엔진필터 도입, unavailable reason 확장) 변경 시 regression·localization 두 소비자에 동시 파급되고, 새 소비자가 D5 엔진경계 가드를 누락하면 혼합엔진 스토어에서 무의미한 delta/재가중이 조용히 재발(실제 3회 재발한 클래스). foundations.md:289는 디렉토리 reach-in만 금지(공개 API 호출은 회색지대)라 강한 규칙 위반은 아니나 cross-engine fact 합성이 mediating 계층 없이 산재.
- **권고**: cross-engine fact 합성(coverage delta 임베드, regression prior 재가중)을 orchestration이 주입하거나 공유 selector 하나로 엔진경계 가드를 SSoT화. 최소한 소비자는 각 엔진 공개 __init__ 심볼만 바인딩하고 내부 서브모듈(regression.compare 등) 직접참조를 끊는다. **(예상 크기: multi-cycle)**
- **검증 노트**: 구조 evidence 전부 확증(import DAG·orchestration 밖 합성). coverage/__init__.py가 심볼을 공개 export함에도 소비자가 서브모듈 직접 참조. D5 3중 복제 특정 커밋 이력은 브리핑 의존이라 미확인이라 uncertain→final confirmed, M.

<a id="xct-07"></a>
### XCT-07 [M] 비단조 ULID + ms 단위 created_at → 동일-ms 형제 run의 정렬/baseline 선택이 비결정적
- **근거**: `src/novetest/utils/ulid.py:49` — generate_ulid(:49-53)는 매 호출 완전 랜덤 80비트 suffix만 붙이고 동일-ms 단조 증가 보장 없이 time.time() 벽시계를 ms 절단. reference.py:24는 created_at=extract_timestamp_ms(ulid)로 ms prefix에서 파생. memory/store.py:116(list_run_history), :152(find_runs_for_target)는 created_at 단일 키 reverse 정렬만(2차 tiebreak 없음), 정렬 전 순서는 rglob FS 순서. regression/compare.py:633 resolve_baseline_for_run은 이 newest-first 순서에 의존해 첫 생존자를 baseline으로 선택.
- **실패 시나리오**: replay/engine.py:79-114가 tight loop로 run_id=generate_ulid()를 만들고 각 rerun을 원본과 동일 target_expression 정규 record로 저장 → 다중 rerun이 손쉽게 같은 ms에 떨어져 동일 created_at. 이후 find_runs_for_target/list_run_history가 형제를 동률 반환하며 stable-sort가 rglob 순서를 보존해 실행·플랫폼마다 달라짐 → memory list 순서, inspect/status, resolve_baseline_for_run이 고르는 baseline이 비결정적 → 동일 target의 regression_facts.json 내용이 run마다 달라질 수 있음(NFR-REG-001 위배). 벽시계 역행(NTP) 시 나중 run이 더 작은 created_at을 받는 오정렬 경로도 성립.
- **권고**: memory/store.py 두 정렬에 run_id(또는 entry_id)를 2차 tiebreak로 추가(key=(created_at, run_id))하고 resolve_baseline_for_run도 동일 규약 명시. 실행순서 정확 반영엔 동일-ms 단조 ULID나 sub-ms 필드 도입. assign_run_reference 밖 경로의 created_at==extract_timestamp_ms 불변식 방어 검증도 고려. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 전부 실재·일치. compare.py:636-639의 >= 비교가 target 동률 형제를 제외하나 이는 target 시점 한정이고, 다중 오래된 동일-ms 형제 및 resolve_latest_baseline head 클러스터 동률은 여전히 비결정적. flaky 탐지 시 동률 형제 outcome이 갈리면 임의 선택이 유의미. M.

<a id="xct-08"></a>
### XCT-08 [M] 실 엔진 e2e는 전부 shutil.which로 skip-gated + 어댑터 유닛은 subprocess seam을 stub → 기본 CI는 go/cargo/dotnet/junit·lcov/cobertura/jacoco에 실 subprocess 신호 0
- **근거**: `tests/integration/run/test_cargo_basic.py:61` — 어댑터 유닛은 실 엔진을 절대 스폰 안 함: test_cargo_adapter.py:5-12 "stubs the subprocess seam via monkeypatch on ...run_subprocess", :51에서 shutil.which를 _FAKE_CARGO로 대체, canned NDJSON 재생(test_gotest_adapter.py:5, test_dotnet_adapter.py:5 동일). 실 바이너리 경로인 통합 테스트는 shutil.which로 skip: test_cargo_basic.py:61-64, test_dotnet_basic.py:56-57, test_gotest_basic.py:26-27, test_junit_maven.py:40-49(모듈레벨 skipif). CI 매트릭스는 python+node만 장착(.github/workflows/ci.yml:4, :56-58 setup-node만). test_cargo_basic.py:4-8 주석 "CI has no Rust cell → skip on every runner".
- **실패 시나리오**: cargo_adapter argv(`cargo nextest --message-format=libtest-json`)나 nextest 스키마가 바뀌면(Open Q#3 미해결) test_cargo_adapter.py는 옛 canned 바이트를 stub된 seam에 재생해 green, 실 바이너리 검증 test_cargo_basic.py는 매 CI 셀에서 shutil.which is None→skip→PR green 머지, 파손은 로컬 equip 호스트에서만 드러남. dotnet_adapter(1513 LOC 최대 어댑터)·gotest도 동일하며 Manual Test 호스트가 go+dotnet 3사이클 미장착이라 이 두 어댑터는 파이프라인 어디에서도 실 e2e 미실행. Windows 경로 버그 2건이 'Linux pre-merge 게이트가 구조적으로 못 잡음'과 동형.
- **권고**: CI 매트릭스에 go/cargo/dotnet/java 셀(최소 1 OS) 추가하거나, 장착 셀에서 skip→fail 승격 가드(NOVETEST_REQUIRE_ENGINES) 도입. 최소한 go+dotnet은 어딘가 한 호스트에서 상시 e2e가 돌도록 equip 갭 폐쇄. **(예상 크기: multi-cycle)**
- **검증 노트**: 사실 전부 확인(refute 불가). H→M 조정: 능동 버그가 아닌 CI 커버리지/드리프트 갭이고, 피해 실현엔 외부 포맷 drift+실파손+출고 전 로컬 e2e 미실행 3중 조건 필요. 갭이 ci.yml/docstring에 명시 추적되고 cargo/java는 equip 호스트에서 e2e가 돌아 '인지·추적 중'이라 M.

<a id="xct-09"></a>
### XCT-09 [M] 엔진 게이트가 pytest.skip(≠fail)이고 최소 장착-엔진 수 assert가 없어 돌아야 할 테스트의 조용한 skip 퇴화가 불가시
- **근거**: `tests/integration/run/test_jest_basic.py:38` — 모든 엔진 게이트가 런타임 pytest.skip 또는 skipif이며 xfail/fail 아님. test_jest_basic.py:33-43은 node/npx 및 fixture의 node_modules/.bin/jest 존재까지 검사하고 없으면 :38-43 pytest.skip. CI는 node가 유일 장착 네이티브 엔진(ci.yml:56)이고 jest node_modules 설치는 pytest 앞단(ci.yml:60-65). skip 카운트 상·하한 assert나 "이 셀에서 엔진 X 반드시 present" assert가 전무.
- **실패 시나리오**: ci.yml의 jest npm install 스텝 회귀나 fixture 경로 변경 시 test_jest_basic.py:38 local_jest.exists()가 False→pytest.skip→CI가 유일 실행하던 네이티브 커버리지 경로(istanbul_parser)까지 신호 상실. 스위트는 green 유지, skip 카운트만 조용히 증가(13 skipped 베이스라인 무가드)해 어떤 게이트도 퇴화를 알리지 않음.
- **권고**: 장착 보장 엔진(CI의 jest)은 skip→fail 승격 조건부 가드(CI=1 && NOVETEST_REQUIRE_JEST 시 skip 금지) 추가, skip 카운트 상·하한 assert로 드리프트 가시화. **(예상 크기: 1-cycle)**
- **검증 노트**: 코드 일치 확인. ci.yml:55-58이 9개 매트릭스 셀 전부 Node 설치, npm install이 pytest 앞단이라 실제 jest 실행. test_jest_coverage.py:37,50-51 동일 가드로 istanbul 경로도 함께 침묵. skip 카운트/present assert/terminal_summary 훅 전무 grep 확인. M.

<a id="xct-10"></a>
### XCT-10 [L] perf NFR 테스트가 non-blocking(continue-on-error + 필수 체크 아님) — NFR-COV-002/LOC-002 천장 사실상 미시행
- **근거**: `.github/workflows/ci.yml:135` — perf job은 :132-135 continue-on-error: true, :122 주석 "not on branch protection's required-status-check set", perf는 testpaths 밖이라 기본 스위트 미수집(:116-117, :152에서만 tests/perf 실행). test_perf_compare.py:68 BUDGET_SECONDS=3.0(assert median<3.0), test_perf_derive_aggregate.py:34 BUDGET 5.0.
- **실패 시나리오**: compare_coverage_facts에 O(n²) 스캔이 재유입돼 50k 로케이션에서 3s/5s 예산 초과 시 perf job은 red지만 continue-on-error가 워크플로를 green으로 유지하고 필수 체크도 아니라 PR 머지 → 아무 게이트도 발화하지 않은 채 NFR 회귀가 릴리스되어 사용자는 느린 coverage diff/localize를 겪음.
- **권고**: perf를 required-but-generous(천장의 2~3배 하드 실패선)로 승격하거나 최소한 회귀 알림을 붙여 advisory-only 상태 해소. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: 인용 실재. continue-on-error:true는 job failure에도 workflow conclusion을 success로 만들어 필수/비필수 무관하게 perf 회귀가 머지를 차단 못 함. 데이터손상·소비자 오도 아닌 프로세스 위생 갭이라 L.

<a id="xct-11"></a>
### XCT-11 [L] CLAUDE.md 구조 블록이 실존하지 않는 src/novetest/mcp/를 등재
- **근거**: `CLAUDE.md:42` — ":42 "└── mcp/  # MCP transport (post-MVP)"가 구조 트리에 포함되나 `ls src/novetest/mcp`는 부재(실제 하위: cli/coverage/localization/memory/models/orchestration/regression/replay/run/utils). foundations.md:421/:484도 mcp/를 등재하며 delivery-phasing.md:261-278 Phase 7은 DoD 미체크로 미구현 정직 표기.
- **실패 시나리오**: CLAUDE.md Structure 블록은 모든 에이전트 컨텍스트에 상시 주입되는 권위 파일 지도. 이를 따라 `cd src/novetest/mcp`하거나 MCP 트랜스포트를 grep하는 에이전트는 아무것도 못 찾음. Phase 7 미착수라 실제 부재가 맞지만 지도는 '(planned/absent)' 표기 없이 실존 디렉토리처럼 나열. post-MVP 라벨이 붙어 저심각.
- **권고**: CLAUDE.md:42(및 foundations.md:421) mcp/ 항목에 '(Phase 7, 미구현)' 마커를 달거나 구현 전까지 트리에서 제거해 실 소스 레이아웃과 일치. **(예상 크기: quick-win)**
- **검증 노트**: CLAUDE.md:42 직접 확인, `ls src/novetest/`에 mcp 부재 확인. "(post-MVP)" 라벨이 있어 완전 오도는 아니나 명시 마커 없는 위생 드리프트라 L.

<a id="xct-12"></a>
### XCT-12 [L] 파생 엔진 27개 import가 Memory 공개 surface를 우회하고 내부 서브모듈(store/project_store)에 직접 바인딩
- **근거**: `src/novetest/memory/__init__.py:35` — :35-54가 ProjectStore·retrieve_run_evidence·store_run_evidence·RUN_DIR_PREFIX 등을 공개 __all__로 노출(docstring:3 'Public surface mirrors ... memory.md'). 그러나 coverage/regression/localization/replay 전반에서 `from novetest.memory.store import ...`/`project_store import ...` 27건, 공개 `from novetest.memory import ...`는 이들 4엔진 내 0건. 예: coverage/availability.py:39-40, regression/compare.py:32-33, localization/derive.py:63-64, replay/engine.py:28-29. (대조: run 엔진은 orchestration/replay가 공개 novetest.run 경유 일관 소비.)
- **실패 시나리오**: Memory 팀이 내부 모듈 재편(retrieve_run_evidence를 store.py에서 분리, project_store.py 분할) 시 공개 __all__에 이미 있는 심볼임에도 다운스트림 import가 전부 깨짐 — 패키지 경계가 리팩터 절연을 제공 못 하고 __all__이 장식용으로 전락.
- **권고**: 파생 엔진 import를 `from novetest.memory import ...` 공개 경로로 통일, 내부 서브모듈 참조 금지 lint/리뷰 체크 추가. 비공개 심볼은 __all__에서 명시 배제. **(예상 크기: 1-cycle)**
- **검증 노트**: 27건/0건 수치 일치, 인용 4예시 줄번호 일치. 이동 심볼 부분집합만 깨진다는 점에서 "27개 전부" 경미 과장이나 핵심 유효. 단일 배포판 내부 결합, import 에러로 즉시 발각되는 기계적 수정이라 L.

<a id="xct-13"></a>
### XCT-13 [L] Memory→Run 레이어 역전(deferred import) + 'supported engine pairs' SSoT가 run 엔진에 매립
- **근거**: `src/novetest/memory/project_store.py:304` — set_pinned_engine이 :304에서 함수-로컬 `from novetest.run.engine_selector import list_supported_engine_pairs`로 run을 상향 호출해 pin 유효성 검증(:306-312). 주석 :299-303이 'importing inside the function keeps Memory import-light ... this is a layering courtesy'로 역전 자인. 동일 SSoT(run/engine_selector.py:50-58 _SUPPORTED_PAIRS)를 cli/app.py:87도 소비 — 지원 (ecosystem, engine) 쌍 도메인 상수가 run 내부에 있는데 memory·cli가 필요로 함.
- **실패 시나리오**: 향후 run 계열(readiness가 pin 검증하려 memory import)에서 반대 방향 의존이 생기면 이 deferred import가 실제 순환의존으로 전환돼 로드순서 취약성 발생, 같은 지연-import 우회를 역방향으로 또 심어야 함. 지원쌍 목록 변경 시 소유권이 run에 있어 memory 검증 의미가 run 배포에 결합.
- **권고**: list_supported_engine_pairs 지원쌍 상수를 models/(또는 공유 config)로 승격해 run·memory·cli가 동등 계층 참조하게 하고 memory→run 상향 import 제거. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 실재·일치. 현재 순환 없으나(run이 memory 미import) deferred import가 역전 은폐+상수 소유권 run 결박은 성립. finding이 묶은 readiness.py:49는 intra-layer라 역전 사례 아님(핵심 주장 무관). 기능버그·데이터손상 없어 L.

<a id="xct-14"></a>
### XCT-14 [L] *-coverage 픽스처는 본체 복제가 아닌 별개 SUT(중복 우려 근거 없음) — 다만 CI 미실행 SUT 다수로 유지비>신호
- **근거**: `tests/fixtures/projects/pytest-coverage/tests/test_classifier.py:12` — base와 *-coverage는 별개 SUT: gotest-basic(math.go/math_test.go) vs gotest-basic-coverage(arithmetic.go+classifier.go); cargo도 lib.rs vs arithmetic.rs+classifier.rs. pytest-coverage/tests/test_classifier.py:12는 "The negative branch (value < 0) is deliberately left uncovered to exercise the Coverage engine's missing_lines/missing_branches paths"로 의도된 미커버 분기 문서화. 즉 5개 언어×{basic,coverage}+localization 3변형 ≈ 13개 손수 divergent SUT이며 XCT-08대로 pytest/jest 외 전부 skip-gated라 CI 신호 0.
- **실패 시나리오**: (비용) supported-engine-matrix floor/ceiling 상향마다 ~13개 divergent SUT를 equip 호스트에서 손으로 재검증해야 하고, 8개 이상은 CI에서 절대 안 돌아 픽스처와 어댑터 기대 간 드리프트(픽스처 Cargo.lock·csproj TargetFramework가 어댑터 파싱 가정 대비 낡음)가 조용히 누적돼 수동 equip-and-exercise 사이클에서만 뒤늦게 발견.
- **권고**: 'coverage=본체 중복' 전제는 근거 없음(별개 SUT)임을 확정하고, CI 미실행 픽스처 유지비는 XCT-08의 엔진 셀 추가와 묶어 처리(장착 셀 없으면 유지비>신호). 불필요 변형은 통합 검토. **(예상 크기: 1-cycle)**
- **검증 노트**: 픽스처가 divergent SUT임 직접 확인('본체 복제' 전제 무근거). 드리프트 예시 파일(Cargo.lock, csproj net8.0) 실존. 유지비>신호 논리는 XCT-08 의존하나 로컬 증거와 일관. AI 오판·데이터손상 아닌 유지비 위생이라 L.

## 미확정 관찰
없음.
