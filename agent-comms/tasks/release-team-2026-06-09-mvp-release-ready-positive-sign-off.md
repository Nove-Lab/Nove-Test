---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-09
slug: mvp-release-ready-positive-sign-off
related:
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# Task — MVP Release-Ready Positive Sign-Off (Phase-3-only re-validation pass)

## Mission

어제 (2026-06-09 첫 release readiness cycle)의 **negative sign-off**
("MVP NOT release-ready as of `bd4d300`")의 단일 blocker가 오늘 Windows
CI fix triple로 닫혔어 (`a036815`, `ci.yml` run `27187459586` 10/10
GREEN). 본 슬라이스는 그 변화를 empirical 재검증해서 **positive
sign-off** ("MVP release-ready as of `<commit>`") 으로 deliverable
flip. 새 정책 결정 zero — pure validation pass.

## Background — self-contained

수신 팀이 이 대화를 볼 수 없으므로 컨텍스트 자체 포함.

### 어제 release readiness assessment (negative sign-off)

`history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-
blocker-surfaced.md` 요약:

- **GREEN at `bd4d300`**: PyApp binary build 3-cell + install.sh E2E +
  SHA-256 verify (`release-test.yml` run `27176266868`)
- **BLOCKER at `bd4d300`**: `ci.yml` Windows × 3 Python cells RED 9
  days chronic since 2026-06-01 (20 failures: 5 Coverage + 4
  Localization B2-2 regression + 11 Run/JUnit)
- THIRD_PARTY_NOTICES.txt vendored JUnit JAR EPL 2.0 attribution
  empirically met (decision `2026-06-03-junit-console-launcher-vendor.md`
  §3 binding)

### 오늘 Windows CI fix triple cycle

`history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
요약:

- **3-team parallel triple** (Coverage + Localization + Run) PASSED
- **`ci.yml` run `27187459586` on `871a278` = 10/10 GREEN** — 9-day
  chronic Windows red 종료, `main` 2026-05-31 이후 첫 all-green matrix
- `delivery-phasing.md` Phase 0 DoD #1 re-closed (5/16 closure + 6/9
  re-open + 6/9 re-close audit trail in one bullet)

### 본 슬라이스 = empirical re-validation only

새 src/tests/config 변경 zero. 어제 assessment의 negative 결과를 cause-
gone empirical 재확인 + handoff sign-off statement flip만.

## Scope — 4-task validation pass

### 1. `release-test.yml` workflow_dispatch on current HEAD

```bash
gh workflow run release-test.yml --ref main
# 또는 worktree branch 이름으로
```

Trigger + 완료 후:
- 3-cell PyApp build (linux-x86_64, linux-aarch64, macos-universal2)
  모두 green
- 3개 `.sha256` sidecar 산출
- `install-script-e2e` job green (clean install + idempotent re-install)
- 빌드 시간 + binary 크기 어제 (`27176266868`) 대비 비교 (회귀
  surveillance — 9일 전과 차이 미미 예상)

### 2. `ci.yml` all-green re-validation at current HEAD

```bash
gh run list --workflow ci.yml --branch main --limit 5
gh run view <latest-run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected:
- 10/10 GREEN matrix (또는 9 cells 그린 + release-related cells 그린)
- Windows × Python 3.11/3.12/3.13 모두 그린 (오늘 `27187459586`이 처음)

만약 본 슬라이스 (Release team worktree commit + Main Branch FF-merge)
후 새 push로 trigger된 ci.yml run이 있다면 그 run을 사용. 없다면
`27187459586` (Windows fix triple closure 시점)을 evidence로 인용 OK
— 본 슬라이스가 src/tests 만지지 않으므로 ci 결과가 동일해야 함.

### 3. THIRD_PARTY_NOTICES.txt vendored JAR 재검증

```bash
sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
# Expected: b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc
```

NOTICES 파일의 pinned SHA-256과 byte-identical 매칭 확인. decision
`2026-06-03-junit-console-launcher-vendor.md` §3 mandate (EPL 2.0
attribution + artifact coords + license URL + source URL + SHA-256)
모두 충족 여부 확인.

### 4. Handoff sign-off statement flip

어제 negative sign-off:
> "MVP NOT release-ready as of `bd4d300`. Blocker: ci.yml Windows red ..."

오늘 positive sign-off (handoff에 작성):
> "**MVP release-ready as of `<current-HEAD>`**. All Phase 0 DoD bullets
> empirically green: (1) `uv run pytest -q` green on 3 OSes × 3 Python
> via `ci.yml` run `<latest-id>`; (2) signed binary builds via
> `release-test.yml` run `<re-dispatch-id>`; (3) curl-pipe-sh end-to-end
> green; (4) SHA-256 verify + tampered-binary abort test green; (5)
> `-v`/`-h` envelopes structurally correct. Vendored JUnit JAR EPL 2.0
> attribution per decision §3 byte-identically valid. Single remaining
> non-blocker polish: pip-dep attribution (cyclopts, numpy) + `novetest
> --licenses` CLI surface — both post-MVP per yesterday's PM
> disposition."

## Out of scope

