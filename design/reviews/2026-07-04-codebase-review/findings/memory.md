# Memory 엔진 + Project Store findings

스코프: `src/novetest/memory/`의 run-evidence 영속화(`store.py`)와 file-only Project Store 라이프사이클(`project_store.py`)의 동시성·원자성·데이터 무결성 검토. 집계 — 확정 M 2건 / L 2건 (H 0건), 미확정 1건.

## 확정 findings

<a id="mem-01"></a>
### MEM-01 [M] 동시 run+reset: wipe의 rename가 store_run_evidence의 mkdir(parents=True)와 경합해 run이 조용히 유실
- **근거**: `src/novetest/memory/project_store.py:421` — `wipe_project_store`는 `store_path`(=.novetest)를 통째로 staging으로 rename한다(project_store.py:420-421, 이후 :422 rmtree). 한편 `store_run_evidence`는 이미 해석해둔 `store.path` 아래로 `run_dir.mkdir(parents=True, exist_ok=False)`(store.py:71)를 수행한다. 두 경로 어디에도 파일 락/조율이 없다(memory 전역에서 flock/fcntl/lock 부재 확인).
- **실패 시나리오**: 프로세스 A가 `novetest run`(store_run_evidence)을, 프로세스 B가 `novetest reset`을 동시에 실행할 때, B가 .novetest를 staging으로 rename한 뒤 A의 `mkdir(parents=True)`가 옛 경로에 대해 실행되면 누락된 중간 디렉토리를 새로 만들며 store.json 없는 부분 .novetest 스켈레톤을 되살린다. A의 record.json은 그 스켈레톤에 기록되지만 `find_nearest_store`가 store.json 없는 .novetest를 store로 인정하지 않고 지나쳐(project_store.py:254-259, 268) 해당 run이 영구 고아가 된다. B의 rmtree는 staging본만 지운다. 결과적으로 A의 run 증거가 조용히 사라진다.
- **권고**: 파괴적 프리미티브(wipe)와 store_run_evidence 사이에 store 루트 존재 재검증 또는 워크스페이스 단위 어드바이저리 락 도입을 검토한다. 최소한 store_run_evidence가 mkdir 전에 store.json 존재를 재확인하고, 부재 시 domain 오류로 실패하도록 해 고아 스켈레톤 생성을 막는다. **(예상 크기: 1-cycle)**
- **검증 노트**: 인용 사실 전부 실재·정확. TOCTOU 재현 논리 검증됨. run+reset 동시 실행이라는 좁은 타이밍 전제에 의존하고 전형적 직렬 CLI 워크플로에서 확률이 낮아 M 적정(H 미격상).

<a id="mem-02"></a>
### MEM-02 [M] 툼스톤이 rename-후-mutate 순서라 크래시 시 status/tombstoned_at 불변식 위반 상태로 고착
- **근거**: `src/novetest/memory/store.py:179` — `delete_run_evidence`는 `resolved.run_dir.rename(tombstone_dir)`(store.py:179)를 먼저 하고, 그다음 `tombstoned_record`(status="tombstoned", metadata["tombstoned_at"]=...)를 tombstone_dir/record.json에 write_text(store.py:181-190)한다. 두 스텝 사이 크래시면 레코드는 tombstone 위치에 있으나 내용은 원본(status가 예: "passed", metadata에 tombstoned_at 없음)이다. `_resolve`는 위치 기반으로 tombstoned=True를 매기지만 tombstoned_at은 `metadata.get`→None(store.py:236-237). 재-delete는 resolved.tombstoned=True에서 즉시 no-op 반환(store.py:168-175)이라 재스탬핑이 없어 영구 고착. MemoryEntry docstring(memory_entry.py:33)은 "tombstoned_at is non-null exactly when soft-deleted"를 계약한다.
- **실패 시나리오**: delete 도중(rename 성공, 2차 write 전) 크래시하면 해당 run은 이후 영구적으로 tombstoned로 보이면서 tombstoned_at=None·status=원본값을 유지한다 — MemoryEntry 불변식을 깨고, `get_memory_entry_availability`/`list_run_history`가 tombstone 시각 없는 소프트삭제 항목을 노출한다. 재삭제해도 no-op이라 자가치유 불가.
- **권고**: 순서를 뒤집어 원자화한다 — 갱신된 tombstoned record를 live run_dir(또는 tmp)에 먼저 기록한 뒤 단일 rename으로 tombstone 위치로 이동. 그러면 rename 하나가 완전히 갱신된 레코드를 옮겨 부분상태가 사라진다. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: 인용된 모든 경로가 실재·일치. 비원자 2스텝(179 rename → 187 write)과 재-delete no-op 고착, memory_entry.py:32-33 불변식 위반까지 코드상 성립. 크래시라는 좁은 창에 조건부이고 위치 기반 tombstoned 플래그는 여전히 True라 상시 손상은 아니므로 M 적정.

