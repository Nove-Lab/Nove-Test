# Run 엔진 (run core + native adapters) findings

스코프: `src/novetest/run/`(엔진 코어 + 6개 네이티브 어댑터: pytest/jest/junit/go-test/cargo(nextest)/xunit)와 `utils/asyncio_subprocess.py`, 관련 정규화/readiness/설계문서. 집계: 확정 27건(H 2 · M 13 · L 12), 미확정 0건.

## 확정 findings

<a id="run-01"></a>
### RUN-01 [H] go 어댑터가 디렉터리/nodeid 타깃을 변환 없이 넘겨 `novetest run .`은 루트 패키지만 실행(무증상 축소)하고 `./subdir`·`pkg::Test`는 가짜 빌드실패로 처리
- **근거**: `src/novetest/run/adapters/gotest_adapter.py:113` — `target_arg = test_target.target_expression or "./..."`(:113) 후 `argv.append(target_arg)`(:137)로 타깃식을 그대로 `go test`에 붙인다. target_resolver.py:35-41은 존재하는 디렉터리를 target_type="directory"로 두고 target_expression을 verbatim 유지, anchor_resolution.py:262-263은 `./pkg`를 `pkg`로 정규화하고 `.`은 `.`로 유지(workflows/run.py:108-111 순서: normalize→resolve). cargo_adapter.py:269와 dotnet_adapter.py:1046은 `target_type != "directory"` 가드로 이 클래스를 명시 회피하나 go에는 그 가드가 없다.
- **실패 시나리오**: 테스트가 하위 패키지(`./pkg/...`)에 있는 전형적 Go 모듈에서 `novetest run .` 실행 → normalize가 `.` 유지 → go 어댑터가 `go test -json ... .`(루트 패키지 단독, 비재귀) 실행 → 루트에 테스트 없으면 events 비고 returncode 0 → normalizer.py:479-480이 status="passed"로 집계. 전체 스위트를 조용히 건너뛰고 통과 보고. 별개로 `novetest run ./pkg`는 normalize가 `pkg`로 축약 → `go test pkg`(go는 `pkg`를 import-path로 해석) → 컴파일 이전 실패 → gotest_adapter.py:257-265 빌드실패 분기가 AdapterInvocationError(unparseable-output) 발생. 같은 입력을 cargo/dotnet은 --workspace/전체 csproj로, pytest는 디렉터리 재귀로 정상 처리한다.
- **권고**: go 어댑터에서 target_type을 인지해 변환: directory → `./<rel>/...`(또는 빈 타깃과 동일한 `./...`), nodeid(`<pkg>::<Test>`) → `<./pkg>` + `-run '^<Test>$'`로 분해. 최소한 cargo/dotnet과 동일하게 `.`/directory 타깃에 대해 `./...`로 폴백해 무증상 축소를 제거하라. **(예상 크기: 1-cycle)**
- **검증 노트**: gotest_adapter.py:113/137이 target_type을 보지 않고 verbatim append함을 직접 확인; cargo:269/dotnet:1046의 directory 가드 부재로 두 시나리오(무증상 false-green + 가짜 빌드실패) 모두 성립.

<a id="run-02"></a>
### RUN-02 [H] JUnit 어댑터만 워크스페이스 영속 리포트 디렉터리를 정리 없이 glob → 이전/필터 실행의 stale TEST-*.xml을 현재 실행 결과로 보고
- **근거**: `src/novetest/run/adapters/junit_adapter.py:314` — :314-320은 Maven 리포트를 `workspace/target/surefire-reports`에서, :621-634는 Gradle을 `workspace/build/test-results/test`에서 읽고 :784 `sorted(reports_dir.glob("TEST-*.xml"))`로 전부 파싱, :458-465는 `shutil.copytree(..., dirs_exist_ok=True)`로 통째 스테이징한다. 실행 전 clean 단계 없음(:245-249 `mvn -B test`에 clean 미포함). 부분 실행은 :277-278 `-Dtest=<expr>`로 좁힌다. 대조: pytest_adapter.py:73/jest:83/gotest:88/cargo:163은 per-run native_dir, dotnet은 TRX를 `--results-directory <native_dir/TestResults>`(:287,:1039)로 매 실행 신선한 per-run artifact_dir에 쓴다.
- **실패 시나리오**: 실제 리포지토리에서 `novetest run`(전체 50개) → Surefire가 TEST-*.xml 50개 생성. 이어서 `novetest run com.foo.BarTest`(=`-Dtest` 필터) → Surefire는 BarTest만 재실행·갱신하지만 나머지 49개 클래스의 stale XML은 그대로 잔존. 어댑터는 TEST-*.xml 전체를 glob → 이번 실행에서 돌지 않은 49개를 현재 run의 tests/summary/failed_tests로 보고. RunRecord가 오염되어 Regression/Localization의 baseline·재가중이 유령 테스트를 기반으로 동작. Gradle의 build/test-results/test도 clean 없이는 동일.
- **권고**: 실행 직전 스테이징 소스 리포트 디렉터리를 비우거나(또는 mtime>started_ms 필터), Maven은 `<reportsDirectory>`/Gradle은 test 결과 출력을 per-run artifact_dir로 리다이렉트해 다른 5개 어댑터와 동일하게 신선한 실행별 격리를 확보하라. **(예상 크기: 1-cycle)**
- **검증 노트**: :314/:318이 영속 워크스페이스 경로를 report_locations로 담고 :784 glob이 무조건 전량 파싱함을 확인; `_stage_reports_dir`는 목적지만 정리하고 소스 워크스페이스는 절대 비우지 않으며 mtime 신선도 필터도 부재 → 유령 테스트로 envelope·baseline 침묵 오염.

<a id="run-03"></a>
### RUN-03 [M] Rust 계약이 nightly `cargo test -Z unstable-options`로 남아 있으나 실제 어댑터는 `cargo nextest`
- **근거**: `design/interace-contract/run.md:82` — :78 §2.5 헤더 "Rust - `cargo test`", :82 "`cargo test <filter> -- --format=json -Z unstable-options` | Native CLI (`cargo test` / libtest, nightly JSON)". design/workflows/run.md:31,:77도 동일 nightly 문자열. 코드: cargo_adapter.py:4-9 docstring이 "Ships nextest-only per decisions/2026-05-29-cargo-adapter-nextest-primary.md"라 선언하고, :217-246 argv는 `cargo llvm-cov nextest ... --message-format=libtest-json`(coverage) 및 `cargo nextest run --no-fail-fast --message-format=libtest-json`(plain)로 구성된다. `-Z unstable-options`/`--format=json`은 어디에도 없다.
- **실패 시나리오**: interace-contract/run.md:82을 Rust 지원의 권위 소스로 삼는 에이전트/테스트는 nightly `cargo test -Z unstable-options --format=json` 인수를 기대하지만, 실제 배포 어댑터는 stable Rust에서 nextest의 libtest-json을 요구한다. 또한 delivery-phasing.md:290 Open Q#3("cargo nextest libtest-json graduation off nightly")은 이미 nextest-primary로 해소된 경로를 여전히 미결 nightly 이슈로 오기술한다. 계약-워크플로우-어댑터 3자 argv 불일치로 Rust 경로 변경/디버깅 시 잘못된 실행 모델을 근거로 작업하게 된다.
- **권고**: interace-contract/run.md:78,82과 workflows/run.md:31,77의 cargo 행을 `cargo nextest run --message-format=libtest-json` / `cargo llvm-cov nextest`(2026-05-29 결정) 기준으로 갱신하고, delivery-phasing.md:290 Open Q#3 상태를 해소 표기하라. **(예상 크기: quick-win)**
- **검증 노트**: 계약 문서(:78,:82), 워크플로우(:31,:77), 코드 docstring/argv(:4-9,:217-246), delivery-phasing:290 모두 직접 대조 — 코드는 nextest-only로 정확하고 문서만 stale한 문서-코드 드리프트(런타임 손상 없음)라 M.

