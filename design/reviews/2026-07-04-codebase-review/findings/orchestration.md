# Orchestration findings

스코프: `src/novetest/cli/`(transport·envelope·exit code 배선)와 `src/novetest/orchestration/`(workflows, recommendation, onboarding, anchor_resolution)의 계약 정합·중복·경계·엔벨로프 위생 검토. 집계 — 확정 27건(H 0 / M 16 / L 11), 미확정 0건.

> 링크 규약: 앵커는 sibling finding 문서와 동일한 `<a id="orc-NN"></a>` 규약을 따른다(`00-summary.md` Top-10의 `#orc-04`/`#orc-03`/`#orc-16`, `roadmap.md`의 `#orc-01`..`#orc-27` 참조가 이 파일에서 성립한다). 모든 file:line은 이 리뷰 세션에서 `Read`로 직접 연 지점을 인용한다.

## 확정 findings

<a id="orc-01"></a>
### ORC-01 [M] `cli/app.py`가 1973줄 단일 파일에 argv 진입점·엔진 outcome 투영·localization 캐시정책·onboarding 리퓨절 빌더를 모두 적재
- **근거**: `src/novetest/cli/app.py:1` — 파일 총 1973줄(`wc -l` 실측)에 `@app.command` 정의(run_cmd:559, test_cmd:1591, status/memory/coverage/compare/inspect/reset 등), per-engine outcome 프로젝터(`_coverage_outcome_payload:655`·`_regression_outcome_payload`·`_localization_outcome_payload`·`_replay_outcome_payload`), localization 캐시-무효화 정책(:1183-1350), init/reset D7 리퓨절 엔벨로프 빌더(`_no_engine_detected_envelope:351`·`_reset_refusal_envelope`), run_id 해석(:854)이 한 모듈에 공존한다. 저장소 최대 파일이며 여러 팀 관심사(transport / orchestration workflow / recommendation)가 절단선 없이 섞여 있다.
- **실패 시나리오**: 한 동사 배선을 고치려는 개발자가 1973줄에서 관심 절단선을 찾아야 하고, localization 캐시정책(orchestration 관심사)과 엔진 프로젝터(중립 투영)가 CLI transport에 물려 있어 리팩터·리뷰의 blast radius가 파일 전체로 번진다. 후속 seam 슬라이스(S8 exit 계약, S17 예외 매핑, S22 localization 이관, S23 프로젝터 통합)가 각각 이 파일을 터치하므로 통분해를 먼저 하면 이중 작업·머지 충돌이 난다.
- **권고**: 절단선대로 분해 — argv 진입점군→`cli/entrypoint.py`, per-engine 투영군→`handlers/`, localization 캐시정책→orchestration 워크플로, init/reset 리퓨절 빌더→`handlers/onboarding.py`. 잔여 `app.py`는 `@command` 정의 + 얇은 seam ~700줄대. **선행 seam 슬라이스(S8/S17/S22/S23)가 여러 절단면을 먼저 추출한 뒤 착수해야 churn·충돌 최소.** **(예상 크기: multi-cycle)**
- **검증 노트**: 파일 총 1973줄과 인용 심볼 위치(run_cmd:559, test_cmd:1591, `_coverage_outcome_payload:655`, localization 캐시정책 :1183-1350, `_no_engine_detected_envelope:351`, `_resolve_run_reference:854`) 직접 확인. 구조 결함(대형 monolith)이라 기능 오작동은 아니며, 리팩터 회수가 지연되고 churn 위험이 커 W3로 미룸 → M 적정.

<a id="orc-02"></a>
### ORC-02 [M] `run_cmd`/`test_cmd`가 3개 실행 예외 매핑(EngineAmbiguous/EngineNotReady/AdapterInvocation)을 verbatim 복붙
- **근거**: `src/novetest/cli/app.py:585` — `run_cmd`의 `except EngineAmbiguousError`(:585)/`except EngineNotReadyError`(:598)/`except AdapterInvocationError`(:613) 3-블록이 `test_cmd`의 동일 3-블록(:1655/:1666/:1681)과 엔벨로프 구성·에러코드·exit까지 동일하게 반복된다. 두 곳 모두 EngineNotReady를 `code=f"engine-{exc.readiness.state}"`(:606/:1674) + `EXIT_ENGINE_MISSING`으로, AdapterInvocation을 `code=f"adapter-{exc.kind}"` + `EXIT_ENGINE_MISSING`으로 매핑한다.
- **실패 시나리오**: 실행 동사가 3번째로 늘거나(예: 향후 `replay`가 같은 예외 계열을 CLI에서 매핑) 에러코드 계약이 바뀔 때, 두(이상의) 복붙 사이트를 동기 수정해야 하며 한 곳을 놓치면 동사별로 다른 코드/exit가 방출되는 드리프트가 생긴다(ORC-03의 이중접두 버그가 이미 두 사이트에 동일하게 복제된 것이 그 증거).
- **권고**: `_map_execution_exception(command, exc)->(Envelope, int)` 공유 헬퍼로 3개 except를 수렴하고, `run_cmd`/`test_cmd`가 이를 호출. EngineAmbiguous TOCTOU 분기도 흡수하고 RunEngineError 계열을 구조적으로 매핑(EngineNotSupported→exit4). **(예상 크기: quick-win)**
- **검증 노트**: `run_cmd` :585/:598/:613과 `test_cmd` :1655/:1666/:1681 두 except 트리플을 직접 대조, 엔벨로프·코드·exit 동일 확인. 순수 중복(현행 정확·테스트됨)이나 동기-수정 부담 + 실증된 복제 드리프트(ORC-03) → M 적정.

