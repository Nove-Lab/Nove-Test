# Models + Utils findings

스코프: `src/novetest/models/`(8개 도메인 엔티티)와 `src/novetest/utils/`(asyncio_subprocess, path_utils, ulid)의 계약·경계·자원 안전성 검토. 집계 — 확정 5건(H 1 / M 1 / L 3), 미확정 1건.

## 확정 findings

<a id="mod-01"></a>
### MOD-01 [H] 타임아웃 시 직계 자식만 kill — 손자 프로세스 고아화 + 파이프 EOF 대기로 무한 hang 가능
- **근거**: `src/novetest/utils/asyncio_subprocess.py:69` — `run_subprocess`는 타임아웃 시 :69 `proc.kill()`로 직계 자식 1개 PID에만 SIGKILL을 보낸다. `create_subprocess_exec`(:48)는 start_new_session/프로세스그룹 없이 생성되며(저장소 전체에서 프로세스 종료는 이 :69 kill 단 1곳, killpg/setsid/CREATE_NEW_PROCESS_GROUP/terminate 전무), stdout_task=:58 `proc.stdout.read()`/stderr_task=:59는 EOF까지 읽고, :72 `await asyncio.gather(stdout_task, stderr_task)`에는 타임아웃이 없다.
- **실패 시나리오**: cargo nextest / dotnet test / mvn / gradle / jest는 실제 테스트를 별도 자식(테스트 바이너리·testhost·JVM·jest-worker)으로 띄우고 이들이 부모의 stdout/stderr 파이프 write-end를 상속한다. 예: `cargo nextest run`이 hang된 테스트 바이너리를 스폰한 상태에서 600s 타임아웃 발화 → :69가 `cargo` 프로세스만 죽인다 → 테스트 바이너리는 고아로 살아남아 파이프 write-end를 계속 보유 → :58 read()가 EOF를 못 받음 → :72 gather가 영구 블록. run_subprocess가 절대 반환하지 않아 타임아웃 자체가 무력화된다. 최선의 경우에도(손자가 파이프를 안 잡으면) 손자 테스트 프로세스가 고아로 계속 CPU를 소모한다.
- **권고**: POSIX는 `start_new_session=True` + 타임아웃 시 `os.killpg(os.getpgid(pid), SIGKILL)`, Windows는 CREATE_NEW_PROCESS_GROUP 또는 Job Object로 프로세스 트리 전체를 종료. 추가로 :72 gather에 별도 타임아웃(짧은 grace)을 걸어 파이프 드레인이 영구 블록되지 않게 한다. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 file:line 모두 정확. :48-55 프로세스그룹 미설정 생성, :58-59 EOF까지 read, :66 wait_for 타임아웃 시 :69 직계 자식만 SIGKILL, :72 gather 무타임아웃 확인. 모든 어댑터가 이 단일 헬퍼 경유하며 cargo_adapter가 timeout을 전달해 경로 도달 가능. 손자 파이프 상속 시 gather 영구 블록으로 envelope 미반환 침묵 실패 → H 적정.

<a id="mod-02"></a>
### MOD-02 [M] stdout/stderr를 상한 없이 메모리로 전량 read — 폭주 출력 시 OOM
- **근거**: `src/novetest/utils/asyncio_subprocess.py:58` — :58 `proc.stdout.read()` / :59 `proc.stderr.read()`는 크기 제한 인자 없이 EOF까지 전체를 메모리에 적재하고, :73 `SubprocessResult(stdout=bytes, stderr=bytes)`로 원본 전량을 보관한다. 어떤 어댑터도 상한을 두지 않는다.
- **실패 시나리오**: SuT의 테스트가 무한/거대 출력을 stdout에 뿜는 경우(로그 폭주 버그, 또는 악의적 SuT) run_subprocess가 그 바이트를 전부 메모리에 축적한다. gotest_adapter.py는 코멘트에서 '<< 1MB per package'를 가정하지만 코드 상 실제 캡은 없어, 폭주 출력 1건이 오케스트레이터 프로세스를 OOM으로 몰 수 있다. MOD-01과 결합되면 타임아웃도 이를 못 끊는다.
- **권고**: read()에 바이트 상한을 두고 초과분은 truncate(+truncated 플래그)하거나, 청크 드레인 루프로 상한 도달 시 조기 종료. envelope는 어차피 stderr tail 400자만 쓰므로 전량 보관은 불필요. **(예상 크기: quick-win)**
- **검증 노트**: `read(-1)`은 EOF까지 전량 적재하며 transport 64KB `_limit`은 readline/readuntil에만 적용되어 총량 미제한. 6개 어댑터+readiness 어디에도 truncate 인자 없고 gotest 주석은 강제 캡 아닌 가정임을 확인. 병적/악의적 입력 필요한 가용성 리스크 → M 적정.

