---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-09
slug: windows-path-normalization-fix
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/tasks/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md
---

# Task — Localization `_normalize_to_workspace_relative` Windows fix (4 tests)

## Mission

2026-06-08 B2-2 슬라이스가 도입한 `_normalize_to_workspace_relative`
helper가 Windows에서 drive prefix 손실 + path separator 비정렬 발생.
어제 머지된 슬라이스가 곧바로 Windows CI에 4 failures 추가했고, B2 cycle
의 "PASSED" verdict가 Linux/macOS 기준이었음을 명시적으로 surface함. 본
슬라이스는 그 회귀를 정정.

## Background — self-contained

수신 팀이 이 대화를 볼 수 없으므로 컨텍스트 자체 포함.

### B2-2 슬라이스 (2026-06-08) 회귀

어제 머지된 `51ea1b6` "feat(localization): B2 UX normalization — mode-
invariant metadata keys + workspace-relative paths"의 `_normalize_to_workspace_
relative` helper가 `Path.relative_to`를 사용. 의도:
- `failure_proximity` mode의 `code_location.file`을 workspace-relative로
  정규화 (envelope shape 통일)
- outside-workspace path는 absolute 유지 ("not your code" semantic cue)

Linux/macOS에서 동작 정상. **Windows에서 실패**:
- `Path.relative_to`가 drive prefix를 절단 → `'Users\\runneradmin\\...\\src\\foo.py'`
  같은 path 생성 (no `C:`)
- 또는 cross-drive (`D:\workspace` vs `C:\Users\runner\...`)에서
  ValueError

### 실패 inventory (4 tests)

```
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_workspace_internal_path_normalized_to_relative
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_path_outside_workspace_kept_absolute
FAILED tests/unit/localization/test_derive_failure_proximity.py::test_absolute_and_relative_for_same_file_collapse_to_relative
FAILED tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top
```

### B2-2 WORKLOG의 self-aware deferred

B2-2 슬라이스 WORKLOG entry §"Gotcha #2"에 적혀 있는 내용:

> "`Path.resolve()` deliberately NOT called on either side of the
> relative_to comparison ... a future cycle adds resolve() if Manual
> Test surfaces a real-host symlink scenario where the absolute-
> fallthrough confuses operators."

**그 "future cycle"이 본 슬라이스. 단지 Manual Test가 아니라 Windows
CI가 surface한 형태.** 또 issue가 `.resolve()`가 아니라 `Path.relative_to`
의 cross-drive/drive-prefix 문제 — 다른 fix shape 필요.

## PM 권장 Fix shape

Coverage parsers의 scenario A 패턴 (B2-3 amendment) 따름:

```python
def _normalize_to_workspace_relative(file_path: Path, workspace_root: Path) -> Path:
    """Normalize file_path to workspace-relative POSIX form when possible."""
    # outside-workspace check: keep absolute (semantic "not your code" cue per B2-2)
    if _is_outside_workspace(file_path, workspace_root):
        return file_path  # absolute, deliberately

    # inside-workspace normalize to workspace-relative POSIX
    try:
        rel = file_path.relative_to(workspace_root)
    except ValueError:
        # cross-drive or drive-prefix loss case (Windows D:↔C:)
        rel = Path(os.path.relpath(file_path, workspace_root))
    return Path(rel.as_posix())  # POSIX separator across OSes
```

핵심:
- `os.path.relpath` fallback이 cross-drive를 처리
- `.as_posix()`로 separator 정규화 (Windows에선 `\` → `/`)
- outside-workspace 판정은 그대로 유지 (B2-2 의도 보존)

### outside-workspace 판정 자체도 cross-drive 안전 필요

B2-2의 `_is_outside_workspace` (또는 동등 함수)도 `Path.relative_to`나
`is_relative_to`를 사용한다면 cross-drive에서 잘못된 판정 위험. Phase
1에서 audit 후 같은 패턴 적용:

```python
def _is_outside_workspace(file_path: Path, workspace_root: Path) -> bool:
    try:
        file_path.relative_to(workspace_root)
        return False  # inside
    except ValueError:
        return True  # outside (cross-drive 도 outside로 분류 — workspace_root와 무관)