<a id="mem-03"></a>
### MEM-03 [L] wipe rmtree 실패 시 .novetest.deleting.<ulid> staging 트리가 영구 누수(청소·재수확 없음)
- **근거**: `src/novetest/memory/project_store.py:422` — `wipe_project_store`는 rename로 store를 staging으로 분리(project_store.py:421) 후 `shutil.rmtree(staging, ignore_errors=False)`(project_store.py:422)를 호출한다. docstring(project_store.py:403-407)은 rmtree가 raise하면 "orphaned staging dir은 caller 문제"라 인정하나, 코드 어디에도 staging 재수확/청소 로직이 없다. `create_project_store`·`locate_project_store`는 .novetest 이름만 보므로 `.novetest.deleting.*`는 영원히 무시된다.
- **실패 시나리오**: rmtree가 중간 파일 권한 오류 등으로 raise하면 store는 이미 분리된 상태로, 부분 삭제된 `.novetest.deleting.<ulid>` 트리가 워크스페이스 부모에 남는다. WipeReport는 반환되지 않고(예외 전파) 재시도 시 store_path에 store.json이 없어 `ProjectStoreNotFoundError`(uninitialized)만 나므로, 고아 트리는 툴에 보이지 않은 채 디스크를 계속 점유한다. 반복 실패 시 누적.
- **권고**: init/reset 진입 시 워크스페이스 부모의 `.novetest.deleting.*` 스테이징 잔재를 best-effort 재수확(rmtree)하는 스윕을 추가하거나, wipe 실패 시 staging 경로를 WipeError에 실어 Orchestration이 사용자에게 정리를 지시한다. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: 인용 코드 실재·일치. `_STAGING_DIR_PREFIX`는 생성에만 쓰이고 재수확/sweep 참조가 src/novetest/ 전체에 전무. 다만 예외가 Orchestration으로 전파되어 store-wipe-failed로 통지되므로 완전 침묵은 아님 — 드문 실패 경로의 디스크 누수(위생)라 L 적정.

<a id="mem-04"></a>
### MEM-04 [L] stored_at을 영속 필드가 아닌 파일 mtime에서 유도 — store/retrieve 값 불일치 및 FS 조작에 취약
- **근거**: `src/novetest/memory/store.py:94` — `store_run_evidence`는 stored_at을 wall-clock int(`time.time()*1000`)(store.py:77)로 만들어 반환하지만, `retrieve_run_evidence`(store.py:94)·`list_run_history`(store.py:107)·`find_runs_for_target`(store.py:143)은 `_path_mtime_ms(record.json)`(store.py:280-281)로 재유도한다. record.json에는 stored_at이 직렬화되지 않는다(RunRecord.to_dict에 없음 — run_record.py:53-69). `delete_run_evidence`는 tombstone record.json을 재작성(store.py:187)하므로 mtime이 삭제 시각으로 갱신된다.
- **실패 시나리오**: 동일 run을 store 직후 반환한 stored_at과 이후 retrieve로 얻은 stored_at이 원리상 다른 소스(벽시계 vs mtime)라 미세하게 어긋난다. 툼스톤 후에는 stored_at이 원 저장 시각이 아니라 삭제 시각을 보고한다. 또한 git checkout/백업 복원/클라우드 동기화가 record.json의 mtime을 바꾸면 사용자에게 노출되는 stored_at이 실제 저장 시점과 무관하게 이동한다.
- **권고**: stored_at을 record.json(또는 별도 사이드카)에 영속 필드로 기록하고 retrieve/list가 그 값을 읽게 해 mtime 의존을 제거한다. 툼스톤 시에도 원 stored_at을 보존하고 tombstoned_at을 별도로 유지한다. **(예상 크기: quick-win(≤반나절))**
- **검증 노트**: 인용 file:line 실재·일치. RunRecord 데이터클래스/to_dict에 stored_at 부재 확인 — mtime 재유도가 유일 소스. 정렬은 created_at 기준(store.py:116,152)이라 데이터 손상/오결론으로 이어지지 않는 정보성 필드이므로 L 유지.