- 새 production / dev deps 추가
- `src/**`, `tests/{unit,integration}/**` 변경 (charter forbidden)
- THIRD_PARTY_NOTICES.txt 확장 (pip-dep attribution은 post-MVP polish)
- `novetest --licenses` CLI 구현 (Orchestration team territory + post-MVP)
- Windows install.ps1 (Open Q #16, post-MVP)
- 새 정책 결정 — 본 슬라이스는 empirical validation만

## 파일 footprint 가이드

- `agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md` (생성)
- `WORKLOG.md` (엔트리; src/tests 안 만지지만 narrative 가치)
- `agent-comms/INDEX.md` (regen)

**zero `src/`, zero `tests/`, zero `pyproject.toml`, zero `.github/workflows/`** — 어제 release readiness cycle과 동일 shape.

## Definition of done

1. ✅ `release-test.yml` workflow_dispatch trigger + run green (3 cells +
   install-script-e2e + sha256 sidecars). Run number handoff에 명시.
2. ✅ `ci.yml` all-green matrix at HEAD (자체 push trigger의 새 run 또는
   `27187459586` 인용). Run number handoff에 명시.
3. ✅ THIRD_PARTY_NOTICES.txt vendored JUnit JAR SHA-256 byte-identical
   확인. `sha256sum` 결과 handoff에 명시.
4. ✅ Handoff sign-off statement flip: **"MVP release-ready as of
   `<commit>`"** 명시 + 5 Phase 0 DoD 모두 empirical green 인용
5. ✅ WORKLOG.md 엔트리 (charter 양식)
6. ✅ Handoff `agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md`
   + DoD bullets believed closed
7. ✅ `python3 tools/regen_comms_index.py`

## Cross-team coordination

### 단일 슬라이스 — 병렬 cycle 아님

본 cycle은 Release team **단독 슬라이스**. 어제 첫 release readiness
assessment cycle (`230420c`)과 동일 shape. comms-only — 매우 가벼움.

### 만지지 말 것 (Release team charter)

- `src/novetest/**` (모든 engine code)
- `tests/unit/**`, `tests/integration/**`
- `tests/fixtures/projects/**`
- `agent-comms/{tasks,decisions,history,verifications,findings}/**`

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native 어댑터 src + 통합 테스트 만지지 않음 → §2.5 게이트
발동 **안 함**. 일반 host 또는 equipped host 둘 다 OK.

### 메타-decision §1 SHOULD tier

`decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
§1 "Manual Test verification host = equipped, by default"는 본 슬라이스
의 후속 Manual Test verification에 적용. Release team 자체 작업에는
적용 안 됨 (comms-only validation pass).

## Implementation guidance

### Workflow trigger 명령

```bash
# Release-test workflow dispatch
gh workflow run release-test.yml --ref main
# 그 후 run 추적
gh run list --workflow release-test.yml --limit 5
gh run watch <run-id>

# CI matrix 최근 run 확인
gh run list --workflow ci.yml --branch main --limit 5
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'

# 바이너리 산출물 다운로드 검증 (optional sanity check)
gh run download <release-test-run-id> --pattern 'novetest-*'
```

### Sign-off statement 어휘 가이드

어제 Manual Test framing (`findings/manual-test-team-2026-06-09-mvp-
release-readiness-assessment.md`):
> "The cycle's deliverable IS a negative sign-off ... Manual Test's
> job here was to verify the *integrity and accuracy of that negative
> sign-off*."

오늘은 정반대 framing — positive sign-off가 deliverable. Manual Test가
다음 단계에서 그 positive sign-off의 integrity를 검증. Release team
handoff는 명확한 어휘로 sign-off를 박을 것:

> "**MVP release-ready as of `<commit>`.**"

뒤따르는 evidence list (위 §4의 다섯 줄)가 binding citation.

### Run number formatting

여러 workflow run 인용 시 일관 어휘:
- `release-test.yml` run `<id>` (re-dispatched yyyy-mm-dd hh:mm UTC)
- `ci.yml` run `<id>` (post-`<commit>` push trigger; <count>/<count>
  matrix green)

## Reference

- `agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
  — 오늘 Windows CI fix triple cycle closure (ci.yml run `27187459586`
  10/10 GREEN narrative)
- `agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md`
  — 어제 첫 release readiness cycle (negative sign-off origin)
- `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`
  §3 — THIRD_PARTY_NOTICES.txt EPL 2.0 binding
- `design/implementation-plan/delivery-phasing.md` Phase 0 §"Definition-
  of-done" — 5 bullet 모두 `[x]` (DoD #1은 6/9 re-closed marker 포함)
- `.claude/agents/novetest-release-team.md` — 팀 charter

## 추정

- `release-test.yml` workflow_dispatch + wait: ~5-10분
- `ci.yml` 결과 확인 (cached): ~1분
- THIRD_PARTY_NOTICES sha256 check: ~1분
- Handoff 작성: ~10-15분
- Wall time: **~30분**
- 단일 cycle, 단일 attempt 예상

## Cycle 마감 후 후속 (PM 직접 처리, Release team scope 아님)

본 슬라이스가 PASSED로 닫히면:
- PM이 history entry 작성: `history/2026-06-09-mvp-release-ready-
  positive-sign-off.md` (또는 동등 slug)
- PM이 cycle 마감 commit + 5 transient 삭제 + INDEX regen
- **MVP release-ready 상태 달성** — release tag + GitHub Releases 발행
  + announcement는 별도 작업

본 슬라이스는 release-ready status만 박음. 실제 release 발행은 그 후
CEO의 별도 명령 (release tag 생성 등). 가능한 next-cycle 후보:
- "release tag v0.1.0 발행 + GitHub Releases 산출물 업로드 cycle"
- 또는 v1 metadata-channel sunset (post-MVP cleanup) — release 직후