<a id="run-04"></a>
### RUN-04 [M] 실패-로그 상대경로 `str(...relative_to())` 관용구가 어댑터 4곳에 복제 — Windows `.as_posix()` 수정이 놓친 클론 siblings
- **근거**: `src/novetest/run/adapters/cargo_adapter.py:367` — `failure_logs[...] = str(failure_path.relative_to(artifact_dir))` 관용구가 cargo:367, gotest:247-249, junit:898, dotnet:1233에 동일 복제(네 곳 모두 `.as_posix()` 아닌 `str()`). 이 값은 TestResult.failure_reference로 영속되고 localization/failure_proximity.py:247-248 `resolve_failure_text`가 `log_path = store.path/"run"/"artifacts"/f"run_{run_id}"/failure_reference`로 되읽는다. Wave1 `.as_posix()` 픽스(886dc09)는 envelope-evidence 사이트만 고쳤고 이 어댑터 artifact-log 키들은 잔여(브리핑은 3곳이라 했으나 gotest:248 포함 실제 4곳).
- **실패 시나리오**: Windows 호스트에서 `str(PurePath.relative_to())`는 백슬래시 경로(`native\failures\foo.log`)를 산출해 failure_reference에 저장·record.json에 영속. (a) 그 백슬래시 문자열이 AI 소비용 envelope에 posix-정규화된 다른 evidence와 섞여 나가고, (b) 해당 store를 POSIX 호스트에서 분석하면 `Path("native\failures\foo.log")`가 백슬래시를 리터럴 파일명으로 취급 → failure_proximity.py:249 `.is_file()`가 False → resolve_failure_text가 "" 반환 → 실패 로그 파싱 스킵 → failure_proximity localization이 parse_warning만 남기고 조용히 빈 finding으로 퇴화. Linux pre-merge 게이트는 구조적으로 못 잡는 계열.
- **권고**: 4개 사이트를 `failure_path.relative_to(artifact_dir).as_posix()`로 일괄 교체(원라인×4). 나아가 '실패로그 파일 기록+상대경로화'를 run/adapters 공용 헬퍼로 뽑아 posix 정규화를 한 곳에 강제하라. **(예상 크기: quick-win)**
- **검증 노트**: 4곳 모두 `str()` 사용·`.as_posix()` 부재 직접 확인, grep으로 정확히 이 4곳뿐임 확인; 되읽기 침묵실패(item b)는 resolve_failure_text가 cargo/gotest 엔진명에만 적용되어 조건부이나 finding scenario가 정확히 이에 초점을 맞춰 재현 논리 유효 → cross-host 이식 시 조건부 퇴화 + 컨벤션 드리프트로 M.

<a id="run-05"></a>
### RUN-05 [M] cargo 커버리지 모드에서 컴파일 실패가 '빌드 실패'가 아니라 'llvm-cov가 lcov를 쓰지 않음'으로 오진 — 빌드실패 판별이 non-coverage로만 게이트
- **근거**: `src/novetest/run/adapters/cargo_adapter.py:378` — `if not collect_coverage and not saw_test_started and result.returncode != 0:`로 빌드실패 진단 블록이 coverage 모드에서 통째로 스킵된다(주석 :373-377 "Skip in coverage mode"). 커버리지 모드에서 컴파일 실패 시 events 비고 coverage_path 부재 → :442-460이 `f"cargo llvm-cov did not write {coverage_path}"`(unparseable-output)로 상승. 비커버리지 경로 :429-433은 동일 원인을 `"likely build failure"`로 정확히 기술. 대조: gotest_adapter.py:257-265는 collect_coverage와 무관하게 빌드실패를 판별.
- **실패 시나리오**: `novetest run --coverage`가 컴파일 에러 있는 Rust 워크스페이스에서 실행 → saw_test_started False, coverage.lcov 미생성 → 어댑터가 'cargo llvm-cov did not write coverage.lcov' 메시지를 냄. 실제 근본 원인(소스 컴파일 실패)이 아니라 커버리지 툴 장애로 오지시되어 사용자/AI가 llvm-cov 설치·설정을 헛되이 파고들게 된다. 동일 커밋을 비커버리지로 돌리면 정확히 'likely build failure'가 나와 메시지가 자기모순.
- **권고**: 빌드실패 판별을 coverage 모드에서도 수행(스킵 게이트 제거 또는 coverage 경로에서도 saw_test_started False+returncode!=0면 컴파일 실패로 먼저 진단)하고, coverage_path 부재 메시지는 진짜 llvm-cov 실패에만 남겨라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: :378 게이트가 진단 블록 전체를 커버리지 모드에서 스킵시킴을 직접 확인; 오류는 여전히 unparseable-output+stderr tail로 표면화되어 침묵실패는 아니나 헤드라인이 llvm-cov 툴 장애로 오지시해 헛수고 유발 → M.

<a id="run-06"></a>
### RUN-06 [M] 어댑터 4종의 `_safe_failure_log_name` 복제 — escape 문자셋이 이미 3/11/16으로 발산
- **근거**: `src/novetest/run/adapters/cargo_adapter.py:511` — 실패-로그 파일명 위생 헬퍼가 4개 어댑터에 독립 정의되며 치환 문자셋이 서로 다르다: cargo:511-534 = `/`,`:`,`\` 3자; gotest:312-335 = 동일 3자; junit:964-979 = 위 3자+`#`,`[`,`]`,`(`,`)`,`,`,` `,`\t`의 11자; dotnet:1331-1357 = 11자+`=`,`"`,`'`,`<`,`>`의 16자. 산출 파일명은 cargo:366/gotest:244/junit:897/dotnet:1232의 `failure_path.write_text(...)`로 디스크에 기록된다.
- **실패 시나리오**: cargo/gotest의 3자 문자셋은 Windows 예약문자 `<>"|?*` 중 `:`만 escape하고 나머지는 미처리. 향후 rstest/test-case 매크로나 신규 nextest 포맷이 파라미터화 test name에 그런 문자를 포함하면 cargo:366 `write_text`가 Windows에서 OSError(invalid filename)를 raise — 이 write는 try/except로 감싸이지 않아 어댑터 run 전체가 unparseable-output으로 실패. 더 현실적 드리프트: 누군가 Windows 예약문자 대응을 위해 junit/dotnet 문자셋을 확장하며 cargo/gotest 복제본을 놓치면(이미 제각각이라 '여기만 다르겠지' 가정) 엔진별 위생 수준이 계속 벌어진다.
- **권고**: run/adapters 공용 헬퍼로 `safe_failure_log_name(name, extra_chars=())` 단일 구현을 두고 Windows 예약문자 `<>:"/\|?*`+공백/탭을 항상 포함하는 union 문자셋을 기본으로. 각 어댑터는 엔진 특유 문자만 extra로 추가하고 4개 복제 정의를 제거하라. **(예상 크기: 1-cycle)**
- **검증 노트**: 4개 정의를 직접 열어 문자셋 3/3/11/16 발산과 replace-루프 로직 동일성 확인; cargo:366 write_text가 try/except 미감쌈 확인. OSError는 미래 매크로 포맷 의존 추측성이나 복제·드리프트 주 논거는 코드로 확정 → 현재 데이터손상 없어 M.

