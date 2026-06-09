---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-06-09
slug: windows-parser-fixes
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
---

# Task — Coverage parsers Windows cross-platform fixes (4 tests)

## Mission

Coverage parsers가 Windows × Python 3.11/3.12/3.13에서 RED 상태. `ci.yml`
가 2026-06-01 이후 9일 chronic. 4개 failing tests를 클리어해서 CI matrix
green 복구에 기여. cargo LCOV path 정규화 패턴 (2026-06-08 amend 시 도입)
을 다른 affected parsers (cobertura, derive_xunit)로 확장.

## Background — self-contained

수신 팀이 이 대화를 볼 수 없으므로 컨텍스트 자체 포함.

### MVP release-readiness assessment 발견

2026-06-09 Release team의 readiness assessment에서 surface된 단일 blocker:
`ci.yml` Windows × 3 Python = 3 cells RED, **20 failing tests per cell**,
chronic since 2026-06-01 (30+ consecutive red runs). 그 중 5 tests가
Coverage team territory:

```
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlBasic::test_fixture_coverlet_basic_yields_one_file_fully_covered
FAILED tests/unit/coverage/test_cobertura_parser.py::TestParseCoberturaXmlMultiClass::test_fixture_partial_coverage_yields_two_files
FAILED tests/unit/coverage/test_derive_xunit.py::test_derive_xunit_all_sources_unresolvable_returns_sources_not_found
FAILED tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning
```

(test_cobertura + test_derive_xunit 사이 3개 + LCOV 1개 = 4 unit tests)

### Category A — `Path.relative_to` cross-drive ValueError (3 tests)

```
ValueError: path is on mount 'D:', start on mount 'C:'
```

Windows `Path.relative_to`는 서로 다른 drive letter일 때 ValueError 발생.
GitHub Actions Windows runner는 `runner.temp`가 `C:\...`, `GITHUB_WORKSPACE`
가 `D:\a\Nove-Test\Nove-Test\` — 자연스러운 cross-drive setup. **실제
Windows 사용자 (D: drive 사용 등) 환경 그대로 reproduce**.

영향 파일 추정:
- `src/novetest/coverage/cobertura_parser.py`
- `src/novetest/coverage/derive_xunit.py` (또는 동등 — derive_xunit_cobertura helper)
- 다른 parser들 내부에 동일 패턴이 있을 수 있음 → grep 으로 audit

### Category B — LCOV Windows path-separator literal (1 test)

```
FAILED tests/unit/coverage/test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning
```

테스트가 `'/ws/cargo-project' in warning_text` 어설션. Windows에선
warning text가 `'\\ws\\cargo-project'`. **production code의 relpath
fallback IS firing** (B2-3 cycle에서 적용된 normalize) — 테스트만 POSIX
separator literal pinning.

### B2-3 cycle 정렬 — 이미 채택된 패턴

`decisions/2026-05-15-coverage-facts-json-layout.md` "Amendment 2026-06-08"
constraint #6은 outside-workspace path를 `../`-prefixed POSIX relpath로
정규화. cargo LCOV (`lcov_parser.py`)와 istanbul은 이 패턴 따름. **본
슬라이스는 같은 scenario A 패턴을 cobertura + derive_xunit에 확장**.

## Scope

### Phase 1 — Parser audit (15-30분)

5개 parsers (`coverage_parser`, `istanbul_parser`, `lcov_parser`,
`jacoco_parser`, `cobertura_parser`) + derive helpers (특히 `derive_xunit`)
의 path-handling 코드를 grep:

```bash
grep -n "Path.*relative_to\|\.relative_to(" src/novetest/coverage/
```

각 hit이 cross-drive ValueError 위험 있는지 판정:
- workspace_root 기준으로 file path를 narrow한다면 → ValueError risk
- 이미 `try/except ValueError` + `os.path.relpath` fallback 있다면 → OK

### Phase 2 — Apply scenario A pattern to affected parsers

```python
try:
    relpath = Path(file_path).relative_to(workspace_root)