<a id="orc-03"></a>
### ORC-03 [M] 엔진-미준비 에러코드가 이중접두 `engine-engine-missing`으로 방출 — D7 계약 토큰과 불일치
- **근거**: `src/novetest/cli/app.py:606` — `EngineNotReadyError` 매핑이 `code=f"engine-{exc.readiness.state}"`인데, `readiness.state`의 실제 값은 이미 `"engine-missing"`(`src/novetest/run/readiness.py:82,154,270,388,484`) 또는 `"engine-misconfigured"`(readiness.py:138 등)이다. 따라서 방출 코드는 `"engine-engine-missing"`/`"engine-engine-misconfigured"`로 접두가 이중 부착된다. 동일 버그가 `test_cmd`의 :1674에도 복제되어 있다.
- **실패 시나리오**: 계약대로 `errors[0].code == "engine-missing"`로 분기하려는 AI 에이전트/스크립트가 실제 방출값 `"engine-engine-missing"`과 절대 매치하지 못해 엔진 부재를 '알 수 없는 실패'로 오분류한다. wire 계약(D7 토큰 `no-engine-detected`/`engine-missing`)과 실제 방출 토큰이 어긋난다.
- **권고**: `code=exc.readiness.state`로 접두를 제거(state가 이미 완성 토큰). 동일 수정을 :606·:1674 두 곳에 적용하고 ORC-02의 공유 헬퍼로 수렴하면 재발이 원천 차단된다. **(예상 크기: quick-win)**
- **검증 노트**: app.py:606·1674의 `f"engine-{...}"` 접두와 readiness.py의 `state="engine-missing"`(:82 등) 값을 직접 확인 — 문자열 결합 결과가 이중접두임이 코드상 확정. Top-10 순위 6. 계약 위반이나 크래시 아님 → M 적정.

<a id="orc-04"></a>
### ORC-04 [M] `status==errored` 런을 exit1·ok=False(도구 실패)로 오분류 — 계약상 사용자 결과인데 Nove Test 실패로 표기
- **근거**: `src/novetest/cli/app.py:635` — `run_cmd`의 status→(ok,exit) 매핑이 `passed`→`EXIT_OK`/ok=True(:635-637), `failed`→`EXIT_USER_TESTS_FAILED`(=3)/ok=True(:638-640), **else**→`EXIT_GENERIC`(=1)/ok=False(:641-643)다. `errored`는 else로 떨어져 exit1·ok=False가 된다(`EXIT_GENERIC=1`은 `src/novetest/cli/output.py:13`). 그러나 `errored`는 pytest 수집 에러 등으로 정상 정규화·영속된 **사용자 결과**이지 Nove Test 도구 실패가 아니다.
- **실패 시나리오**: pytest collection error로 `errored`가 된 스위트가 RunRecord로 정상 영속됐는데도 envelope는 `ok=False`·exit1(도구 일반 오류)로 나가, exit code로 도구 실패 vs 사용자 실패를 구분하는 AI 에이전트/CI가 "Nove Test가 깨졌다"로 오독한다. `failed`가 ok=True/exit3인 것과 대칭이 깨진다.
- **권고**: `errored` 런을 `failed` 계열(ok=True, exit3 또는 전용 코드)로 재분류. status→(ok,exit) 매핑을 단일 헬퍼로 추출해 `run_cmd`/`test_cmd`(handlers/test.py)가 공유(ORC-03/23과 한 슬라이스 S8). **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: app.py:635-643의 3분기와 `EXIT_GENERIC=1`/`EXIT_USER_TESTS_FAILED=3`(output.py:13,15) 직접 확인 — `errored`가 else→exit1·ok=False로 떨어짐이 코드상 확정. Top-10 순위 5. wire 계약 오분류 → M 적정.

<a id="orc-05"></a>
### ORC-05 [M] run_id→RunReference 해석이 CLI 4곳에 verbatim 복제
- **근거**: `src/novetest/cli/app.py:759` — `next((e for e in entries if e.run_record.run_reference.run_id == run_id), None)` 형태의 선형 스캔이 `memory_show`(:759), `memory_delete`(:800), `_resolve_run_reference`(:865) 세 곳에 동일하게 반복되고, orchestration 워크플로 `inspect`에도 같은 술어가 별도로 산다(`src/novetest/orchestration/workflows/inspect.py:126`). 총 4개 복제 사이트가 동일한 "run_id로 히스토리 선형탐색 후 None" 로직을 재구현한다.
- **실패 시나리오**: run_id 해석 규칙이 바뀌거나(예: 접두 매칭·ambiguous 처리) not-found 엔벨로프 문구를 통일하려 할 때 4개 사이트를 동기 수정해야 하며, 한 곳을 놓치면 동사별로 해석/에러 문구가 갈린다. 선형 스캔이 4곳에 흩어져 Memory 조회 API 경계도 흐려진다.
- **권고**: Memory에 `find_entry_by_run_id(store, run_id)` 공개 API를 추가하고 CLI 4중 복제를 이 호출(또는 공유 `_resolve_run_reference`)로 대체. not-found 엔벨로프 문자열을 단일 상수화. **(예상 크기: quick-win)**
- **검증 노트**: app.py:759·800·865의 동일 제너레이터 술어와 inspect.py:126의 동형 술어를 직접 확인(4개 사이트). 순수 중복 → M 적정.

<a id="orc-06"></a>
### ORC-06 [M] top-level `compare` verb가 regression+coverage 합성을 CLI에 인라인 — coverage delta 이중노출
- **근거**: `src/novetest/cli/app.py:1030` — `compare_cmd`가 `compare_runs`(:994, `cli/app.py:72` import)와 coverage delta 투영(`_coverage_delta_payload:931`)을 CLI 레벨에서 직접 조합한다. coverage delta는 `coverage.diff`(:917-925)에서도 `_coverage_delta_payload`로 방출되어, 같은 delta가 두 동사 경로에 인라인 합성된다.
- **실패 시나리오**: compare 뷰의 regression+coverage 합성 규칙이나 delta 표현이 바뀌면 CLI의 인라인 조립을 직접 고쳐야 하고, coverage delta가 `compare`와 `coverage.diff` 두 곳에 이중 정의되어 표현 드리프트가 생기기 쉽다. 합성이 orchestration이 아니라 transport 레이어에 있어 경계가 깨진다.
- **권고**: `compare` verb의 regression+coverage 인라인 합성을 `build_compare_view(store, baseline, target)` 워크플로로 이관하고 coverage delta 이중노출을 정리. CLI는 뷰를 받아 envelope로 투영만. **(예상 크기: 1-cycle)**
- **검증 노트**: `compare_cmd:1030`, `compare_runs` import(:72)·호출(:994), `_coverage_delta_payload:931`과 `coverage.diff`(:917-925)의 delta 방출을 직접 확인. compare 뷰 합성 세부(regression+coverage 결합 형태)는 워크플로 이관 대상이라 CLI 인라인임만 확정 → M 적정.