<a id="run-07"></a>
### RUN-07 [M] 두 개의 서로 다른 Coverlet 경고 kind가 동일 문자열 "engine-misconfigured"로 정의되고 readiness-state 토큰과 충돌
- **근거**: `src/novetest/run/adapters/dotnet_adapter.py:156` — WARNING_COVERLET_BELOW_FLOOR(:156)와 WARNING_COVERLET_ABSENT(:157)가 둘 다 Final="engine-misconfigured"로 정의된다. 이 문자열은 AdapterWarning.code로 실려(:422-431 absent, :457-469 below-floor) app.py:275 `_adapter_to_envelope_warnings`에서 EnvelopeWarning.code로 그대로 복사되고 cli/renderers/registry.py:115가 `⚠ {warning.code}: {message}`로 렌더한다. 그런데 동일 문자열 "engine-misconfigured"는 run/types.py:65 EngineReadinessResult.state 값(readiness 3-상태 중 하나, exit 4 계열)이기도 하다. 모듈 주석(:152-154)과 types.py:98은 warning code를 "binding contract by downstream consumers"로 명시.
- **실패 시나리오**: coverlet.collector가 floor 미만인 정상 프로젝트에서 `novetest run --coverage` 실행 → 테스트는 전부 통과(exit 3 아님)하지만 envelope.warnings[].code == "engine-misconfigured"가 방출되고 text 렌더러가 성공 run에 `⚠ engine-misconfigured: ...`를 출력. (1) engine이 올바로 설정돼 테스트가 돈 run을 readiness 실패 taxonomy(engine-missing/misconfigured, exit 4 계열)와 같은 토큰으로 표기해 소비자를 오도. (2) below-floor와 absent 두 조건이 code만으로 구별 불가 — code를 key로 분기하는 기계 소비자는 두 경우를 병합해버린다.
- **권고**: 두 warning kind를 고유 slug로 분리(예: `coverlet-below-floor`/`coverlet-absent`)하고, readiness-state 문자열 "engine-misconfigured"를 warning code로 재사용하지 말 것. warning taxonomy와 readiness-state taxonomy를 분리해 계약 표면을 명확히 하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: :156-157 두 kind가 동일 Final 문자열임과 방출→복사→렌더 경로(:422-431/:457-469→app.py:275→registry.py:115) 직접 확인; readiness.py 23개 site에서 동일 문자열이 state로 할당돼 토큰 충돌 실재, 성공 run에 실패 taxonomy 토큰 부착 시나리오 성립 → M.

<a id="run-08"></a>
### RUN-08 [M] 호출자 timeout이 restore/probe/version 서브프로세스로 전파되지 않아 coverage run의 실질 벽시계 예산이 caller 지정치를 크게 초과
- **근거**: `src/novetest/run/adapters/dotnet_adapter.py:406` — run_xunit의 timeout 파라미터(:235)는 오직 메인 `dotnet test` 호출(:500-505)에만 전달된다. coverage 경로의 선행 서브프로세스들은 caller timeout과 무관한 하드코딩 예산을 쓴다: _ensure_csproj_restored=300.0(:810), _probe_coverlet_version JSON/tabular 각 30.0(:840,:852), _read_dotnet_version=10.0(:1475). run_subprocess는 env=None일 때 부모 env 상속하며 timeout 인자를 그대로 사용(utils/asyncio_subprocess.py:66).
- **실패 시나리오**: `execute(..., timeout=30, collect_coverage=True)`를 fresh fixture에서 호출하면, 아직 테스트가 시작되기도 전에 _ensure_csproj_restored의 `dotnet restore`(:406)가 최대 300초까지 블록될 수 있고(cold NuGet cache), 이어 probe 30+30초, version 10초가 추가된다. caller가 30초 예산을 기대했음에도 총 벽시계가 ~370초에 이를 수 있다 — timeout 계약이 coverage pre-flight 단계에서 무력화된다.
- **권고**: caller timeout을 pre-flight 단계로도 전파(잔여 예산 분할 또는 caller timeout 기반 상한 적용). 최소한 하드코딩 300/30/10초가 caller 예산을 초과하지 않도록 min()으로 클램프하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: timeout 파라미터가 메인 test 호출(:504)에만 전달되고 restore(:810)/probe(:840,:852)/version(:1475) 선행 서브프로세스가 하드코딩 예산을 씀을 직접 확인; run_subprocess가 timeout을 wait_for에 그대로 사용해 cold cache 시 누적 벽시계가 계약 초과 → M.

<a id="run-09"></a>
### RUN-09 [M] jest Windows 런처가 `cmd /c` — 미검증 target_expression의 cmd 메타문자 주입(RCE, Windows 한정)
- **근거**: `src/novetest/run/adapters/jest_adapter.py:253` — _npx_launcher(:230-254)는 Windows에서 `["cmd","/c","npx"]`를 반환하고(:253), argv에 :131-132 `argv.append(test_target.target_expression)`로 target을 그대로 덧붙인다. 런처 docstring(:243-249)은 공백/따옴표 인용만 논하고 `&|<>^%` 같은 cmd 메타문자 이스케이프는 다루지 않는다. normalize_target_expression은 존재하지 않는 경로를 verbatim 통과시킨다(orchestration/anchor_resolution.py:264-265).
- **실패 시나리오**: Windows에서 target_expression에 공백 없는 메타문자 페이로드(예: `a&calc`)가 오면, Python subprocess가 argv를 list2cmdline으로 합성할 때 공백/따옴표가 없어 인용되지 않고 그대로 커맨드라인에 실린다 → `cmd /c npx jest ... a&calc` → cmd.exe가 `&`를 명령 구분자로 해석해 `calc` 실행. 제품이 'AI-agent 소비용'이라 target이 신뢰 불가 입력(악성 repo의 테스트명/파일명 등)에서 파생돼 서브프로세스 argv로 주입되면 사용자 셸을 거치지 않고 곧장 Windows RCE가 된다. POSIX는 npx를 직접 exec(:254)해 영향 없음.
- **권고**: target을 cmd에 넘기기 전 메타문자 검증/거부(또는 화이트리스트), 혹은 cmd /c 대신 node로 jest.js를 직접 exec하는 런처로 전환. 최소한 target에 `&|<>^%"`가 있으면 usage 오류로 반려하라. **(예상 크기: 1-cycle)**
- **검증 노트**: `list2cmdline(['cmd','/c','npx','jest','a&calc'])`가 인용 없는 `a&calc`를 산출함을 실측 확인, target 전 계층 메타문자 거부 로직 부재(grep) 확인; Windows 한정+신뢰불가 target 전제의 조건부라 절대 RCE지만 M 방어 가능.