## 미확정 관찰

<a id="mem-05"></a>
### MEM-05 [H→미확정] 레코드 1개가 손상/미래스키마면 전체 history 스캔이 uncaught 예외로 붕괴
- **근거**: `src/novetest/memory/store.py:275` — `_read_record`(store.py:275-277)는 `path.read_text` 후 `RunRecord.from_dict(json.loads(raw))`를 try/except 없이 호출한다. json.loads는 잘린 JSON에서 JSONDecodeError를, RunRecord.from_dict는 schema_version!=1이면 ValueError(run_record.py:85-89)·필수키 누락 시 ValueError(run_record.py:116-119)를 던진다. `_iter_all_records`(store.py:249-272)는 rglob(record.json) 결과마다 `_read_record`를 호출하며 예외를 걸러내지 않아 `list_run_history`(store.py:106-116)/`find_runs_for_target`(store.py:138-151)의 리스트 컴프리헨션에서 그대로 전파된다. 소비자: cli memory list/show(app.py:739,757,778,863), regression/compare.py(715), regression/retrieval.py(128), localization/derive.py(1094).
- **실패 시나리오**: 단 하나의 record.json이 (a) torn write로 잘렸거나, (b) 클라우드 동기화/부분 git checkout로 미완성이거나, (c) 신형 novetest가 같은 store에 schema_version=2로 기록한 뒤 구형 novetest가 읽으면 — memory list, memory show(다른 run조차), regression compare, localization derive의 baseline/history 워크가 전부 uncaught 예외로 죽는다. 나쁜 항목 1건을 건너뛰는 격리가 없어 all-or-nothing으로 히스토리 전체가 소실된다.
- **권고**: `_iter_all_records`/`_read_record`에 per-record 격리를 추가한다 — 파싱 실패 레코드는 스킵하고 warnings로 표면화(또는 quarantine 목록 반환). retrieve_run_evidence처럼 특정 run 지목 경로는 loud 유지하되, 전체 스캔(list/find)은 개별 오류가 나머지를 오염시키지 않도록 분리한다. **(예상 크기: 1-cycle)**
- **검증 노트 (왜 미확정)**: 코드 사실관계는 전부 실재·정확하다(무방어 파싱·격리 없는 반복·ValueError/JSONDecodeError 경로). 그러나 H 심각도가 미확정 — 1차 판정은 H였으나 2차 재검에서 (1) 피해가 무결성/오판이 아닌 가용성·복원력 문제(app.py:1960-1973의 최상위 catch-all이 uncaught 예외를 code="cli-error" 구조화 envelope로 변환하므로 loud·복구가능, 나머지 레코드는 디스크에 온전), (2) 트리거 빈도가 낮음(torn write는 극히 짧은 창, 클라우드/부분 checkout은 특이 셋업, schema_version=2 skew는 현재 단일버전 SCHEMA_VERSION=1이라 아직 불가능), (3) 파일 1건 제거로 복구 가능 — 을 근거로 M로 하향 주장이 제기됐다. all-or-nothing 블라스트 반경과 memory list 자체가 죽어 self-serve 진단이 막히는 wedge는 실질 결함이나 L은 과함. 두 판정(H vs M) 사이에서 미해소 상태이므로 미확정으로 남긴다.