<a id="orc-07"></a>
### ORC-07 [M] ~230줄 localization 캐시-무효화 정책이 CLI transport에 상주 — orchestration 관심사 누출
- **근거**: `src/novetest/cli/app.py:1183` — localization 동사 경로에 캐시-무효화 정책(Defect 5/7 fix)이 :1183-1350에 걸쳐 인라인으로 산다: 엔진 플래그 변경 시 on-disk `localization_findings.json` unlink 후 재파생(:1302, unlink는 :1390), `failure_proximity` 모드 예외처리(:1350), 그리고 `cli/app.py:43`이 `localization.persistence.localization_findings_path`를 직접 import한다. 파생 정책·파일 unlink가 transport 레이어에 물려 있다.
- **실패 시나리오**: 캐시 무효화 규칙(어떤 플래그 조합이 재파생을 트리거하는지, 어느 파일을 unlink하는지)이 orchestration이 아니라 CLI에 있어, localization 파생 정책을 바꾸려면 transport 코드를 고쳐야 하고 CLI가 localization 내부(파일 경로 helper)에 결합된다. app.py 비대화(ORC-01)의 주요 기여 요인.
- **권고**: ~230줄 캐시 무효화 정책(unlink + 재파생 + failure_proximity 예외처리)을 orchestration의 localization 워크플로 핸들러로 이관. CLI는 `(outcome, warning)` 튜플만 받아 envelope로 투영하고 `localization_findings_path`의 CLI import를 제거. cli→orchestration 방향이라 사이클 없음. **(예상 크기: 1-cycle)**
- **검증 노트**: app.py:43 import, 캐시정책 docstring/코드(:1183-1350), unlink 사이트(:1390) 직접 확인. 관심사 누출(경계) 결함 → M 적정. XCT-02와 교차.

<a id="orc-08"></a>
### ORC-08 [M] 엔진 outcome 프로젝터 4쌍이 `cli/app.py`와 `workflows/inspect.py`에 이중 정의
- **근거**: `src/novetest/orchestration/workflows/inspect.py:216` — inspect의 coverage/regression/localization/replay outcome 프로젝터 4개가 각각 docstring에서 "Identical wire shape to `cli/app.py::_coverage_outcome_payload`"(:216), "…`_regression_outcome_payload`"(:247), "…`_localization_outcome_payload`"(:281), "…`_replay_outcome_payload`"(:304)라고 명시하며 CLI의 `_coverage_outcome_payload`(app.py:655) 등과 동일 wire shape를 병렬 구현한다.
- **실패 시나리오**: 엔진 outcome의 wire 표현(예: coverage summary 필드 추가)을 바꾸면 CLI와 inspect 두 프로젝터를 동기 수정해야 하고, docstring이 "identical"을 약속하지만 강제 장치가 없어 한 쪽만 고치면 같은 outcome이 동사에 따라 다른 형태로 방출된다.
- **권고**: 이중 정의된 4쌍 프로젝터를 orchestration 중립 모듈로 이동해 단일 출처화하고 CLI·inspect가 공유. **(예상 크기: 1-cycle)**
- **검증 노트**: inspect.py:216/247/281/304의 "Identical wire shape to cli/app.py::_*_outcome_payload" 4개 docstring과 CLI 측 `_coverage_outcome_payload:655`을 직접 확인 — 이중 정의가 코드·docstring상 명시적. 순수 중복 → M 적정.

<a id="orc-09"></a>
### ORC-09 [M] 읽기 전용 동사가 모호/pre-pin 스토어에서 exit2로 하드 실패 — 읽기 seam 부재
- **근거**: `src/novetest/cli/app.py:159` — 모든 동사가 통과하는 단일 workspace-해석 seam `_require_store`가 `resolve_workspace`(:168)를 호출하고, 이것이 legacy pin-less 스토어에서 단일 엔진을 못 고르면 `EngineAmbiguousError`를 던져 :178-189가 `code="engine-ambiguous"` + `EXIT_USAGE`(=2)로 하드 종료한다. `status`(:688)·`memory.list`(:738)·`memory.show`(:756)·`coverage.show`(:895) 등 순수 읽기 동사도 모두 이 seam을 통과하므로(:688 등), 저장된 런을 그냥 조회하려는 요청조차 모호 스토어에서 exit2로 거부된다.
- **실패 시나리오**: pre-pin(D6 마이그레이션 대상) 또는 다중 마커 스토어에서 사용자가 과거 런을 보려 `novetest status`/`memory list`를 실행하면, 실행 동사(run/test)가 만나야 할 엔진 모호성 때문에 읽기 동사가 exit2로 하드 실패한다. 읽기와 실행이 같은 해석 seam을 공유해 실행-전용 제약이 읽기 경로로 누출된다.
- **권고**: 읽기 전용 동사(status/memory list/inspect)가 모호/pre-pin 스토어에서 exit2 하드 실패하지 않도록 seam을 분리 — `EngineAmbiguousError`는 실행 동사가 `resolve_execution_engine`에서만 만나도록. **(예상 크기: 1-cycle)**
- **검증 노트**: `_require_store:159-192`의 EngineAmbiguous→exit2 분기(:178-189)와 읽기 동사들의 `_require_store` 호출(status:688, memory.list:738 등) 직접 확인. **D6는 2026-07-03 최신 결정 표면이라 구현 완결성이 유동적** — seam 분리 착수 시 재검증 필요. 읽기 경로 하드 실패 → M 적정. XCT-04와 교차.