<a id="run-10"></a>
### RUN-10 [M] junit 어댑터가 mvn.cmd/gradle.bat/gradlew를 직접 exec — Windows에서 배치 셰임 실행 불가 추정
- **근거**: `src/novetest/run/adapters/junit_adapter.py:230` — maven 경로는 :230 `shutil.which("mvn")` 결과를 :246 argv[0]으로 직접 create_subprocess_exec(:283)한다. gradle 경로는 :524 `workspace/"gradlew"`+:525 `os.access(..., os.X_OK)` 또는 :528 `shutil.which("gradle")`를 :540 그대로 exec한다. 반면 jest 어댑터는 동일 문제('CreateProcess는 .cmd/.bat를 실행 못 함')를 :236-241 docstring에서 명시하고 `cmd /c`로 우회한다.
- **실패 시나리오**: Windows에서 `mvn`은 mvn.cmd, `gradle`은 gradle.bat, 래퍼는 gradlew.bat다. shutil.which가 PATHEXT로 mvn.cmd를 반환해도 create_subprocess_exec(=CreateProcess)는 배치 파일을 직접 실행하지 못하고(오류 193) 실패한다. 또 :524의 gradlew(확장자 없음)와 :525 os.X_OK 검사는 POSIX 전용이라 Windows에서 래퍼를 못 찾는다. jest만 우회하고 junit은 미우회 — 동일 함정 처리 비대칭.
- **권고**: jest의 _npx_launcher 패턴을 junit에도 적용(Windows에서 mvn/gradle/gradlew를 `cmd /c` 경유), 단 이때 target(-Dtest/--tests) 메타문자 주입도 함께 방어. Windows CI에 junit 레인이 없어 미검출 상태일 가능성이 크다. **(예상 크기: 1-cycle)**
- **검증 노트**: :230→:246→:283 exec 경로와 gradle :524-540 경로, jest의 :236-241 우회 docstring 직접 대조 — 함정 처리 비대칭 실재. 미세: Windows .cmd exec는 통상 WinError 193(FileNotFoundError 아님)이라 :289 핸들러가 못 잡고 raw OSError 전파 가능 → finding 서술보다 오히려 더 나쁜 실패. Windows 검증 부재로 confidence uncertain이나 결함 자체는 성립 → M.

<a id="run-11"></a>
### RUN-11 [M] pytest 어댑터가 foundations §3의 venv-우선 인터프리터·결정론 env 계약을 미이행
- **근거**: `src/novetest/run/adapters/pytest_adapter.py:78` — foundations.md:187 "If target/.venv/bin/pytest (or Scripts\pytest.exe on Windows) exists, use it. Otherwise fall back to python -m pytest. Never call bare pytest"; :186 "set deterministic ones (PYTHONHASHSEED=0, CI=1, FORCE_COLOR=0)". 코드: pytest_adapter.py:77-86 argv가 `sys.executable, "-m", "pytest", ...`로 시작해 novetest 자기 프로세스 인터프리터를 쓰고 target/.venv 프로브가 전무. :236-243 _build_child_env는 PYTEST_DISABLE_PLUGIN_AUTOLOAD/PYTHONUTF8/PYTHONIOENCODING/NO_COLOR만 설정하고 PYTEST_ADDOPTS만 pop하며 PYTHONHASHSEED·CI·FORCE_COLOR는 설정하지 않는다.
- **실패 시나리오**: foundations §7의 PyApp 단일 바이너리 배포에서 sys.executable은 사용자 data-dir에 풀린 번들 CPython으로, SuT 프로젝트의 `<project>/.venv`에만 설치된 pytest/플러그인에 접근할 수 없다. §3:187은 정확히 이 상황을 위해 venv-우선 해석을 규정하나 어댑터는 .venv/bin/pytest를 탐색하지 않으므로 pytest가 프로젝트 venv에만 있는 Python SuT는 실제 설치돼 있음에도 :147-153 경로에서 "pytest is not importable from the resolved interpreter"로 실패. 별도로 PYTHONHASHSEED=0/CI=1 결정론 env가 적용되지 않아 hash-seed 민감 테스트가 계약대로 고정되지 않는다.
- **권고**: 어댑터에 target/.venv 우선(존재 시)→python -m pytest 폴백 인터프리터 해석을 구현하고 PYTHONHASHSEED=0/CI=1(및 FORCE_COLOR 정책)을 _build_child_env에 반영하거나, 구현 불가/불필요면 foundations §3:186-187을 정정하라. 배포 모드(standalone PyApp vs pipx-into-venv)에 따라 런타임 심각도가 달라지므로 배포 계약과 함께 판단 필요. **(예상 크기: 1-cycle)**
- **검증 노트**: foundations:186-187 계약과 pytest_adapter.py:77-86(venv 프로브 부재)·:236-243(결정론 env 미설정) 직접 대조; §3 계약은 stale 목록(§318/§475)에 없어 유효 → 문서-코드 드리프트로 M(런타임 심각도는 배포 모드 조건부).

<a id="run-12"></a>
### RUN-12 [M] 제로-수집(0개 테스트) 처리가 엔진별로 3갈래로 갈림: pytest=errored / go·junit·xunit·jest=passed / cargo=예외 발생
- **근거**: `src/novetest/run/normalizer.py:205` — pytest: :205-207 `exit_code in (2,3,5)`→"errored"(5=no-tests-collected). go: :479-480 `returncode==0`→"passed". cargo: :623 aggregate는 `returncode==0`→"passed"이나 실제 런타임은 cargo_adapter.py:378·414-433에서 0개 매칭 시 `_NEXTEST_NO_TESTS_*`/빌드실패 분기로 AdapterInvocationError를 먼저 방출해 aggregate에 도달하지 못함. junit: :759-760 동일→"passed", xunit 미러(:899-900), jest도 success:true면 passed(:327-328). 즉 pytest만 exit5→errored로 상이하며 cargo는 어댑터 레벨에서 exit-nonzero 예외로 처리.
- **실패 시나리오**: 아무 테스트도 수집되지 않는 타깃(빈 필터/빈 패키지/존재하지 않는 필터)을 실행하는 동일 상황에서 pytest는 status=errored, go/junit/xunit/jest는 status=passed(무증상 초록으로 '아무것도 실행 안 됨'이 '성공'으로 보고), cargo는 exit-nonzero 예외(unparseable-output)로 도구실패 처리. 같은 의미의 사건이 엔진에 따라 성공/에러/도구실패로 제각기 보고되어 AI 소비자가 크로스-엔진 히스토리를 일관되게 해석할 수 없고, go/junit/xunit/jest의 zero-collected passed는 알려진 followup #1과 동일 표면.
- **권고**: 제로-수집을 단일 상태(명시적 'no-tests' 또는 일관되게 errored)로 수렴시키는 크로스-어댑터 규칙을 정하고 6개 정규화/어댑터 경로에 동일 적용. 5개 aggregate 함수의 `returncode==0 && len(test_results)==0` 분기를 명시 상태로 통일하라. **(예상 크기: 1-cycle)**
- **검증 노트**: 6개 경로 직접 확인 — pytest(:205-207)만 errored, go(:479-480)/junit(:759-760)/xunit(:899-900)/jest(:327-328) passed, cargo는 aggregate 도달 전 AdapterInvocationError raise로 3갈래 비대칭 실재; known followup #1과 동일 표면 → M(전담 조사 존재로 좌표 기록).

