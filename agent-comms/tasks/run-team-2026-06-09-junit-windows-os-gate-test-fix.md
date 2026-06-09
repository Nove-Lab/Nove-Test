---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-06-09
slug: junit-windows-os-gate-test-fix
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/tasks/coverage-team-2026-06-09-windows-parser-fixes.md
  - agent-comms/tasks/localization-team-2026-06-09-windows-path-normalization-fix.md
---

# Task — Run team JUnit Windows OS-gate test fixes (12 tests, test-only)

## Mission

JUnit adapter는 Windows를 **의도적으로 차단** (decision `2026-06-03-junit-
console-launcher-vendor.md` §R5; foundations Open Q #16 Windows binary
pipeline 미구현). production code는 `engine-misconfigured` 응답으로
정상 동작. **테스트만 OS gate를 처리 못 함** — Linux/macOS에서 작성된
12개 tests가 Windows CI에서 fail. 본 슬라이스는 **test-only fix**.

## Background — self-contained

수신 팀이 이 대화를 볼 수 없으므로 컨텍스트 자체 포함.

### JUnit adapter Windows OS gate (decision 명시)

`decisions/2026-06-03-junit-console-launcher-vendor.md` §"Risks (carried
into the JUnit adapter cycle cycle brief)" §Windows:

> "The JUnit adapter MUST gate on OS support and emit
> `engine-misconfigured` of kind `os-unsupported` with the message ...
> until that gap closes."