<a id="orc-10"></a>
### ORC-10 [M] `normalize_target_expression`의 비존재-경로 분기가 lexical canonicalization을 건너뜀 — 파일시스템 존재에 따라 키가 갈림
- **근거**: `src/novetest/orchestration/anchor_resolution.py:264` — `normalize_target_expression`은 존재하는 상대경로만 `to_workspace_relative_posix`로 정규화(:262-263)하고, else(비존재) 분기는 `normalized = path_part`로 **입력 그대로** 반환한다(:264-265). `..` collapse·`./` strip이 존재 경로에만 적용되어, 같은 논리적 타깃도 디스크 존재 여부·표기 형태(`a/../b` vs `b`, `./sub` vs `sub`)에 따라 다른 정규화 키를 낳는다.
- **실패 시나리오**: regression baseline은 target_expression 키로 런을 묶는데, 비존재 경로(아직 안 만든 테스트, 오타, 삭제된 경로)나 `..` 포함 표기가 매번 다른 문자열로 통과해 같은 논리 타깃의 baseline 시리즈가 분열된다. Windows-dotdotdot fast-follow(`fdf44d7`) 계보의 잔여 표면 — all-dots 가드(:260-261)는 있으나 일반 `..` collapse는 없다.
- **권고**: else(비존재) 분기에도 lexical canonicalization(`..` collapse 포함)을 적용해 파일시스템 존재와 무관하게 안정된 키 산출. 네이티브 엔진 패턴은 계속 verbatim 통과. **(예상 크기: quick-win)**
- **검증 노트**: anchor_resolution.py:257-266의 4분기(절대/all-dots/존재/else) 직접 확인 — else가 `path_part` verbatim 반환이라 비존재·`..` 표기에 lexical 정규화 부재 확정. all-dots 가드(:260-261)는 별건. baseline 분열은 regression 소비 계약에 의존 → M 적정.

<a id="orc-11"></a>
### ORC-11 [M] command 등록이 두 침묵 사이트로 갈려 완결성 강제 없음 — `workspaces` 동사 본체 미구현
- **근거**: `src/novetest/cli/renderers/registry.py:55` — CLI 렌더러 디스패치 `_RENDERERS` dict(registry.py:55 부근, "version"/"init"/"run"/... 키)와 onboarding의 `command_surface.py` `CommandSpec` 튜플(`_OPERATING` 등, :66 부근)이 command 토큰을 각각 독립 나열한다. 둘을 실제 등록된 `@app.command` 트리와 대조하는 완결성 가드가 없어 한 사이트에만 추가/누락돼도 조용히 통과한다. `workspaces` 동사는 어느 사이트에도 본체가 없다(`grep workspaces` = app.py/command_surface/registry 전부 무매치).
- **실패 시나리오**: 새 동사를 추가하거나 이름을 바꿀 때 `_RENDERERS` 키·`CommandSpec` name·`@app.command` 등록 셋 중 한둘만 갱신하면, 렌더러 미등록(런타임 KeyError) 또는 도움말/서피스 누락이 테스트 없이 새어나간다. 세 등록 사이트의 정합이 사람 규율에만 의존한다.
- **권고**: cli/app 트리 순회로 등록된 command 토큰을 수집해 `registry._RENDERERS` 키 집합 + `command_surface` name 집합과 정확 일치하는지 assert하는 완결성 테스트 추가(두 침묵 사이트를 테스트 타임에 loud화). **신규 `workspaces` 동사 본체는 제품 결정 미스케줄 — 이 슬라이스는 테스트만.** **(예상 크기: 1-cycle)**
- **검증 노트**: `registry.py`의 `_RENDERERS` dict(:55 부근)와 `command_surface.py`의 `CommandSpec` 튜플(:66 부근) 직접 확인, `workspaces` 무매치 확인. 완결성 가드 부재(잠재 등록 드리프트) → M 적정.

<a id="orc-12"></a>
### ORC-12 [M] `compound_resolution`의 swallow 판정이 파일 단위 — 같은 파일의 무관한 심볼 추천을 침묵 삭제
- **근거**: `src/novetest/orchestration/recommendation/categories.py:491` — `compound_resolution`이 compound가 발화한 `file`을 `swallowed_files` set(:520), `test_id`를 `swallowed_tests` set(:521)에 **독립적으로** 모은 뒤, `investigate_location` hit을 `payload["file"] in swallowed_files`이면 무조건 드롭한다(:525-527). 즉 파일 F에 compound가 하나라도 발화하면, F의 **다른(무관한) 위치/심볼**에 대한 `investigate_location`도 함께 삭제된다. docstring(:501-504)은 "unrelated investigate_location on a different file"만 방어한다고 주장하나, 같은 파일 내 무관 심볼은 걸러지지 않는다.
- **실패 시나리오**: 한 파일 F에 서로 다른 함수 두 개가 있고, 함수 A가 regression+localization compound로 잡히면, 무관한 함수 B에 대한 `investigate_location`(다른 결함) 추천이 파일 단위 매치로 조용히 삭제되어 AI 에이전트/사용자가 B의 실제 의심 위치를 못 본다.
- **권고**: swallow 판정 키를 파일 단위에서 `(file, primary_line)`/`(file, symbol)`로 좁혀 같은 파일의 무관한 심볼 침묵 삭제를 제거(스펙이 파일 단위 의도면 PM 확인). **(예상 크기: 1-cycle)**
- **검증 노트**: categories.py:512-531 직접 확인 — `swallowed_files` set 기반 드롭(:526)이 파일 단위이고 primary_line/symbol 좁힘 없음이 코드상 확정. docstring 주장과 실제 판정 범위의 괴리 확인. 파생 추천 침묵 삭제 → M 적정.