<a id="mod-03"></a>
### MOD-03 [L] models/ 미러 규칙 드리프트 — 8개 모델 중 3개의 계약 테스트가 tests/unit/models/ 밖에 있음
- **근거**: `src/novetest/models/replay_result.py:1` — tests/unit/models/에는 test_coverage_fact_set/memory_entry/run_record/run_reference/test_result만 있고 models/localization_finding.py·models/regression_fact_set.py·models/replay_result.py의 미러 테스트가 없다. 계약 테스트가 sibling 엔진 디렉토리에 산다: tests/unit/localization/test_localization_finding_model.py, tests/unit/regression/test_regression_fact_set.py. replay_result는 전용 모델 테스트가 없고 replay/orchestration 테스트 안에서만 부수적으로 exercise된다. CLAUDE.md 구조 규칙 'one test module per source module, mirrors src/ tree'와 불일치.
- **실패 시나리오**: 개발자가 models/replay_result.py에 필드를 추가할 때 tests/unit/models/test_replay_result.py를 찾지만 없어, to_dict/schema_version 불변식이 replay 엔진 테스트 setup에 결합된 채 암묵 검증된다. 엔진 테스트의 assertion이 신규 필드를 커버하지 않으면 직렬화 회귀를 놓치기 쉽다.
- **권고**: 3개 모델의 계약 테스트를 tests/unit/models/ 미러로 이동/추가하거나, 미러 규칙을 명시적으로 완화 문서화한다. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: models/ 8개 중 미러 5개만 존재. localization_finding·regression_fact_set은 진짜 모델 테스트이나 위치 밖, replay_result는 전용 테스트 전무·간접 exercise만. replay_result.py:114/137/157/167에 직렬화 불변식 실재해 미러 부재 시 회귀 유출 가능. 위생/드리프트 → L 적정.

<a id="mod-04"></a>
### MOD-04 [L] 동일한 test-nodeid 개념이 모델마다 node_id vs test_id로 명명 드리프트
- **근거**: `src/novetest/models/replay_result.py:108` — TestResult.node_id(test_result.py:36, docstring 'native engine의 stable test identifier')와 TestTransition.node_id(regression_fact_set.py:80)는 nodeid를 node_id로 부른다. 반면 ReplayResult.test_id(replay_result.py:108)는 docstring에서 명시적으로 'focal divergent test nodeid'라며 같은 nodeid를 test_id로 명명하고, EvidenceCitation.selector의 test_result kind 규약(localization_finding.py:153)도 `{"test_id": <nodeid>, ...}`로 test_id 키를 쓴다. 같은 LocalizationEntry의 related_failed_tests(localization_finding.py:218)는 nodeid 튜플을 값으로 담아 개념적으로 node_id와 동일.
- **실패 시나리오**: AI 에이전트/소비자가 여러 fact set을 조인할 때 동일 test 식별자를 node_id와 test_id 두 이름으로 마주쳐, 예컨대 ReplayResult.test_id를 TestResult.node_id/TestTransition.node_id와 매칭하려면 키 이름을 특수 처리해야 한다. wire 스키마가 이미 v1로 굳어 두 이름이 영속화되므로, 통합 코드/문서가 이 비대칭을 매번 재학습해야 하는 유지비가 발생한다(기능적 오작동은 아니나 계약 일관성 결함).
- **권고**: v1 wire가 동결이라 실제 rename은 schema bump가 필요하므로, 최소한 각 모델 docstring과 계약 문서에 'test_id == node_id (동일 nodeid 개념, 명명 차이는 역사적)'임을 명시. 차기 스키마 정리 시 node_id로 통일 후보로 등록. **(예상 크기: quick-win)**
- **검증 노트**: 인용 file:line 전부 직접 확인, 줄 밀림 없음. ReplayResult.test_id docstring이 nodeid를 test_id로 명명, TestResult/TestTransition은 동일 개념을 node_id로 명명하는 이원화가 코드·docstring상 성립. v1 영속화로 조인 소비자 유지비 시나리오 유효. 계약 일관성/위생 → L 적정.