JUnit adapter는 Windows에서 `state == "engine-misconfigured"` +
message "JUnit adapter requires a non-Windows host until the Windows
binary pipeline ships (Open Question #16)" 반환. **adapter는 정상**.

### 실패 inventory (12 tests, 2 categories)

#### Category D — JUnit subprocess UnicodeDecodeError (1 test)

```
FAILED tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 226: invalid start byte
```

Windows에서 `subprocess.run(..., text=True)`는 host의 cp1252 locale
codec 사용. byte `0x97`은 UTF-8 invalid start이지만 cp1252 (Latin small
letter `ó` 근방)에서는 valid. subprocess output에 Windows-1252-encoded
character 포함된 경우 decode 실패.

**같은 패턴이 Release team `tests/release/test_install_script.py::_run_install_script`에서
이미 해결됨** (commit `12cf04d` 2026-05-21: `encoding="utf-8"` 추가).

#### Category E — JUnit Windows OS gate not handled by tests (11 tests)

```
FAILED tests/unit/run/test_junit_readiness.py::test_ready_when_java_and_mvn_present
FAILED tests/unit/run/test_junit_readiness.py::test_missing_jdk
FAILED tests/unit/run/test_junit_readiness.py::test_missing_mvn
FAILED tests/unit/run/test_junit_readiness.py::test_missing_jupiter
FAILED tests/unit/run/test_junit_readiness.py::test_junit4_specific_diagnostic
FAILED tests/unit/run/test_junit_readiness.py::test_testng_specific_diagnostic
FAILED tests/unit/run/test_junit_readiness.py::test_gradle_wrapper_path
FAILED tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope
FAILED tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope
FAILED tests/integration/run/test_junit_warnings.py::test_cli_smoke_missing_jacoco_emits_envelope_warning
FAILED tests/integration/run/test_junit_warnings.py::test_cli_smoke_ambiguous_build_tool_emits_envelope_warning
FAILED tests/integration/run/test_junit_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter
```

이 테스트들은 JUnit readiness `state == "ready"` (혹은 다른 "engine
detected" 케이스)를 기대. Windows에서는 adapter가 `state == "engine-
misconfigured"` 반환 → assertion 실패. **adapter는 의도된 동작; 테스트가
OS gate 를 reckon 못 함**.

## PM 권장 Fix shape — module-level pytest skip

### Category D — `encoding="utf-8"`

`tests/unit/run/adapters/test_junit_adapter.py::TestGradleCoverageArgv::test_init_script_present_with_coverage_and_jacoco`
의 `subprocess.run(..., text=True)`에 `encoding="utf-8"` 추가:

```python
result = subprocess.run(
    [...], text=True, encoding="utf-8",  # ← 추가
    capture_output=True, check=False,
)
```

추가로 `tests/unit/run/adapters/test_*_adapter.py`에 동일 패턴이
잠재하는지 grep 후 일괄 sweep 권장 (다른 어댑터들에서도 같은 class bug
숨어 있을 가능성):

```bash
grep -rn "subprocess.run.*text=True" tests/unit/run/adapters/
```

`encoding="utf-8"` 없는 hit들 = sweep 후보.

### Category E — `pytestmark = pytest.mark.skipif`

PM 권장 = **(α) module-level skipif**. 이유:
- 가장 단순
- adapter Windows-gate는 결정 §R5에 binding이므로 테스트가 Windows에서 skip되는 것이 정합적
- 향후 Windows binary pipeline (Open Q #16) 구현 시 skipif 제거만 하면 됨

```python
# tests/unit/run/test_junit_readiness.py 상단
import pytest
import sys

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason=(
        "JUnit adapter gates Windows per decision "
        "2026-06-03-junit-console-launcher-vendor.md §R5; "
        "Open Question #16 (Windows binary pipeline) pending."
    ),
)
```

같은 패턴을 다음 5개 파일에 적용:
- `tests/unit/run/test_junit_readiness.py` (7 tests)
- `tests/unit/run/adapters/test_junit_adapter.py` (Category D 외에도 OS-gate-sensitive cases가 있다면)
- `tests/integration/run/test_junit_gradle.py` (1 test)
- `tests/integration/run/test_junit_maven.py` (1 test)
- `tests/integration/run/test_junit_warnings.py` (3 tests)

### 대안 (β) os-gate-aware branch

`pytest.mark.skipif` 대신 테스트 안에서 OS branch:

```python
def test_ready_when_java_and_mvn_present():
    result = readiness_probe(...)
    if sys.platform.startswith("win"):
        # adapter MUST emit engine-misconfigured per decision §R5
        assert result.state == "engine-misconfigured"
        assert "non-Windows host" in result.diagnostic
    else:
        # original assertions
        assert result.state == "ready"
```

장점: Windows 회귀 detection (gate 자체가 깨지면 catch)
단점: 12 tests 각각 branch 추가 — 코드 양 증가

PM 권장 = **(α) skipif** for 단순성. 한 곳에서 os-gate firing 자체를
검증하는 dedicated 테스트는 별도 추가 가능 (optional, scope 작음).

### 선택 옵션 — os-gate-firing 검증 dedicated test (optional)

skipif로 12 tests를 패스하면 gate 자체가 깨졌을 때 회귀 감지 못 함.
선택적으로 1개 dedicated test 추가:

```python
# tests/unit/run/test_junit_readiness.py
@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="OS-gate firing 검증 — Windows에서만 의미",
)
def test_os_gate_fires_on_windows_per_decision_R5():
    result = readiness_probe(...)
    assert result.state == "engine-misconfigured"
    assert "Windows" in result.diagnostic or "Open Question #16" in result.diagnostic
```

이 테스트는 module-level skipif와 별개 — module skipif은 Linux/macOS만
fires이게 하는데, 이 테스트는 그 정반대. 결과: Windows에서 1 test가
실행되어 gate firing 검증.

PM 의견: optional. 단순성 우선시 안 해도 됨. handoff에 근거 명시.

## Scope

### In scope

- Category D: 1 test에 `encoding="utf-8"` 추가 + 다른 어댑터 tests sweep
- Category E: 5 test 파일에 `pytestmark = pytest.mark.skipif` 추가
- (optional) 1 dedicated os-gate-firing 검증 test (Windows-only)
- 12 failing tests Windows에서 skip 또는 그린

### Out of scope

- **JUnit adapter src 변경 zero** — adapter는 정상 동작. test-only fix.
- 다른 어댑터 (cargo, dotnet, gotest, jest, pytest)의 Windows 동작 변경
- Windows binary pipeline 구현 (Open Q #16 post-MVP)
- 다른 팀 territory

## 파일 footprint 가이드

- `tests/unit/run/test_junit_readiness.py`
- `tests/unit/run/adapters/test_junit_adapter.py` (Category D + 다른
  skipif 후보)
- `tests/integration/run/test_junit_gradle.py`
- `tests/integration/run/test_junit_maven.py`
- `tests/integration/run/test_junit_warnings.py`

**zero `src/`** — test-only.

## Definition of done

1. ✅ Category D test가 Windows에서 그린 (`encoding="utf-8"` 추가)
2. ✅ 다른 어댑터 tests audit + 같은 class bug 있으면 sweep
3. ✅ Category E의 5 test 파일에 module-level skipif 추가 → 11 tests
   Windows에서 skip
4. ✅ (optional) os-gate-firing dedicated test 1개 — handoff에 채택 여부
   + 근거 명시
5. ✅ Linux/macOS에서 12 tests 그대로 그린 (regression 없음 — skipif은
   non-Windows에서만 firing)
6. ✅ `uv run mypy --strict src/novetest` 클린 (변경 없음)
7. ✅ `uv run pytest -q tests/unit tests/integration` 그린 (equipped host)
8. ✅ **CI matrix verdict criterion**: 본 슬라이스 머지 후 `ci.yml` run에서
   JUnit 관련 12 tests Windows × 3 Python = 3 cells에서 skip (또는
   dedicated test가 추가됐다면 그건 그린). PM이 verification doc에
   cite할 `ci.yml` run number 명시.
9. ✅ WORKLOG.md 엔트리 (charter 양식)
10. ✅ Handoff `agent-comms/handoffs/run-team-2026-06-09-junit-windows-os-gate-test-fix.md`
    + DoD bullets believed closed
11. ✅ `python3 tools/regen_comms_index.py`

## Cross-team coordination — parallel cycle (3 teams)

본 슬라이스는 **Windows CI fix parallel triple의 3/3**. 같은 cycle에:

- Coverage팀: cross-drive ValueError + LCOV separator literal 수정
  (`tasks/coverage-team-2026-06-09-windows-parser-fixes.md`)
- Localization팀: `_normalize_to_workspace_relative` Windows drive-prefix
  수정 (`tasks/localization-team-2026-06-09-windows-path-normalization-fix.md`)

### 파일 ownership — Zero 충돌 보장

| 팀 | 디렉토리 |
|---|---|
| Run (본 슬라이스) | `tests/{unit,integration}/run/` (test-only; src 변경 없음) |
| Coverage (페어 1) | `src/novetest/coverage/` + 관련 tests |
| Localization (페어 2) | `src/novetest/localization/` + 관련 tests |

### 만지지 말 것

- `src/novetest/run/adapters/junit_adapter.py` — adapter는 정상; test-
  only fix
- `decisions/2026-06-03-junit-console-launcher-vendor.md` — §R5 binding
  그대로
- `cli/output.py::EnvelopeWarning` shape
- `coverage/**`, `localization/**`, `regression/**`, `replay/**`
- Windows binary pipeline 구현 (Open Q #16 post-MVP)

### Main Branch merge 순서

알파벳 FF-merge: **coverage → localization → run**.

### 새 verdict 기준 — CI matrix green (메타-decision §1 보강)

각 슬라이스의 verification doc은:
1. **Equipped-host verification** (메타-decision §1): Manual Test가
   equipped host에서 단위 + 통합 테스트 그린 (skip 정상)
2. **CI matrix verdict** (이 cycle 신규): 본 슬라이스 머지 후 `gh run`
   query로 `ci.yml` 가장 최근 run에서 JUnit 관련 12 tests가 Windows × 3
   Python = 3 cells에서 skip (또는 dedicated test 그린) + run number cite

### §2.5 equip-and-exercise 게이트

본 슬라이스는 **test-only** — JUnit adapter src 변경 없음. §2.5 file-
glob의 두 trigger (`src/novetest/run/adapters/junit_adapter.py` +
`tests/integration/run/test_junit_*.py`) 중 두 번째는 만짐 (skipif 추가).

해석: §2.5는 두 가지 변경이 **동시에** 발생할 때를 의도 (adapter src
변경이 통합 테스트에 영향 미치는 경우). 본 슬라이스는 adapter src 변경
zero → §2.5 발동 안 함이 자연스러운 해석. 일반 host에서 진행 OK.

만약 Run team이 §2.5 발동을 보수적으로 해석한다면 question 파일링 →
PM이 즉시 판단 (judgment call: test-only는 §2.5 trigger 아님).

## Implementation guidance

### `encoding="utf-8"` sweep

```bash
grep -rn "subprocess.run.*text=True" tests/unit/run/adapters/ tests/integration/run/
# 각 hit이 encoding= 가지는지 확인. 없는 hit들 = fix 후보
```

같은 패턴이 다른 곳에 잠재한다면 동일 패턴으로 sweep:

```python
result = subprocess.run(
    [...], text=True, encoding="utf-8",  # ← cp1252 회피
    capture_output=True, ...
)
```

### skipif 일관 어휘

5 파일 모두 동일 import + pytestmark:
```python
import pytest
import sys

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason=(
        "JUnit adapter gates Windows per decision "
        "2026-06-03-junit-console-launcher-vendor.md §R5; "
        "Open Question #16 (Windows binary pipeline) pending."
    ),
)
```

### CI matrix verdict 명령

```bash
gh run list --workflow ci.yml --branch main --limit 3
gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | contains("Windows")) | {name, conclusion}'
```

skipped tests가 다음과 같이 표시되어야 함:
```
tests/unit/run/test_junit_readiness.py ........... SKIPPED [reason: JUnit adapter gates Windows...]
```

## Reference

- `agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md`
  — 본 cycle의 cycle-close history
- `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`
  §R5 — Windows OS gate binding
- `.claude/agents/novetest-run-team.md` — 팀 charter

## 추정

- Phase 1 audit (encoding sweep): ~15분
- Phase 2 skipif 추가 (5 파일): ~15분
- Phase 3 tests (regression 확인): ~15-30분
- Wall time: **~1-1.5시간**
- 단일 cycle, 단일 attempt 예상