<a id="run-13"></a>
### RUN-13 [M] jest node_id가 절대 파일경로를 내장 — 크로스-호스트 regression 매칭 붕괴 및 Windows 역슬래시 유입
- **근거**: `src/novetest/run/normalizer.py:254` — _normalize_jest_payload는 `suite_file = suite.get("name") or suite.get("testFilePath") or ""`를 그대로 쓰고(:254) node_id를 `"::".join(part for part in (suite_file, ancestors, title) if part)`로 합성한다(:276). jest의 testResults[].name/testFilePath는 절대경로다. jest 어댑터는 raw payload(json.loads)를 무가공 전달한다(jest_adapter.py:196/221 `payload=payload`). 반면 pytest는 workspace-relative nodeid, go는 package::test, cargo는 binary::test로 논리적/상대 식별자를 쓴다.
- **실패 시나리오**: jest 프로젝트를 로컬 `/home/alice/proj`에서 실행해 baseline을 남기고 CI `/build/proj`(또는 컨테이너 다른 마운트 경로)에서 candidate를 실행하면 모든 test_results의 node_id 접두 절대경로가 달라져 regression union-walk(compare.py:364-366)가 동일 테스트를 전부 removed+added로 분류(사실상 비교 무의미). 또한 Windows에서 jest name은 역슬래시 절대경로라 node_id에 `\`가 그대로 persist되어 record.json/envelope에 유입 — evidence 문자열을 .as_posix()로 강제한 fast-follow의 POSIX-portable 자세와 정면 배치.
- **권고**: jest 어댑터(또는 normalizer)에서 suite name을 workspace-relative POSIX(.as_posix())로 정규화한 뒤 node_id 접두로 사용. workspace 밖 파일은 정책 결정 필요. 크로스-호스트/Windows 회귀 테스트를 추가하라. **(예상 크기: 1-cycle)**
- **검증 노트**: :254 절대경로 무가공 채택·:276 접두 합성, jest_adapter.py raw payload 전달, compare.py union-walk가 node_id 매칭 키 사용 확인; 타 엔진 상대/논리 식별자와의 비대칭 실재. 동일 호스트 반복비교엔 정상이라 조건부 드리프트로 M.

<a id="run-14"></a>
### RUN-14 [M] dotnet readiness의 test-csproj 선택 필터가 어댑터와 발산('test'만 vs tests/test/specs/spec) — ready 후 어댑터가 다른 csproj 실행
- **근거**: `src/novetest/run/readiness.py:914` — readiness 필터는 `test_csprojs = [p for p in all_csprojs if "test" in p.name.lower()]`(:914)이고 없으면 `all_csprojs[0]`(:915)을 고른다. 어댑터 _detect_test_project는 `any(token in p.name.lower() for token in ("tests","test","specs","spec"))`로 필터한다(dotnet_adapter.py:671-676). 둘 다 lower() 정렬 후 [0]을 픽하지만 필터 토큰이 다르다. readiness 주석(:893-895)은 '_detect_test_project의 walk를 mirror한다'고 주장하나 실제 판정 로직은 어긋난다.
- **실패 시나리오**: 워크스페이스에 `Z.Test/Z.Test.csproj`(xunit)와 `A.Specs/A.Specs.csproj`(xunit 없음)가 있으면 readiness는 'test'만 매칭해 test_csprojs=[Z.Test]→Z.Test의 xunit 확인→state=ready. 그러나 어댑터는 'specs'도 매칭해 test_csprojs=[A.Specs, Z.Test], 정렬상 'a.specs'<'z.test'로 chosen=A.Specs(xunit 없음)를 dotnet test에 넘겨 0 테스트/실패로 귀결. 역방향(A.Specs만 xunit, test-토큰 프로젝트 없음)에서는 readiness가 all_csprojs[0]=xunit 없는 라이브러리를 골라 engine-misconfigured로 정상 실행 가능 워크스페이스를 차단(false-negative).
- **권고**: readiness가 어댑터의 _detect_test_project를 직접 재사용하거나 동일 토큰 집합(tests/test/specs/spec)과 동일 정렬/픽 규칙을 공유해 SSoT화하고 발산 방지 테스트를 추가하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: readiness:914-915(‘test’만)와 어댑터:671-678(4토큰) 필터 발산, mirror 주장(:893-895)과의 불일치 직접 확인; spec-named 프로젝트가 정렬상 앞설 때만 트리거되는 엣지 레이아웃 의존이라 M.

<a id="run-15"></a>
### RUN-15 [M] 타임아웃 시 직속 자식만 kill(프로세스 그룹 미종료) → jest/junit/dotnet/cargo/go의 손자 테스트 프로세스·JVM·testhost·node 워커가 고아로 잔존(어댑터 간 비대칭)
- **근거**: `src/novetest/utils/asyncio_subprocess.py:69` — :67-70에서 `asyncio.TimeoutError` 시 `proc.kill()` 후 `await proc.wait()`만 수행, 프로세스 그룹/트리 시그널 없음(start_new_session/killpg 부재). 모듈 docstring(:7-8)이 "signal-group escalation arrive when a sub-product needs them"으로 미구현을 자백. pytest는 `python -m pytest`(pytest_adapter.py:77-86)로 in-process 실행해 직속 자식 kill로 종료되나, jest는 Windows에서 `cmd /c npx`(jest_adapter.py:252-254)로 cmd만 죽고 npx→node→워커 잔존, go는 컴파일된 test 바이너리, cargo nextest는 per-test 바이너리, junit은 mvn→포크된 Surefire JVM, dotnet은 dotnet→VSTest→testhost를 각각 별도 자식으로 스폰.
- **실패 시나리오**: 600초 타임아웃에 걸린 jest/junit/dotnet 실행에서 run_subprocess가 최상위 런처(cmd/mvn/dotnet)만 SIGKILL → 실제 테스트를 수행하던 JVM/testhost/node 워커는 계속 살아 CPU·파일락·포트를 점유하며 자연 종료까지 잔류. 병렬도가 높을수록 고아 누수가 누적되어 후속 실행/CI 슬롯을 잠식. 동일 상황에서 pytest만 안전.
- **권고**: POSIX는 `start_new_session=True`+`os.killpg`, Windows는 job object 또는 `taskkill /T`로 프로세스 트리 전체를 종료하도록 run_subprocess를 확장. 최소한 SIGTERM→유예→SIGKILL 그레이스풀 시퀀스와 그룹 킬을 추가하라. **(예상 크기: 1-cycle)**
- **검증 노트**: :48-55 create_subprocess_exec에 start_new_session 부재, :67-70 kill+wait만 수행함과 docstring 자백 직접 확인; jest cmd/npx·pytest in-process 대조로 어댑터 간 고아 잔존 비대칭 성립 → M.

<a id="run-16"></a>
### RUN-16 [L] .NET Test-to-code mapping 문서가 같은 파일 내 2026-06-05 Amendment와 자기모순(per-test 지원 주장 vs aggregate-effective)
- **근거**: `design/implementation-plan/engine-adapters.md:508` — :508 "**Per-test attribution is supported.** ... `mapping_granularity: per-test`."가 바로 위 :504 Amendment 2026-06-05("PerTestCoverage는 empirically inert ... 어댑터는 aggregate-effective-default로 출하 ... failure_proximity로 라우팅")와 정면 모순. 실제 코드는 dotnet_adapter.py:553-565에서 _glob_coverage_xml 실측 결과 수로 mapping_granularity를 도출하며, per-test glob(coverage.*.cobertura.xml)이 Coverlet 6.0.x에서 매치되지 않아 실무상 항상 "aggregate"(:564-565)를 방출한다.
- **실패 시나리오**: 엔진 어댑터 계약을 이 문서로 학습하는 신규 기여자/에이전트가 :508만 읽으면 xunit이 per-test 커버리지를 방출한다고 오인 → Localization mode 선택(:29의 mapping_granularity→mode 매핑)이 per-test SBFL을 기대하도록 잘못 설계할 위험. 실제 방출은 aggregate이며 failure_proximity로 라우팅되어야 함(:504).
- **권고**: engine-adapters.md:506-508 "Test-to-code mapping" 절을 :504 Amendment와 일치하도록 수정: per-test는 deferred, v1은 aggregate-effective-default, mapping_granularity는 glob 실측 파생임을 명시하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: :508 문장과 :504 Amendment의 자기모순, dotnet_adapter.py:552-565의 glob 실측 파생(코드는 Amendment 편) 직접 확인; 설계문서 모순으로 런타임 데이터 아님 → L.

<a id="run-17"></a>
### RUN-17 [L] 실패 로그 기록 규칙 비대칭: cargo/dotnet은 빈 버퍼도 빈 파일 생성·등록, go/junit은 내용 없으면 스킵 → failure_reference 유무 불일치
- **근거**: `src/novetest/run/adapters/cargo_adapter.py:361` — :361-367은 `ev_event=="failed"`면 `buffer=output_buffers.get(name,[])`가 비어도 무조건 `write_text("".join(buffer))`(빈 파일)+failure_logs 등록. dotnet:1218-1233도 log_lines가 비면 빈 파일 기록·등록. 대조: gotest:238-239 `if buffer:`로 빈 버퍼 스킵, junit:882는 status failed/errored AND failure_payload 존재일 때만 기록.
- **실패 시나리오**: stdout/stderr 캡처가 없는 실패(예: 패닉 메시지 미캡처)에서 cargo/dotnet은 failures/<name>.log 빈 파일을 만들고 failure_logs에 등록 → normalizer의 failure_reference가 빈 파일을 가리킴. 동일 상황에서 go/junit은 등록하지 않아 인라인 폴백 경로를 탄다. 크로스-엔진으로 failure_reference의 존재·의미가 달라져 소비자의 실패 상세 렌더링이 엔진에 따라 갈린다.
- **권고**: 빈 버퍼일 때 로그 파일 생성·등록을 생략하도록 cargo/dotnet을 go/junit과 통일하거나, 반대로 네 어댑터 모두 빈 실패 로그도 항상 생성하도록 규칙을 명문화하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: cargo:361-367·dotnet:1218-1233(빈 검사 없이 등록)과 gotest:238-239(`if buffer:`)·junit:882(failure_payload 조건) 직접 대조로 비대칭 확인; 0바이트 로그 참조로 데이터손상 수준은 아니라 L.

<a id="run-18"></a>
### RUN-18 [L] restore/probe/version 보조 서브프로세스가 _build_child_env 정화를 받지 못해 telemetry-optout 의도가 coverage 경로 첫 호출에서 무력화
- **근거**: `src/novetest/run/adapters/dotnet_adapter.py:807` — 메인 `dotnet test`는 _build_child_env()(:497→:1062-1089: DOTNET_NOLOGO/DOTNET_CLI_TELEMETRY_OPTOUT/DOTNET_SKIP_FIRST_TIME_EXPERIENCE/NO_COLOR/MSBUILDTERMINALLOGGER)를 전달하지만, _ensure_csproj_restored(:807-811), _probe_coverlet_version(:836-841,:848-853), _read_dotnet_version(:1472-1476)는 run_subprocess를 env 인자 없이 호출한다. asyncio_subprocess.py:54에 따라 env=None이면 자식이 CLI의 원 env를 그대로 상속한다.
- **실패 시나리오**: coverage 경로에서 실제 가장 먼저 실행되는 dotnet 호출은 _ensure_csproj_restored의 `dotnet restore`(:406)인데 여기엔 opt-out env가 없다. 한 번도 dotnet을 돌린 적 없는 호스트에서 이 첫 호출이 .NET first-run experience(telemetry notice+NuGet fallback 채우기)를 트리거해 telemetry ping과 추가 지연을 발생 — docstring(:1067-1070)이 명시한 telemetry opt-out·first-time skip 의도가 정작 first 호출에서 defeated된다(sentinel이 restore로 소비된 뒤에야 후속 test 호출이 조용해짐).
- **권고**: restore/probe/version 서브프로세스에도 _build_child_env()(최소 DOTNET_CLI_TELEMETRY_OPTOUT/DOTNET_SKIP_FIRST_TIME_EXPERIENCE/DOTNET_NOLOGO)를 전달해 정화 env를 세 보조 호출에 일관 적용하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: 세 보조 호출(:807-811/:836-853/:1472-1476)이 env 없이 호출되고 메인만 _build_child_env 전달됨, coverage 경로 첫 dotnet 호출이 restore임을 직접 확인; telemetry ping/지연으로 데이터손상 아님 → L.

<a id="run-19"></a>
### RUN-19 [L] _slugify_for_coverlet: 정의·__all__ 노출·단위테스트만 있고 실사용 호출자 0건인 dead code
- **근거**: `src/novetest/run/adapters/dotnet_adapter.py:1420` — 전역 grep 결과 _slugify_for_coverlet의 유일 출현은 정의(:1420), __all__ 등재(:1510), tests/unit/run/adapters/test_dotnet_adapter.py:51/1099/1104/1115의 직접 테스트뿐 — src/ 내 기능 호출자 0건. docstring(:1432-1434)은 "Used by the R1 probe"라 주장하나 모듈 어디에도 R1 probe 함수가 없다. per-test 승격 경로(:554-562)도 slug 상관을 쓰지 않고 per_test_files[0].parent만 취한다. junit_adapter.py:1266 _glob_jacoco_xml dead-함수 선례와 동형.
- **실패 시나리오**: per-test 커버리지가 Coverlet 6.0.x에서 empirically inert(:40-51)이므로 slug 상관 로직이 필요해지는 경로가 없다. 그럼에도 함수가 __all__로 export되고 단위테스트가 통과해 커버리지·grep 상 '살아있는' 것처럼 보여 유지보수자가 forward-compat 상관 로직이 배선돼 있다고 오인할 수 있다(실제로는 미배선). 미래 Coverlet이 per-test를 지원해도 :561의 승격 경로는 이 slugifier를 호출하지 않는다.
- **권고**: _slugify_for_coverlet를 제거하거나(그리고 __all__·단위테스트도 함께), 실제 per-test 상관 경로에 배선할 때까지 명시적 dead-code로 격리 표기하라. per-test 승격 경로(:554-565)가 slug 상관을 실제로 필요로 하는지 재검토하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: grep으로 src 내 기능 호출자 0건, "R1 probe"가 주석에만 존재, 승격 경로(:561)가 slugifier 미호출 직접 확인 — dead code+docstring 드리프트로 L.

<a id="run-20"></a>
### RUN-20 [L] go의 `-timeout`이 서브프로세스 타임아웃과 동일값이라 go의 그레이스풀 자체-타임아웃이 사실상 무력화
- **근거**: `src/novetest/run/adapters/gotest_adapter.py:120` — :120 `timeout_seconds = int(timeout) if timeout is not None else 600`+:126 `f"-timeout={timeout_seconds}s"`로 go 내부 타임아웃을 서브프로세스 타임아웃과 같은 값으로 설정. asyncio_subprocess.py:66은 서브프로세스 벽시계 타임아웃을 spawn 시점(빌드 포함)부터 재고, go의 -timeout은 빌드 이후 테스트 실행 시점부터 잰다. docstring(:117-119)은 'go test가 스스로 죽인다'는 이점을 주장한다.
- **실패 시나리오**: 테스트가 무한 대기하는 경우 서브프로세스 벽시계(빌드+실행)가 go의 실행-전용 타임아웃보다 먼저 소진되어 asyncio_subprocess의 `proc.kill()`이 먼저 발화 → go의 패닉 덤프+이벤트 방출(그레이스풀 경로)이 손실되고 일반 timed-out AdapterInvocationError(:163-167)로 귀결. 결과적으로 -timeout 플래그가 주장된 이점(진단 가능한 자체 종료)을 제공하지 못한다.
- **권고**: go의 `-timeout`을 서브프로세스 타임아웃보다 작게(예: timeout*0.9 또는 -빌드 여유) 두어 go가 먼저 그레이스풀하게 종료·덤프하도록 하거나, docstring의 이점 주장을 실제 동작에 맞게 정정하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: :120/:126 동일값 설정과 asyncio_subprocess:48/66/69의 spawn-시점 벽시계·grace-없는 kill 직접 확인; -timeout이 per-package라 `./...` 다중 패키지에선 시나리오 강화. 타임아웃은 여전히 kind=timed-out로 정확 보고돼 데이터손상 없어 L('사실상 무력화'는 다소 과장).

<a id="run-21"></a>
### RUN-21 [L] _glob_jacoco_xml는 호출자 0건인 죽은 함수 — 동일 로직이 Maven 파스 경로에 인라인 복제되어 있음
- **근거**: `src/novetest/run/adapters/junit_adapter.py:1266` — _glob_jacoco_xml(:1266-1286)에 대한 grep 결과 src/tests 통틀어 정의 라인 1건 외 참조 0건. 반면 실제 Maven 커버리지 해석은 같은 파일 :364(module_dir/'target'/'site'/'jacoco'/'jacoco.xml')와 :376(workspace/'target'/'site'/'jacoco'/'jacoco.xml')에 인라인으로 재구현되어 있다 — _glob_jacoco_xml 본문(:1281,:1285)과 문자 그대로 동일한 경로 조립.
- **실패 시나리오**: 누군가 multi-module JaCoCo 글로빙 버그(예: 첫 모듈만 반환하는 :1279-1284 정책)를 고치려고 _glob_jacoco_xml을 수정하면, 실제 실행 경로는 :354-379의 인라인 코드이므로 수정은 런타임에 아무 효과가 없다. 죽은 복제본이 '고쳤다는 착각'을 유발하는 유지보수 함정이며 두 사본이 조용히 드리프트할 수 있다.
- **권고**: _glob_jacoco_xml(:1266-1286)을 삭제하거나, 반대로 :354-379의 Maven 인라인 글로빙을 이 헬퍼 호출로 치환해 단일 출처로 통합하라. 삭제 쪽이 surgical. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: grep으로 정의 외 참조 0건, :364/:376 인라인 복제가 함수 본문과 동일 경로 조립임 확인 — dead code+복제 드리프트로 L.

<a id="run-22"></a>
### RUN-22 [L] `-`로 시작하는 target_expression이 `--` 분리자 없이 엔진 플래그로 소비됨
- **근거**: `src/novetest/run/adapters/pytest_adapter.py:108` — pytest는 :107-108 `argv.append(test_target.target_expression)`, jest는 :131-132, cargo는 :269-270에서 target을 독립 argv 원소로 덧붙이되 그 앞에 `--` 분리자가 없다(dotnet은 :1053 `FullyQualifiedName~<expr>`로, junit은 :278 `-Dtest=<expr>`로 값 내부에 임베드해 무해). normalize_target_expression은 존재하지 않는 경로를 verbatim 통과(orchestration/anchor_resolution.py:264-265)시켜 dash-선두 값이 그대로 도달한다.
- **실패 시나리오**: workflow-API/replay 등 CLI Cyclopts 파서를 우회하는 호출자가 target_expression=`-p no:cacheprovider`(또는 `--pdb`,`-c /path`)를 넘기면 pytest는 이를 테스트 경로가 아니라 옵션으로 해석한다 → 문서 계약상 target은 경로/필터여야 하나 임의 엔진 플래그가 주입되어 수집 대상/설정이 바뀐다. `--` 분리자 부재로 '존재하지 않는 경로 → 깔끔한 에러' 대신 조용한 플래그 주입이 된다.
- **권고**: pytest/jest/cargo argv에서 target append 직전에 `--` 분리자를 삽입(예: pytest `..., "--", target`)해 dash-선두 값을 positional로 못박아라. **(예상 크기: quick-win)**
- **검증 노트**: :107-108/jest:131-132/cargo:269-270의 `--` 미삽입과 dotnet/junit 임베드 무해, anchor_resolution.py:221-265에서 `--pdb`가 verbatim 반환되는 경로 직접 추적 확인; CLI 우회 프로그래매틱 호출자가 계약 위반해야 트리거되는 오용성 입력이라 confidence uncertain·L.

<a id="run-23"></a>
### RUN-23 [L] 6개 어댑터의 subprocess 실행/타임아웃/타이밍/stdout·stderr 기록 스켈레톤 복붙
- **근거**: `src/novetest/run/adapters/pytest_adapter.py:111` — 동일 5단 스켈레톤(`artifact_dir.resolve()` → `native_dir.mkdir(parents=True,exist_ok=True)` → `started_ms=int(time.time()*1000)` → `run_subprocess(...)` → `completed_ms` → `stdout/stderr .write_bytes(...)` → `if result.timed_out: raise AdapterInvocationError(..., kind="timed-out")`)이 pytest:69/111/120/123, jest:79/135/156/159, gotest:84/140/160/163, cargo:159/273/292/295, junit:136/281/299/302 및 595/612/615(2-phase build+run), dotnet:281/498/516/519에 반복. 타임아웃 kind는 6곳 모두 `"timed-out"`으로 일치(현재는 미드리프트).
- **실패 시나리오**: 타임아웃 실패 계약을 바꿀 때(예: AdapterInvocationError에 부분 stdout tail이나 install_hint 같은 구조 필드 추가, 또는 kind 문자열 변경) 6~8개 사이트를 손으로 동기화해야 하며 한 어댑터를 빠뜨리면 엔진별로 타임아웃 envelope 형상이 달라진다. 새 어댑터 추가 시에도 스켈레톤을 다시 복붙하게 되어 `artifact_dir.resolve()` 방어나 stderr 기록 같은 단계를 누락할 여지가 있다(예: stdout만 쓰고 stderr write를 빠뜨리면 실패 진단이 사라짐).
- **권고**: `run/adapters/_harness.py`류 공용 헬퍼로 'native_dir 준비+timed run_subprocess+stdout/stderr 아티팩트 기록+timed-out 표준 raise'를 감싸고(엔진별 argv 빌드와 payload 파싱만 콜백/이후 단계로 남김) 6개 어댑터가 이를 호출해 타임아웃 계약을 단일 지점에 수렴시켜라. **(예상 크기: 1-cycle)**
- **검증 노트**: 6개 어댑터를 직접 열어 5단 스켈레톤 동형 반복과 6곳 kind="timed-out"·메시지 형식 일치(현재 미드리프트) 확인 — 현재 데이터손상 없는 중복/위생이라 L.

<a id="run-24"></a>
### RUN-24 [L] pytest 자식 env가 부모 PYTHONPATH를 그대로 상속 — 호스트 3.10 트리 누수가 SuT pytest로 전파
- **근거**: `src/novetest/run/adapters/pytest_adapter.py:237` — _build_child_env(:236-243)는 :237 `os.environ.copy()` 후 PYTEST_DISABLE_PLUGIN_AUTOLOAD/PYTHONUTF8/PYTHONIOENCODING/NO_COLOR 설정과 PYTEST_ADDOPTS pop만 하고 PYTHONPATH는 제거하지 않는다. 이 env가 :110→:112 run_subprocess로 `sys.executable -m pytest`(:77-79) 자식에 전달된다. grep 결과 src/novetest 전체에서 PYTHONPATH를 다루는 코드는 0건.
- **실패 시나리오**: GOTCHAS.md가 명시하듯 호스트 프로필이 Python 3.10 트리를 PYTHONPATH로 누수시키는(그래서 모든 python 셸 명령에 `env -u PYTHONPATH`를 강제하는) 환경에서 novetest를 실행하면 pytest 어댑터 자식은 그 PYTHONPATH를 상속해 3.10 site-packages가 sys.path 앞단에 삽입된다 → SuT가 기대한 것과 다른 버전의 패키지가 import되거나 수집 단계가 깨진다.
- **권고**: _build_child_env에 `env.pop("PYTHONPATH", None)`(또는 SuT venv 기준 재설정) 추가. jest/go 어댑터의 env 위생과 동일한 수준으로 python 자식에도 적용하라. **(예상 크기: quick-win)**
- **검증 노트**: :236-243이 PYTHONPATH를 미제거하고 asyncio_subprocess.py:30-54가 자식 env를 전체 대체함을 확인 — 누수 메커니즘은 무조건 성립(confirmed). 단 재현은 부모 셸 PYTHONPATH 설정에 의존하고 하네스가 `env -u PYTHONPATH`를 강제해 자체 테스트에선 재현 안 됨, jest/node는 PYTHONPATH 무영향이라 '어댑터 불일치' 논거가 약함 → python 자식 한정 격리 위생으로 L.

<a id="run-25"></a>
### RUN-25 [L] 소스 내 유일한 활성 TODO(engine.py:52) — execute(engine=None) 레거시 분기; 명시된 선행조건은 이미 충족됨(도달 불가 분기)
- **근거**: `src/novetest/run/engine.py:52` — src/tests 전체에서 활성 TODO/FIXME/XXX/HACK 마커는 :52-54 단 1건. TODO 본문은 'orchestration이 pin을 마지막 caller까지 배선하면 engine=None auto-detect 분기를 제거하라'. 프로덕션 execute() 호출자는 orchestration/workflows/run.py:115와 test.py:196 둘뿐이며 모두 engine=engine_pair 전달. engine_pair=resolve_execution_engine(...)는 anchor_resolution.py:164-206에서 반환타입 tuple[str,str](None 반환 없음, 실패 시 raise). 따라서 engine.py:90-94의 else 분기와 그 안의 select_native_engine(:94, 프로덕션 유일 참조)은 프로덕션 경로에서 도달 불가 — 단위테스트만 진입.
- **실패 시나리오**: pinned 모델(2026-07-03) 도입 이후 execute()에 engine=None을 넘기는 프로덕션 caller가 남지 않았다. 그럼에도 else 분기(:90-94)+assess_engine_readiness 스캔+select_native_engine 디스패치가 계속 존재해 Run 표면의 인지 부하를 키우고 select_native_engine을 '살아있는 API'로 오인하게 만든다(테스트에서만 커버). TODO 선행조건은 이미 만족.
- **권고**: engine=None 분기 제거는 별도 전담 조사 소관이므로 여기서는 존재/선행조건-충족만 기록. 전담 조사 시: else 분기 삭제→engine 파라미터 비-옵셔널화→select_native_engine 프로덕션 유일 참조 소멸 여부 확인 후 함께 정리. assess_engine_readiness는 replay/engine.py:71이 여전히 소비하므로 제거 대상 아님. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: grep으로 src 전체 활성 TODO 1건, 프로덕션 호출자 둘 다 engine_pair(tuple, None 미반환) 전달로 else 분기·select_native_engine 도달 불가, assess_engine_readiness는 replay가 소비 확인 — 죽은-분기 인지부하 관찰(기록 전용)이라 L.

<a id="run-26"></a>
### RUN-26 [L] go/cargo/pytest readiness probe가 run_subprocess의 FileNotFoundError/OSError를 미포착(dotnet만 포착) — TOCTOU 시 미처리 예외로 crash
- **근거**: `src/novetest/run/readiness.py:412` — _probe_dotnet_sdk_version만 `try: ... except (OSError, FileNotFoundError): return None`으로 감싼다(:1008-1015). 반면 go(`go version`, :412-414), cargo(`cargo nextest --version` :509-513, `cargo --version` :529-533), pytest(sys.executable -c, :225-229)는 무방비로 run_subprocess를 호출한다. run_subprocess는 asyncio.create_subprocess_exec를 직접 호출하며(asyncio_subprocess.py:48) 실행 파일 부재 시 FileNotFoundError를 전파한다. go/cargo는 shutil.which로 선검사하지만 which↔exec 사이 TOCTOU 창이 존재하고 load-bearing한 misconfigured 판정 경로다.
- **실패 시나리오**: cargo가 PATH에 있어 which를 통과한 직후 바이너리가 제거/권한변경되면(레이스, 또는 rustup 토글) run_subprocess의 create_subprocess_exec가 FileNotFoundError를 던지고 _assess_cargo_readiness에 핸들러가 없어 assess_engine_readiness/probe_engine 전체가 engine-misconfigured 대신 미처리 예외로 중단된다. dotnet 경로는 동일 상황에서 None(정상 격하)을 반환하는 것과 대비되는 비대칭.
- **권고**: go/cargo/pytest probe의 run_subprocess 호출을 dotnet과 동일하게 try/except (OSError, FileNotFoundError)로 감싸 engine-misconfigured로 격하하거나, run_subprocess가 실행실패를 SubprocessResult(비정상 returncode)로 흡수하도록 헬퍼 계약을 강화하라. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: dotnet만 try/except(:1008-1015) 감싸고 go(:412-414)/cargo(:509-533)/pytest(:225-229)는 무방비, 호출 체인(_probe_candidate→assess_engine_readiness)에도 핸들러 없음 확인; go/cargo shutil.which→exec 사이 TOCTOU 창 실재(pytest는 sys.executable이라 소멸 사실상 불가로 과장) → 좁은 레이스 창의 견고성 비대칭이라 L.

<a id="run-27"></a>
### RUN-27 [L] stdout/stderr를 `.read()`로 전량 메모리 적재 + go/cargo는 events 리스트까지 이중/삼중 보유 → 대형 스위트에서 피크 메모리 비대
- **근거**: `src/novetest/utils/asyncio_subprocess.py:58` — :58-59 `proc.stdout.read()`/`proc.stderr.read()`는 EOF까지 무제한 버퍼링(상한 없음), :72 gather로 전량 수집. go/cargo는 그 위에 원시 바이트를 `.decode().splitlines()`(gotest:184, cargo:315)하고 파싱한 `events: list[dict]`(gotest:176·197, cargo:307·327)를 전부 보유한 뒤 :270-272/:438-440에서 events.jsonl로 다시 직렬화한다.
- **실패 시나리오**: `go test -json ./...`가 수십 MB의 NDJSON 이벤트를 뿜는 대형 모듈에서 피크 메모리 = 원시 bytes+디코드된 str+events dict 리스트+json 재덤프가 동시 상주. 크래시는 아니나 메모리 사용이 출력 크기의 수 배로 확대되어 대형 리포지토리에서 비용/불안정을 유발한다. 정확성 이슈 아님(정렬된 드레인으로 데드락 없음).
- **권고**: 라인 단위 스트리밍 파싱(readline 루프)으로 전환하거나 events 원시 보존을 events.jsonl append-write로 대체해 리스트 상주를 제거하라. 최소한 캡처 상한/경고를 두라. **(예상 크기: 1-cycle)**
- **검증 노트**: :58-59 인자 없는 read()가 EOF까지 무제한(StreamReader 64KB limit 미적용)·:72 gather 전량 수집, gotest/cargo의 decode+events 리스트+jsonl 재직렬화 동시 상주 직접 확인; 데드락·정확성 이슈 없이 피크 메모리 확대만이라 L.

## 미확정 관찰
없음.