<a id="mod-05"></a>
### MOD-05 [L] utils/asyncio_subprocess가 Run 팀 전용인데 공유 utils/에 위치
- **근거**: `src/novetest/utils/asyncio_subprocess.py:1` — asyncio_subprocess.run_subprocess의 import는 6개 어댑터(pytest/jest/junit/gotest/cargo/dotnet_adapter.py)와 run/readiness.py:59에 한정 — src 전체에서 소비자가 run/ 뿐. 반면 utils/의 path_utils(coverage·localization·orchestration)와 ulid(memory·run·replay·orchestration)는 진짜 다팀 공유. models/는 8개 도메인 엔티티가 모두 실제 공유로 덤핑그라운드 아님.
- **실패 시나리오**: 공유 utils/ 위치는 '여러 팀이 의존한다'는 계약을 암시하지만 실제 소유·변경 주체는 Run 단독 — 다른 팀이 subprocess 위생(env 정화 등)을 바꿀 때 소유 경계가 모호해지고, Run 전용 세부(자식 env 정화, timeout 규약)가 공유 표면에 노출되어 오사용 유혹. 경계 규율상 run/ 내부 헬퍼로 두는 편이 소유권 명료.
- **권고**: asyncio_subprocess를 run/ 하위(예: run/_subprocess.py)로 이동하거나, 공유 유지 시 utils/README/주석으로 'Run-owned infra'임을 명시. 실질 리스크는 낮아 우선순위 하. **(예상 크기: quick-win)**
- **검증 노트**: grep+Read로 소비자가 run/ 하위뿐임을 확인(6개 어댑터 + readiness.py:59). 대조군 path_utils/ulid은 실제 다팀 공유로 논거 성립. asyncio_subprocess.py:1-9 docstring도 'Native Engine adapters' 전용 명시. 순수 위생 이슈 → L 적정.

## 미확정 관찰

<a id="mod-06"></a>
### MOD-06 [L] dict 필드를 가진 frozen 데이터클래스는 __hash__가 생성되지만 hash 시 TypeError (동결이 해시가능성을 오도)
- **근거**: `src/novetest/models/run_record.py:47` — `@dataclass(slots=True, frozen=True)`는 eq 기본 True와 함께 필드 튜플 기반 __hash__를 생성한다. 그러나 다수 모델이 dict 필드를 보유: RunRecord.summary_counts/artifact_paths/metadata(run_record.py:47-50), FileCoverage.line_contexts(coverage_fact_set.py:123), CoverageFactSet.metadata(:195), EvidenceCitation.selector(localization_finding.py:163), LocalizationEntry.alternate_scores(:217), ReplayResult.consistency_summary(replay_result.py:111), RegressionFactSet.metadata(regression_fact_set.py:299). dict은 unhashable이므로 hash(instance)는 호출 시점에 `TypeError: unhashable type: 'dict'`를 던진다. (TestResult/RunReference/CoverageSummary 등 스칼라-only 모델은 정상 해시 가능.) 소스 전역에서 현재 이들 복합 모델을 set/dict-key로 쓰는 사이트는 발견되지 않음.
- **실패 시나리오**: frozen=True를 보고 해시 가능한 값 객체로 오인한 장래 코드가 예컨대 set(records)로 run 중복 제거, dict[RunRecord]로 캐시, 또는 functools.lru_cache로 이들 모델을 인자화하면 런타임에 `TypeError: unhashable type: 'dict'`로 즉시 실패한다. 현재는 호출자가 없어 잠복 상태이나, frozen이 부여하는 불변성 계약과 실제 해시 불가 상태의 괴리가 함정으로 남아 있음.
- **권고**: 의도가 '해시 불가한 불변 값'이면 데코레이터는 유지하되 클래스 docstring에 '해시 불가(가변 dict 필드 보유)'를 명시. 해시가 필요하면 dict 필드를 정렬된 tuple(items)로 보관하거나 MappingProxyType/frozendict 도입 후 커스텀 __hash__ 제공. 최소한 오도를 막는 문서화가 quick-win. **(예상 크기: quick-win)**
- **검증 노트**: 인용 file:line 전부 실재·정확하고 메커니즘(frozen+eq → 튜플 __hash__ 생성, dict 필드 해싱 시 TypeError)도 코드상 참. **미확정 사유**: 실제 발현은 이들 복합 모델을 set/dict-key/lru_cache로 쓰는 호출자가 있어야 하나 소스 전역에 부재(to_dict만 dict 필드 소비, 해시 경로 미사용). 결함은 잠복 상태이며 발현이 존재하지 않는 미래 코드에 의존 → uncertain. 순수 위생 사안, L 적정.