<a id="orc-13"></a>
### ORC-13 [M] 커버리지-갭 citation의 `related_finding_id`가 selector 왕복 복원 불가 + 문서 §3 citation shape 불일치
- **근거**: `src/novetest/orchestration/recommendation/categories.py:348` — coverage_gap citation이 `"related_finding_id": f"entry_index_{idx}"`(:348, docstring :309)로 결정적 인덱스 id를 부여하나, `_coverage_gap_citations`(`src/novetest/orchestration/recommendation/citations.py:165`)가 이 `related_finding_id`(entry_index)를 selector에 실어 원본 LocalizationEntry로 왕복 복원하는 경로가 미비하다. 문서 §3의 citation shape 서술과 코드 실제(per-run finding_id + rank/file/primary_line selector)가 어긋난다.
- **실패 시나리오**: 소비자가 coverage_gap 추천의 `related_finding_id`로 관련 localization finding을 역참조하려 하면, entry_index만으로는 해당 run의 실제 finding_id/selector로 안정적으로 복원되지 않아 링크가 끊긴다. 문서가 약속한 citation shape와 실제 방출 형태가 달라 계약 소비자가 오독한다.
- **권고**: `_coverage_gap_citations`가 `related_finding_id`(entry_index)를 selector에 실어 round-trip 복원되게 하고, 문서 §3 citation shape를 코드 실제(per-run finding_id + rank/file/primary_line selector)로 정합(ORC-18과 한 커밋). **(예상 크기: 1-cycle)**
- **검증 노트**: categories.py:309·348의 `related_finding_id="entry_index_{idx}"`와 `citations.py:165 _coverage_gap_citations` 정의 위치는 직접 확인. round-trip 복원 미비·문서 §3 대조의 세부는 citations.py 본문·설계문서를 이 세션에서 완독하지 않아 **confidence: uncertain** — 슬라이스 착수 시 재검증 필요. 계약 정합 이슈 → M(로드맵 판정 승계).

<a id="orc-14"></a>
### ORC-14 [M] D6 pin backfill 쓰기가 읽기 경로에서 발생 — 원자성·읽기 순수성 훼손
- **근거**: `src/novetest/cli/app.py:159` — `_require_store`의 docstring이 seam을 "upward walk + **lazy engine-pin migration for legacy stores**"로 정의하고 "returned handle reflects the post-migration pin state"라 명시한다(:162-165). 즉 `resolve_workspace`(:168)가 legacy 스토어를 읽을 때 pin backfill **쓰기**를 수행하며, 이 seam은 `status`(:688)·`memory.list`(:738) 등 순수 읽기 동사도 통과한다. 읽기 동사가 부수효과로 스토어를 변경한다.
- **실패 시나리오**: 읽기 전용으로 기대되는 `status`/`memory list`가 legacy 스토어에서 pin backfill 쓰기를 트리거해, 동시 실행(다른 프로세스의 run)과 경합하거나 크래시 시 부분-쓴 pin을 남길 수 있다. 읽기 경로의 부수효과가 계약(읽기=side-effect-free)을 위반한다.
- **권고**: D6 backfill 쓰기를 Memory 소유의 원자적 temp-write+rename으로 바꾸고, 읽기 경로에서는 backfill을 생략(읽기는 pin 없이도 조회 가능하게). **D6는 2026-07-03 최신 결정 표면이라 구현 완결성이 가장 불확실 — 착수 시 재검증 필수.** **(예상 크기: 1-cycle)**
- **검증 노트**: `_require_store:159-168`의 docstring이 lazy pin-migration(쓰기)을 명시하고 읽기 동사가 이 seam을 공유함을 직접 확인. backfill 쓰기의 원자성 세부(`resolve_workspace` 내부 구현)는 이 세션에서 완독하지 않아 **confidence: uncertain** — D6 표면 재검증 필요. 읽기 순수성/원자성 → M(로드맵 판정 승계). XCT-04와 교차.