```

이 경우 cross-drive path는 outside-workspace로 처리됨 — `failure_proximity`
의 "not your code" semantic과 자연 정렬 (다른 drive면 사용자 코드 아닐
가능성 큼).

## Scope

### In scope

- `_normalize_to_workspace_relative` helper에 cross-drive ValueError 안전성 추가
- `.as_posix()`로 envelope에 들어가는 path가 POSIX separator 보장
- outside-workspace 판정 (`_is_outside_workspace` 또는 동등)도 cross-drive 안전성
- 4개 failing tests Windows 그린
- Linux/macOS 동작 unchanged (regression 없음)

### Out of scope

- B2-2 슬라이스의 의도적 design 변경 (mode-invariant metadata 키 셋,
  outside-workspace absolute 유지 등 unchanged)
- 다른 mode (sbfl_*)의 path 처리 (B2-2가 이미 workspace-relative 처리 —
  본 슬라이스 unrelated)
- `Path.resolve()` 추가 (B2-2 WORKLOG의 cross-platform 고려 그대로 — 본
  슬라이스는 `os.path.relpath` 패턴이 더 적합)
- `cli/output.py`, `run/types.py`, 다른 팀 territory

## 파일 footprint 가이드

- `src/novetest/localization/failure_proximity.py` (또는 helper가 있는
  파일)
- `tests/unit/localization/test_derive_failure_proximity.py`
- `tests/integration/localization/test_failure_proximity_e2e.py`

## Definition of done

1. ✅ `_normalize_to_workspace_relative` (또는 동등) cross-drive ValueError
   안전 + `.as_posix()` separator 정규화
2. ✅ `_is_outside_workspace` (또는 동등) cross-drive 안전성 audit + 필요
   시 동일 패턴 적용
3. ✅ 4 failing tests Windows에서 그린
4. ✅ Linux/macOS 동작 unchanged — 기존 B2-2 verdict criteria (mode-
   invariant metadata 셋, outside-workspace deliberately absolute 등)
   단위 + 통합 테스트 그대로 그린
5. ✅ B2-2 cycle의 "Localization vs Coverage outside-workspace asymmetry"
   PM disposition (의도적 비대칭) 그대로 — `failure_proximity` outside-
   workspace는 absolute 유지, Coverage는 `../`-prefixed relpath
6. ✅ `uv run mypy --strict src/novetest` 클린
7. ✅ `uv run pytest -q tests/unit tests/integration` 그린 (equipped host)
8. ✅ **CI matrix verdict criterion**: 본 슬라이스 머지 후 `ci.yml` run에서
   Localization 관련 4 tests Windows × 3 Python 3 cells 그린. PM이
   verification doc에 cite할 `ci.yml` run number 명시.
9. ✅ WORKLOG.md 엔트리 (charter 양식)
10. ✅ Handoff `agent-comms/handoffs/localization-team-2026-06-09-windows-path-normalization-fix.md`
    + DoD bullets believed closed
11. ✅ `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **Windows CI fix parallel triple의 2/3**. 같은 cycle에:

- Coverage팀: cross-drive ValueError + LCOV separator literal 수정
  (`tasks/coverage-team-2026-06-09-windows-parser-fixes.md`)
- Run팀: JUnit Windows OS-gate test fixes (test-only)
  (`tasks/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Localization (본 슬라이스) | `src/novetest/localization/` + 관련 tests |
| Coverage (페어 1) | `src/novetest/coverage/` + 관련 tests |
| Run (페어 2) | `tests/{unit,integration}/run/` (test-only) |

### 만지지 말 것

- `cli/output.py::EnvelopeWarning` shape (06-07 freeze)
- `run/types.py::AdapterWarning` shape
- `coverage/**`, `run/**`, `regression/**`, `replay/**`
- v1 metadata bridge 키 — post-MVP cleanup
- B2-2 의 design intent (mode-invariant metadata, outside-workspace
  asymmetry) — 본 슬라이스는 Windows 안전성 추가만; B2-2 contract 보존

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### 새 verdict 기준 — CI matrix green (메타-decision §1 보강)

`decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
§1 SHOULD tier 적용 + 본 cycle의 **CI matrix verdict 추가**:

각 슬라이스의 verification doc은:
1. **Equipped-host verification** (메타-decision §1): Manual Test가
   equipped host에서 단위 + 통합 테스트 그린
2. **CI matrix verdict** (이 cycle 신규): 본 슬라이스 머지 후 `gh run`
   query로 `ci.yml` 가장 최근 run에서 본 슬라이스 관련 tests가 Windows ×
   3 Python = 3 cells 그린 + run number cite

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native adapter src를 만지지 않음 → §2.5 file-glob 발동
**안 함**. 일반 host에서 진행 OK.

## Implementation guidance

### B2-2 의도 보존 — outside-workspace asymmetry

`history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md`
§"Load-bearing lessons" #4에서 PM이 비준한 정책:

> "Coverage: every file in the report is 'code under test.' An outside-
> workspace file is still part of the coverage corpus ... Surface it as
> navigation-friendly relpath
>
> Localization (failure_proximity): outside-workspace paths are stdlib
> frames, `/rustc/<hash>/...`, third-party traceback frames — explicitly
> 'not your code.' Keeping them absolute is a visual cue to the reader:
> 'the bug isn't here.'"

본 슬라이스는 이 정책 **변경 없음**. inside-workspace path만 cross-
drive 안전성 추가. outside-workspace는 absolute 유지 (Windows에서도).

### Test reproducer — cross-drive 시뮬레이션

```python
def test_cross_drive_path_falls_back_to_relpath(monkeypatch):
    workspace_root = Path("D:/workspace") if sys.platform == "win32" else Path("/workspace")
    file_path = Path("C:/Users/runner/file.py") if sys.platform == "win32" else Path("/elsewhere/file.py")
    # 의도: cross-drive (Win) 또는 outside-workspace (POSIX) — outside로 처리되어 absolute 유지
    result = _normalize_to_workspace_relative(file_path, workspace_root)
    assert result.is_absolute()  # outside-workspace deliberately absolute
```

또는 inside-workspace + drive prefix 회복:
```python
def test_inside_workspace_cross_drive_normalizes(monkeypatch):
    # monkey-patch Path.relative_to to raise ValueError
    # then assert os.path.relpath fallback produces correct result
```

### CI matrix verdict 명령

```bash
gh run list --workflow ci.yml --branch main --limit 3
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

## Reference

- `agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md`
  — 본 cycle의 cycle-close history + B2-2 회귀 narrative (§"Load-bearing
  lessons" #2)
- `agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md`
  — B2-2 슬라이스 history + outside-workspace 정책
- `.claude/agents/novetest-localization-team.md` — 팀 charter

## 추정

- Phase 1 audit: ~10-15분 (`_normalize_to_workspace_relative` +
  `_is_outside_workspace` 두 함수만)
- Phase 2 fix: ~15-30분
- Phase 3 tests: ~20-30분
- Wall time: **~1시간**
- 단일 cycle, 단일 attempt 예상