except ValueError:
    # cross-drive / outside-workspace case
    relpath = Path(os.path.relpath(file_path, workspace_root)).as_posix()
```

또는 unconditional `os.path.relpath`:
```python
relpath = Path(os.path.relpath(file_path, workspace_root)).as_posix()
```

PM 권장: **unconditional `os.path.relpath` + `.as_posix()`**. 이유:
- try/except 코드 복잡도 증가
- `os.path.relpath`는 same-drive면 자연스럽게 동작, cross-drive면 fallback
- `.as_posix()`로 separator-agnostic 보장 (Windows에선 `\` → `/`)
- B2-3 amendment의 "Universal contract `not Path(file_path).is_absolute()`"와 자연 정렬

### Phase 3 — LCOV warning text 정규화

`test_lcov_parser.py::test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning`
의 fix 두 옵션:

| 옵션 | 위치 | 효과 |
|---|---|---|
| (α) | `src/novetest/coverage/lcov_parser.py` — warning text 작성 시 `.replace(os.sep, '/')` 또는 `Path(...).as_posix()` | **PM 권장** — warning text가 user-facing/AI-facing이라 POSIX separator가 일관됨 |
| (β) | `tests/unit/coverage/test_lcov_parser.py` — assertion을 separator-agnostic하게 | 테스트만 수정, production 동작 그대로 |

PM 권장 = **(α)**. envelope 일관성 + user 친화. warning emitter가 separator normalize 후 emit.

### Phase 4 — Tests

각 fix에 대해:
- 단위 테스트가 Windows + non-Windows 양쪽 패턴 검증 (mock workspace_root cross-drive simulation 또는 platform-specific 케이스)
- 통합 테스트: 기존 테스트가 그대로 그린 (regression 없음)

## Out of scope

- Phase 1 audit에서 발견된 추가 비대칭이 있다면 별도 cycle로 분리 (특히
  `coverage_parser`, `jacoco_parser`가 cross-drive 패턴 가지면 stand-
  alone)
- `lcov_warnings` channel의 구조 변경 (B2-3에서 이미 freeze — 본 슬라이스는
  warning text의 separator만 정규화)
- Cobertura parser의 path resolution 로직 자체 (sources 처리 등)
- 다른 팀 territory

## 파일 footprint 가이드

- `src/novetest/coverage/cobertura_parser.py` (Phase 2)
- `src/novetest/coverage/derive_xunit.py` 또는 동등 (Phase 2)
- `src/novetest/coverage/lcov_parser.py` (Phase 3 옵션 α)
- 추가 parsers (audit 결과 따라)
- `tests/unit/coverage/test_cobertura_parser.py`
- `tests/unit/coverage/test_derive_xunit.py`
- `tests/unit/coverage/test_lcov_parser.py`

## Definition of done

1. ✅ Phase 1 parser audit 결과 handoff에 명시 (어느 parser가 cross-drive
   ValueError risk를 가지는지 매트릭스)
2. ✅ Category A (3 tests) Windows에서 그린 — cross-drive ValueError 해결
3. ✅ Category B (1 test) Windows에서 그린 — LCOV warning text POSIX
   separator
4. ✅ Universal contract `not Path(f.file_path).is_absolute()` (B2-3 amend
   contract) 유지 — 변경 없음 확인
5. ✅ `uv run mypy --strict src/novetest` 클린
6. ✅ `uv run pytest -q tests/unit tests/integration` 그린 (Linux 또는 macOS
   equipped host)
7. ✅ **CI matrix verdict criterion**: 본 슬라이스 머지 후 `ci.yml` run에서
   Coverage 관련 4 tests가 Windows × 3 Python = 3 cells 모두 그린. PM이
   verification doc에 cite할 `ci.yml` run number 명시.
8. ✅ WORKLOG.md 엔트리 (charter 양식)
9. ✅ Handoff `agent-comms/handoffs/coverage-team-2026-06-09-windows-parser-fixes.md`
   + DoD bullets believed closed
10. ✅ `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **Windows CI fix parallel triple의 1/3**. 같은 cycle에:

- Localization팀: `_normalize_to_workspace_relative` Windows drive-prefix 수정
  (`tasks/localization-team-2026-06-09-windows-path-normalization-fix.md`)
- Run팀: JUnit Windows OS-gate test fixes (test-only)
  (`tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Coverage (본 슬라이스) | `src/novetest/coverage/` + 관련 tests |
| Localization (페어 1) | `src/novetest/localization/` + 관련 tests |
| Run (페어 2) | `tests/{unit,integration}/run/` (test-only; src 변경 없음) |

### 만지지 말 것

- `cli/output.py::EnvelopeWarning` shape (06-07 freeze)
- `run/types.py::AdapterWarning` shape
- `localization/**`, `run/**`, `regression/**`, `replay/**`
- v1 metadata bridge 키 (`coverage_unavailable_*`) — post-MVP cleanup
- B2-3 amendment의 contract (constraint #6 그대로 — Windows fix는
  amendment 보강이지 변경 아님)

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### 새 verdict 기준 — CI matrix green (메타-decision §1 보강)

`decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
§1 "Manual Test verification host = equipped, by default" + 본 cycle의
**CI matrix verdict 추가**:

각 슬라이스의 verification doc은 다음 둘 모두 명시:
1. **Equipped-host verification** (메타-decision §1 SHOULD tier): Manual
   Test가 equipped host에서 단위 + 통합 테스트 그린 확인
2. **CI matrix verdict** (이 cycle 신규): 본 슬라이스 머지 후 `gh run`
   query로 `ci.yml` 가장 최근 run 에서 본 슬라이스 관련 tests가 Windows
   × 3 Python = 3 cells 그린 확인 + run number cite

CI matrix 9 cells 모두 green = 3 슬라이스 모두 통합 후 달성. 본 슬라이스
단독으로는 Coverage 관련 4 tests의 Windows 그린만 verdict 기준.

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native adapter src를 만지지 않음 (Coverage parsers는
adapter 아님) → §2.5 file-glob 발동 **안 함**. 일반 host에서 진행 OK.

## Implementation guidance

### grep 시작점

```bash
# Phase 1 audit
grep -rn "\.relative_to(" src/novetest/coverage/
grep -rn "Path.*relative" src/novetest/coverage/

# LCOV warning text
grep -n "lcov_warnings\|warning.*\\\\\|warning.*os.sep" src/novetest/coverage/lcov_parser.py
```

### Test reproducer — Windows 시뮬레이션

Linux/macOS 호스트에서 cross-drive 시뮬레이션은 monkey-patch 필요:
```python
def test_cross_drive_fallback(monkeypatch):
    # simulate Windows cross-drive ValueError
    def _raising_relative_to(self, *args):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")
    monkeypatch.setattr(Path, "relative_to", _raising_relative_to)
    # ... assert os.path.relpath fallback fires
```

또는 production code가 `try/except ValueError` 명시할 거라면 그 branch를
직접 단위 테스트로 호출.

### CI matrix verdict 확인 명령

```bash
# 본 슬라이스 머지 후 (Main Branch가 수행 또는 handoff에 명시)
gh run list --workflow ci.yml --branch main --limit 3
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

## Reference

- `agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md`
  — 본 cycle의 cycle-close history + load-bearing lessons
- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`
  §"Amendment 2026-06-08" constraint #6 — universal `not is_absolute()`
  contract + scenario A 패턴
- `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`
  (cycle-close에서 삭제됨; 발견 디테일은 history에 distill됨)
- `.claude/agents/novetest-coverage-team.md` — 팀 charter

## 추정

- Phase 1 audit: ~15-30분
- Phase 2-3 fix: ~30-60분
- Phase 4 tests: ~30-60분
- Wall time: **1-2시간**
- 단일 cycle, 단일 attempt 예상