<a id="orc-15"></a>
### ORC-15 [M] run/test 엔벨로프의 상대경로가 `str(Path.relative_to(...))` — Windows backslash 유출
- **근거**: `src/novetest/orchestration/workflows/run.py:125` — 아티팩트 경로 상대화가 `name: str(Path(p).relative_to(store.path))`로, `.as_posix()` 없이 `str()`을 쓴다. 동일 패턴이 `src/novetest/orchestration/workflows/test.py:209`에도 있다. Windows에서 `str(PosixPath 아닌 Path)`는 `\` 구분자를 산출해 record.json·run 엔벨로프에 backslash 경로가 유출된다.
- **실패 시나리오**: Windows에서 run/test를 실행하면 엔벨로프·record.json의 아티팩트 경로가 `sub\dir\file` 형태로 직렬화되어, POSIX 경로를 기대하는 크로스-호스트 소비자(로컬 baseline vs CI candidate 비교, 경로 매칭)가 오작동한다. Wave-1이 이미 다른 곳에서 `.as_posix()` 정규화를 채택했는데 이 두 사이트는 누락됐다.
- **권고**: `run.py:125`·`test.py:209`의 `str(Path(p).relative_to(store.path))`를 `.as_posix()` 정규화로 교체(Wave-1 채택 패턴). `store_run_evidence` 상대화 주석도 정정. **(예상 크기: quick-win)**
- **검증 노트**: workflows/run.py:125·workflows/test.py:209의 `str(Path(p).relative_to(store.path))` 두 사이트를 직접 확인 — `.as_posix()` 부재로 Windows backslash 유출 확정(미장비 호스트라 실행 재현은 아닌 코드 경로 확인). 크로스-호스트 경로 계약 → M 적정.

<a id="orc-16"></a>
### ORC-16 [M] `status`가 tombstone된 최신 run을 `latest_run_reference`로 노출 — 삭제한 run을 현재 head로 오보
- **근거**: `src/novetest/orchestration/workflows/status.py:137` — `build_status_view`가 `history = list_run_history(store)`(:137) 후 `latest = history[0]`(:138)를 그대로 `latest_entry`/`latest_run_reference`로 삼는다. 그런데 `list_run_history`(`src/novetest/memory/store.py:103-117`)는 docstring대로 "newest-first across both **live and tombstoned** runs"로 tombstone된 런까지 포함해 정렬한다(:104,116). 따라서 가장 최근 런이 tombstone돼도 status는 그것을 latest로 선택한다.
- **실패 시나리오**: `run --coverage`로 R을 만든 뒤 `memory delete <R>`(tombstone)하고 `status`를 부르면, tombstone된 R이 여전히 `latest_run_reference`로 노출되어 사용자/에이전트가 삭제한 런을 현재 head로 오인한다. 파생 `*_available` 플래그도 tombstone된 R 기준으로 계산된다.
- **권고**: `build_status_view`의 latest 선택에서 tombstone을 제외(live 런 중 최신을 head로). **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: status.py:137-138의 무필터 `history[0]`과 store.py:103-117 `list_run_history`가 tombstoned 포함임을 직접 확인 — tombstone 런이 latest로 새는 경로 확정. Top-10 순위 10. 데이터 오보 → M 적정.

<a id="orc-17"></a>
### ORC-17 [L] 문서-코드 구조 서술 표류에 걸린 orchestration 항목(레지스트리/디스패치 stale)
- **근거**: `src/novetest/run/engine.py:149` — 실제 엔진 디스패치는 `engine.py:149-204`의 if-elif 사다리인데, `foundations.md §5`의 decorator-registry/NativeAdapter Protocol 서술은 미구현이다(XCT-01/부채 a). orchestration 문서(`design/workflows/`, `design/interace-contract/`)가 이 stale 지도를 전제로 동사 흐름을 서술하는 부분이 표류 위험에 노출된다.
- **실패 시나리오**: 신규 기여자가 stale 문서(레지스트리 존재 전제)를 신뢰해 orchestration 동사 배선을 잘못 이해하거나, 실제 if-elif 디스패치와 다른 확장 지점을 가정한다. 문서가 코드보다 앞서 신뢰되면 확장 시 잘못된 사이트를 편집한다.
- **권고**: 부채 a의 문서 후퇴(S24)에 orchestration 관련 서술을 포함 — `foundations.md §5` 트리/레지스트리 의사코드를 실물(함수형 adapter + if-elif 디스패치 + `_READINESS_PROBES`/`_ENGINE_MARKER_TABLE` SSoT)로 재작성. **레지스트리 구현 금지.** **소유권 위험: program-close carry-forward #5로 미추적 파킹 상태 — PM 명시 배정 필요.** **(예상 크기: quick-win)**
- **검증 노트**: 실제 디스패치가 `engine.py:149-204` if-elif임은 리뷰 세션 규율(알려진 stale 문서)과 부합. orchestration 문서의 정확한 stale 문단 위치는 이 세션에서 개별 열람하지 않아 **confidence: uncertain** — XCT-01/S24와 함께 다룸. 문서 위생 → L(로드맵 판정 승계).

<a id="orc-18"></a>
### ORC-18 [L] recommendation 문서 §3의 citation shape 서술이 코드 실제와 불일치
- **근거**: `src/novetest/orchestration/recommendation/categories.py:309` — citation의 실제 형태는 per-run finding_id + `related_finding_id="entry_index_{idx}"`(:309,348) + rank/file/primary_line selector인데, recommendation 설계 문서 §3의 citation shape 서술이 이 실제 방출 형태와 어긋난다(ORC-13의 문서 축).
- **실패 시나리오**: 문서 §3의 citation shape를 신뢰해 소비자를 구현한 에이전트/개발자가 실제 방출 필드(finding_id/selector 구조)와 다른 키를 파싱하려다 실패한다.
- **권고**: 문서 §3 citation shape를 코드 실제(per-run finding_id + rank/file/primary_line selector)로 정합(ORC-13과 한 커밋). **(예상 크기: quick-win)**
- **검증 노트**: categories.py:309·348의 실제 citation 필드는 직접 확인. 설계 문서 §3의 정확한 서술 대조는 이 세션에서 문서를 열지 않아 **confidence: uncertain** — ORC-13과 배칭 시 재검증. 문서-코드 정합 → L(로드맵 판정 승계).

<a id="orc-19"></a>
### ORC-19 [L] Phase 1 범위 밖 스텁 등록 클러스터 + 도달불가 분기 = 죽은 코드
- **근거**: `src/novetest/cli/app.py:123` — `_make_stub`(:123, `not_implemented_envelope` import :25)과 `_register_flat_stub`(:1811)/`_register_group_stub`(:1816) + "Remaining stubs (not in Phase 1 Run+Memory scope)" 주석(:1807)이 미구현 동사 스텁 등록 클러스터를 이룬다. 실제 동사가 다수 구현된 현 시점에 이 스텁 경로·고아 `not_implemented_envelope` import는 도달성이 의심되는 잔재다.
- **실패 시나리오**: 죽은 스텁 등록 코드가 실제 동사 등록과 섞여 있어 독자가 어떤 동사가 진짜 배선됐는지 판별하기 어렵고, 도달불가 분기가 리뷰·리팩터 노이즈를 키운다(app.py 비대화 기여).
- **권고**: 스텁 등록 클러스터(`_make_stub`/`_register_flat_stub`/`_register_group_stub` + 'Remaining stubs' 주석 + 도달불가 `--output` 분기 + 고아 `not_implemented_envelope` import)를 제거(S28). **(예상 크기: quick-win)**
- **검증 노트**: `_make_stub:123`, import :25, 주석 :1807, `_register_flat_stub:1811`/`_register_group_stub:1816`을 직접 확인. 각 스텁이 실제로 미등록/도달불가인지의 전수 판정은 등록 호출부 완독이 필요해 일부 **confidence: uncertain** — S28 착수 시 사용여부 확정. 죽은 코드 위생 → L 적정.

<a id="orc-20"></a>
### ORC-20 [L] `reset` 성공 data에 `pinned_engine` 누락 — `init`과 비대칭
- **근거**: `src/novetest/cli/app.py:489` — `reset_cmd`의 성공 엔벨로프 data(:489-496)는 `store_path`/`store_state`/`previous_initialized_at`/`initialized_at`/`items_removed`/`engine_readiness`만 담고 `pinned_engine` 키가 없다. 반면 `init` 성공 data는 `pinned_engine`을 포함한다(:342-344, `result.store.pinned_engine.to_dict()`). reset도 재-init 후 pin을 세우므로 같은 필드를 노출해야 대칭이다.
- **실패 시나리오**: init/reset 성공 응답을 동형으로 파싱하는 에이전트가 reset 후 `data.pinned_engine`을 기대하지만 없어, reset 직후 어떤 엔진으로 pin됐는지 응답만으로 알 수 없다(별도 status 호출 필요).
- **권고**: reset 성공 data에 init과 동형 `pinned_engine`을 additive 필드로 추가(byte-stability 스냅샷 갱신 동반). **(예상 크기: quick-win)**
- **검증 노트**: reset data(app.py:489-496)에 `pinned_engine` 부재와 init data(:342-344)의 `pinned_engine` 존재를 직접 확인 — 비대칭 확정. additive 계약 필드 누락 → L 적정.

<a id="orc-21"></a>
### ORC-21 [L] 포괄 예외 catch가 동사명·구조적 매핑을 보존하지 못할 위험
- **근거**: `src/novetest/cli/app.py:585` — 실행 동사의 예외 처리가 `EngineAmbiguous`/`EngineNotReady`/`AdapterInvocation`을 개별 except로 잡되(ORC-02), RunEngineError 계열의 상위 포괄 catch가 명시 매핑에서 빠지면 동사명(`command="run"` vs `"test"`)이나 EngineNotSupported→exit4 같은 구조적 매핑을 잃을 수 있다.
- **실패 시나리오**: 새 RunEngineError 하위 예외가 추가되고 개별 except에 안 걸리면, 포괄 처리가 없거나 동사명을 하드코딩하면 잘못된 command 라벨/exit로 방출된다.
- **권고**: ORC-02의 `_map_execution_exception(command, exc)` 공유 헬퍼가 동사명을 인자로 보존하고 RunEngineError 계열을 구조적으로 매핑(EngineNotSupported→exit4)하도록 설계. **(예상 크기: quick-win)**
- **검증 노트**: run_cmd/test_cmd의 개별 except 3종(:585-631/:1655-1690)은 직접 확인. RunEngineError 상위 포괄 catch 부재로 인한 미매핑 하위예외의 실제 도달 여부는 예외 계층 완독이 필요해 **confidence: uncertain** — S17 착수 시 확정. 견고성 위생 → L(로드맵 판정 승계).

<a id="orc-22"></a>
### ORC-22 [L] `indent_block`이 프로덕션 미사용 죽은 코드
- **근거**: `src/novetest/cli/renderers/_format.py:111` — `indent_block(text, prefix="  ")`가 정의돼 있으나 프로덕션 소비자가 없다(`grep -rn indent_block src/` = 정의 1곳뿐, 사용처는 `tests/unit/cli/renderers/test_format.py`의 단위 테스트만). 테스트만 이 함수를 exercise한다.
- **실패 시나리오**: 죽은 렌더러 헬퍼가 유지·리뷰 대상으로 남아 실제 렌더링 경로를 오도하고, 테스트가 '사용됨'을 가장한다.
- **권고**: `indent_block`(및 그 전용 테스트)을 제거하거나, 향후 사용 예정이면 주석으로 명시. 통합 스냅샷 strip allowlist를 스키마 파생/동기화 가드 테스트로 보강(S28, ORC-27과 함께). **(예상 크기: quick-win)**
- **검증 노트**: `_format.py:111` 정의와 `grep`으로 프로덕션 사용처 부재(테스트 `test_format.py:12,61-62`만)를 직접 확인 — 프로덕션 죽은 코드 확정. 위생 → L 적정.

<a id="orc-23"></a>
### ORC-23 [L] markerless 실행 분기의 에러 토큰이 D7 표준과 미정렬
- **근거**: `src/novetest/cli/app.py:606` — `init`의 markerless 경로는 D7 표준 토큰 `no-engine-detected`(:382)/`engine-ambiguous`를 정확히 방출하는데, `run`/`test`의 markerless(엔진 미준비) 실행 분기는 `code=f"engine-{exc.readiness.state}"`(:606/:1674, ORC-03의 이중접두)로 D7 표준(`no-engine-detected`/`engine-missing`)과 다른 토큰을 낸다.
- **실패 시나리오**: 에이전트가 D7 표준 에러코드로 markerless/엔진부재를 분기하려 하면, init은 표준 토큰을 주는데 run/test는 비표준(이중접두) 토큰을 주어 동사별로 다른 코드 어휘를 학습해야 한다.
- **권고**: markerless 실행 분기의 토큰을 D7 표준(`no-engine-detected`/`engine-missing`)으로 정렬(ORC-03 수정과 한 슬라이스 S8). **(예상 크기: quick-win)**
- **검증 노트**: init의 `no-engine-detected`(:382) 방출과 run/test의 `f"engine-{state}"`(:606/:1674) 방출을 직접 확인 — 토큰 어휘 불일치 확정. ORC-03과 강결합. 계약 어휘 정합 → L 적정.

<a id="orc-24"></a>
### ORC-24 [L] `reset` docstring의 'still recoverable' 문구가 실제 rmtree 실패 시맨틱과 어긋남
- **근거**: `src/novetest/cli/app.py:414` — `reset_cmd`(:414-)의 docstring/주석이 삭제 후 'still recoverable'을 시사하나, reset primitive의 실제 계약상 step6 rmtree 실패는 staging orphan을 남기는 것이지 원본이 복구 가능한 상태는 아니다. 'still recoverable' 서술은 rename **이전** 실패에만 한정되어야 한다.
- **실패 시나리오**: 문서를 신뢰한 사용자가 reset 실패 후 원본이 복구 가능하다고 오인해, 실제로는 staging orphan만 남은 상태에서 잘못된 복구 절차를 시도한다.
- **권고**: reset docstring의 'still recoverable' 문구를 rename 이전 실패로 한정하고, step6 rmtree 실패는 staging orphan임을 primitive 계약과 일치시킴(S27). **(예상 크기: quick-win)**
- **검증 노트**: `reset_cmd:414` 및 성공 경로(:483-497)는 직접 확인. 'still recoverable' docstring 문구의 정확한 위치·reset primitive rmtree step 시맨틱은 reset 워크플로 완독이 필요해 **confidence: uncertain** — S27 착수 시 문구 대조. 문서 정합 → L(로드맵 판정 승계).

<a id="orc-25"></a>
### ORC-25 [L] `inspect`의 regression 파생-부수효과가 `status`(캐시-전용)와 비대칭
- **근거**: `src/novetest/cli/app.py:1546` — 읽기형 동사 `status`는 `build_status_view`가 `compare_runs`를 부르지 않고 `get_regression_facts` 캐시-읽기만 하는 side-effect-free 계약(`status.py:130-134`)인데, `inspect_cmd`(:1546)의 regression 경로는 이와 달리 파생(compare) 부수효과를 낼 수 있어 두 읽기형 동사의 캐시 정책이 어긋난다.
- **실패 시나리오**: `status`와 `inspect`를 모두 '싸고 부수효과 없는 조회'로 기대하는 소비자가, `inspect`에서 예기치 않은 regression 파생 쓰기/비용을 겪는다. 읽기형 동사 간 부수효과 계약이 불일치한다.
- **권고**: `inspect`의 regression 파생-부수효과를 `status`와 동일하게 캐시-전용으로 맞추거나, 부수효과가 의도면 계약 docstring을 정정(S19). **(예상 크기: quick-win)**
- **검증 노트**: `status.py:130-134`의 명시적 side-effect-free 계약(compare_runs 미호출)과 `inspect_cmd:1546` 진입점은 직접 확인. inspect의 regression 파생 부수효과 유무는 inspect 워크플로 본문 완독이 필요해 **confidence: uncertain** — S19(D6 표면)와 함께 재검증. 읽기 대칭성 → L(로드맵 판정 승계).

<a id="orc-26"></a>
### ORC-26 [L] `test_target_in_store` memory_entry의 파생 플래그가 regression/localization 파생 후 재조회되지 않아 stale
- **근거**: `src/novetest/orchestration/workflows/status.py:97` — 파생 `*_available` 플래그는 latest memory_entry 기준으로 계산되는데(`build_status_view:147-156`), run→derive 순서에서 memory_entry가 regression/localization 파생 **후** 재조회되지 않으면 방금 파생한 결과가 플래그에 반영되지 않는 stale 창이 생긴다. 리프레시 지점이 일원화돼 있지 않다.
- **실패 시나리오**: 한 호출 내에서 run 후 regression/localization을 파생했는데 응답의 파생 플래그가 파생 이전 상태를 반영해, 소비자가 방금 만든 파생 결과를 'unavailable'로 오인한다.
- **권고**: `test_target_in_store` memory_entry가 regression/localization 파생 후 재조회되도록 리프레시 지점을 일원화(stale 파생 플래그 제거, S10, ORC-16과 함께). **(예상 크기: quick-win)**
- **검증 노트**: `build_status_view`가 latest entry 기준 캐시-읽기로 플래그를 계산함(status.py:147-156)은 직접 확인. `test_target_in_store` 경로에서 파생 후 재조회 누락의 정확한 사이트는 test 워크플로 완독이 필요해 **confidence: uncertain** — S10 착수 시 리프레시 지점 특정. 파생 신선도 → L(로드맵 판정 승계).

<a id="orc-27"></a>
### ORC-27 [L] 통합 스냅샷 strip allowlist가 스키마 파생/동기화 가드 없이 하드코딩
- **근거**: `src/novetest/cli/app.py:940` — 엔벨로프 wire에서 `schema_version`을 의도적으로 strip하는 스냅샷 관례가 여러 사이트(:940, :1072, :1524, :1531, :1893)에 하드코딩돼 있고, 어떤 top-level 필드를 strip할지 정하는 allowlist가 스키마에서 파생되거나 동기화 가드 테스트로 보호되지 않는다.
- **실패 시나리오**: 엔벨로프 스키마에 top-level 필드가 추가/변경될 때 strip allowlist가 자동 갱신되지 않아, 스냅샷이 새 필드를 예기치 않게 포함/제외하거나 사이트별로 strip 규칙이 갈린다.
- **권고**: 통합 스냅샷 strip allowlist를 스키마 파생 또는 동기화 가드 테스트로 보강(S28, ORC-22와 함께). **(예상 크기: quick-win)**
- **검증 노트**: `schema_version` strip 서술이 app.py:940/1072/1524/1531/1893 다수 사이트에 반복됨을 직접 확인. allowlist가 스키마 파생/가드 테스트 없이 하드코딩임은 코드상 성립하나 전체 strip 규칙 완결성 판정은 스냅샷 테스트 완독이 필요해 일부 **confidence: uncertain** — S28 착수 시 확정. 스냅샷 위생 → L 적정.

## 미확정 관찰

이 도메인에는 미확정(uncertain)으로 강등할 별도 관찰 항목이 없다(확정 27 / 미확정 0). 위 확정 findings 중 일부 L/M 항목(ORC-13/14/17/18/21/24/25/26 등)은 앵커 사이트·핵심 근거는 이 세션에서 직접 확인했으나 특정 하위 주장(문서 §3 대조, D6 backfill 원자성 세부, inspect/reset 워크플로 부수효과·문구)의 완전 검증은 해당 슬라이스 착수 시 재확인이 필요하며, 각 항목의 검증 노트에 `confidence: uncertain`으로 명시했다. **주의: D6(2026-07-03 결정)에 걸린 ORC-09/14/25는 구현 완결성이 가장 유동적이므로 착수 전 재검증 필수.**
