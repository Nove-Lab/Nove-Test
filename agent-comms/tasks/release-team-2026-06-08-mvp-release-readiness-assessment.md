---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-08
slug: mvp-release-readiness-assessment
related:
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
  - agent-comms/history/2026-06-08-b2-ux-normalize-parallel-triple-coverage-localization-run.md
---

# Task — MVP Release Readiness Assessment + Critical-Path Fix

## Mission

5월 16일 Phase 0 closure 후 6개 native engine 어댑터 + 5 Coverage 파서
+ Phase 3 Regression + Phase 4 Localization + Phase 5 Replay + Phase 6
Recommendation 모두 메인에 들어왔어. 명목상 Phase 0 DoD 5/5 체크됐지만
**그건 5월 16일 시점 release readiness**. 오늘 (`5da65a2` commit) 시점에
정말로 MVP를 release 가능한가? 답을 empirical하게 만들어 와줘. gap 발견
시 **release-blocking 항목만** 본 슬라이스에서 수정, 나머지는 follow-up
cycle로 분리.

## Background — self-contained

수신 팀이 이 대화를 볼 수 없으므로 컨텍스트를 자체 포함된 형태로 기술함.

### 5월 16일 closure 시점

`history/2026-05-16-phase0-release-and-phase2-entry.md`에 따르면 Phase 0
release pipeline (`release-test.yml`) 마지막 그린 상태:
- 3-cell matrix: `linux-x86_64`, `linux-aarch64`, `macos-universal2`
- macOS는 universal2 (lipo-fused fat binary) — `macos-13` dependency 폐기
- 모든 binary + `.sha256` sidecar 생성 (3m4s 빌드)
- `install-script-e2e` job 그린 — clean install + idempotent re-install 둘 다 `novetest/v1` envelope 반환
- SHA-256 tampered-binary abort 테스트 통과

해당 게이트는 **5월 16일 head commit** 기준. 그 이후 큰 변화:

### 5월 16일 이후 어댑터 / 엔진 변화

| 추가 항목 | 시점 | 변경 surface | Production dep 영향 가능성 |
|---|---|---|---|
| pytest 어댑터 (Phase 0 기존) | 5월 14일 | `coverage`, `pytest-json-report` 등 | 이미 cover |
| jest 어댑터 (Phase 2) | 5월 21일 | Node deps (toolchain-gated, install 안 함) | 없음 (사용자 host 의존) |
| gotest 어댑터 (Phase 2) | 5월 22일 | Go deps (toolchain-gated) | 없음 |
| junit 어댑터 (Phase 2.5) | 6월 4일 | Maven/Gradle (toolchain-gated) + **vendored Console Launcher JAR** | **YES** — `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar` 동봉 (decision `2026-06-03-junit-console-launcher-vendor.md`) |
| cargo 어댑터 (Phase 2.5) | 5월 30일 | cargo deps (toolchain-gated) | 없음 |
| dotnet 어댑터 (Phase 2.5) | 6월 5일 | dotnet deps (toolchain-gated; Coverlet runsettings는 user host) | 없음 |
| Coverage 5-parser (cobertura 추가) | 6월 7일 | XML 파서 추가 | Python stdlib만 (`xml.etree.ElementTree`) |
| Regression engine | 5월 25일~ | Python only | 없음 |
| Localization engine + SBFL | 5월 27일~ | Python only | 없음 |
| Replay engine | 6월 3일 | Python only | 없음 |
| Recommendation synthesis | 6월 2일 | Python only | 없음 |

### 두 종류의 risk

1. **Production binary risk**: PyApp이 wrapping하는 wheel에 새 deps
   추가됐을 가능성. vendored JAR (~2MB)이 PyApp binary 크기에 영향 줄 수
   있음. install.sh download 시간 / SHA-256 verify에 영향.
2. **CI matrix risk**: Linux/macOS/Windows × Python 3.11/3.12/3.13
   matrix가 head commit에 대해 그린한지. native engine 통합 테스트들이
   toolchain-gated skip으로 처리되고 있는지 (CI 호스트에 native toolchain
   미설치 가정).

## Scope — 3 phase

### Phase 1 — Assessment (gap report)

다음 항목을 점검하고 결과를 handoff §"Assessment matrix"에 매트릭스
형태로 명시:

#### 1.1 CI matrix 상태 (Linux/macOS/Windows × Python 3.11/3.12/3.13)

- 현재 `.github/workflows/`에 어떤 워크플로우들이 있는지 inventory
- `release-test.yml` (또는 후속 이름)이 `5da65a2` head commit에 대해 그린한지 (가능하면 head trigger / 또는 main 푸시로 자연 그린 여부)
- Skipped tests 정상 — toolchain-gated tests는 skip이 올바른 동작
- Failed tests = release blocker

#### 1.2 PyApp binary build matrix

- 3-cell (linux-x86_64, linux-aarch64, macos-universal2) 모두 head commit에서 빌드 성공
- binary 크기 변화 (5월 16일 대비 — vendored JAR + 추가 코드 영향)
- `.sha256` sidecar 생성

#### 1.3 install.sh end-to-end

- 새 binary로 install.sh 동작 확인 (Linux container clean + macOS clean)
- Idempotent re-install 동작
- SHA-256 verify가 정상 동작 (tampered binary abort)
- `novetest --version` 정상 envelope 반환

#### 1.4 production / dev deps 점검

- `pyproject.toml` 현재 deps 목록 — 5월 16일 대비 추가/변경 사항
- 추가된 deps가 production (binary에 포함) vs dev-only인지 판단
- 새 production deps가 PyApp wheel에 포함되어 install.sh 흐름에 들어가는지

#### 1.5 THIRD_PARTY_NOTICES.txt 최신성

- 현재 `THIRD_PARTY_NOTICES.txt` 존재 여부 (없으면 신규 생성 필요)
- vendored JUnit Console Launcher JAR (EPL 2.0) 명세 포함되어 있는지 (decision `2026-06-03-junit-console-launcher-vendor.md` §4 명시)
- 다른 모든 production deps 라이센스 명세 포함 여부

#### 1.6 Phase 0 unchecked DoD bullet 재확인

`design/implementation-plan/delivery-phasing.md` Phase 0 DoD 5개 항목.
명목상 모두 `[x]` 체크됐지만 head commit에서 실제로 모두 성립하는지
empirical 확인. 미성립 시 closure 자체가 stale → 정정 필요.

### Phase 2 — Critical-path fix (gap이 있다면)

Phase 1에서 발견된 gap을 **release-blocking 분류**:

- **Blocker**: binary build 실패, install.sh 실패, SHA-256 verify 실패,
  CI matrix red, THIRD_PARTY_NOTICES.txt 누락된 mandatory 라이센스
- **Non-blocker**: nice-to-have 개선, deprecated warning, optional dep
  업데이트, CI matrix 일부 cell 시간 초과 (skip이지만 timeout)

**본 슬라이스 scope**: blocker만 수정. Non-blocker는 follow-up cycle로
분리 (handoff §"Follow-up cycle candidates"에 명시).

### Phase 3 — Sign-off

- Head commit (또는 Release team fix가 추가된 commit)에 대해
  `release-test.yml` 실제 그린 + binary 산출물 + install.sh smoke green
- Handoff에 sign-off statement 명시: "MVP release-ready as of `<commit>`"
  또는 "MVP not release-ready; blocking gap: <list>"

## Out of scope (PM이 별도로 처리; Release team scope 아님)

- **6-cycle equip-and-exercise 메타-decision 정식화** — PM territory
  (decision 작성). 본 cycle에서 PM이 별도 commit으로 진행.
- **Long-standing TODO sweep audit-trail** — PM territory. history 파일
  들에 closure annotation 추가, audit-trail commit.
- **Fixture inventory matrix** — PM territory. release readiness 결과에
  따라 별도 cycle 또는 PM 단독 commit.
- **v1 metadata-channel sunset** — post-MVP cleanup cycle.
- **Phase 7 MCP transport** — post-MVP.
- **새로운 product feature** — release 이후.

## 파일 footprint 가이드 (Release team territory)

- `pyproject.toml` (deps 변경 시)
- `uv.lock` (lockfile 재생성)
- `scripts/install.sh` (수정 시)
- `.github/workflows/release-test.yml` (또는 동등 — CI matrix 수정 시)
- `.github/workflows/<other>.yml` (다른 워크플로우 수정 시)
- `THIRD_PARTY_NOTICES.txt` (신규 또는 갱신)
- `tests/release/` (release-specific tests; **NOT** `tests/unit/` 또는
  `tests/integration/`)
- `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`

## Implementation guidance

### 1. Assessment 첫 단계 — gh + gitactions 확인

```bash
# 최근 main 푸시에 대한 워크플로우 run 상태
gh run list --branch main --limit 10
# release-test.yml 가장 최근 run
gh run list --workflow release-test.yml --limit 5
```

5월 16일 (`25963163742`) 이후 어떤 run이 있었는지 확인. 없으면 manual
trigger 또는 본 슬라이스 commit 푸시로 자연 trigger.

### 2. 새 deps 확인

```bash
git diff acfc535:pyproject.toml HEAD:pyproject.toml
git log --oneline -- pyproject.toml | head -10
```

5월 16일 close commit과 head commit 사이 `pyproject.toml` 변경 추적.

### 3. THIRD_PARTY_NOTICES.txt

decision `2026-06-03-junit-console-launcher-vendor.md` §4 발췌:

> "ship `THIRD_PARTY_NOTICES.txt` for EPL 2.0; introduces the
> vendored-asset pattern."

이 파일이 실제로 존재하는지 + JUnit Console Launcher 명세 포함 여부 확인.
없으면 신규 생성 (Phase 2 critical-path fix). 다른 deps도 동시 점검.

### 4. install.sh smoke

```bash
# 가장 최근 release-test.yml run의 install-script-e2e job 결과
gh run view <run-id> --log
# 또는 로컬에서 (가능하면 Docker container로 깨끗한 환경)
docker run --rm -it ubuntu:24.04 bash -c '
  apt-get update && apt-get install -y curl ca-certificates
  curl -fsSL <release-test-url>/install.sh | sh
  novetest --version
'
```

## Definition of done

1. ✅ Assessment matrix (1.1-1.6 각 항목) handoff에 명시 (pass/blocker/non-blocker)
2. ✅ Release-blocking gap이 있었다면 Phase 2 fix 수행 + 재검증
3. ✅ 최종 sign-off statement 명시: "MVP release-ready as of `<commit>`"
   또는 "Not ready; blocker(s): <list>"
4. ✅ Head commit (또는 fix 추가된 commit)에서 `release-test.yml` 실제 그린
5. ✅ Binary build 3-cell (linux-x86_64, linux-aarch64, macos-universal2)
   + `.sha256` sidecar 산출물 확인
6. ✅ install.sh end-to-end (clean install + idempotent re-install) 그린
7. ✅ SHA-256 tampered-binary abort 테스트 그린
8. ✅ THIRD_PARTY_NOTICES.txt 최신 (vendored JUnit JAR 포함)
9. ✅ WORKLOG.md 엔트리 (charter 양식; `src/` 안 만지더라도 release
    pipeline 변경 시 narrative 가치)
10. ✅ Handoff `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`
    + Assessment matrix + DoD bullets believed closed + Follow-up cycle
    candidates
11. ✅ `python3 tools/regen_comms_index.py`

## Cross-team coordination

### 단일 슬라이스 (병렬 cycle 아님)

본 cycle은 Release team **단독 슬라이스**. 다른 팀과 병렬 진행 없음.
이전 cycle들 (06-07, 06-08 B1, 06-08 B2)은 2-3팀 병렬이었지만 release
readiness는 cross-cutting infra라 단독이 자연스러움.

### 만지지 말 것 (Release team charter 명시)

Release team charter (`.claude/agents/novetest-release-team.md`)의
forbidden 디렉토리 그대로:
- `src/novetest/**` (모든 engine code)
- `tests/unit/**`, `tests/integration/**`
- `tests/fixtures/projects/**`
- `agent-comms/tasks/**`, `decisions/**`, `history/**`, `verifications/**`, `findings/**`

추가:
- 본 cycle은 Release team scope만; 다른 폴리시 (v1 sunset 등) 손대지 말 것

### §2.5 equip-and-exercise 게이트

본 슬라이스는 native 어댑터 src + 통합 테스트를 만지지 않음 (charter
forbidden) → §2.5 게이트 발동 **안 함**. 일반 host에서 진행 가능.

### Question 파일링 트리거

- 새 production dep 추가 필요 시 → `questions/release-team-2026-06-08-new-production-dep.md` 파일링 + PM 라우팅 (charter §"During work" 명시)
- engine 코드에 영향 가는 변경 필요 시 (e.g., `coverage` 패키지 버전이 adapter 동작에 영향) → question 파일링

## Reference

- `design/implementation-plan/foundations.md` §7 (Distribution)
- `design/implementation-plan/delivery-phasing.md` Phase 0
- `agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md`
  — 5월 16일 closure 결과 (matrix transition, binary build, install
  smoke 모두 명시)
- `agent-comms/decisions/2026-05-14-install-script-hosting-url.md`
  — install URL: `ailovestesting.com/novetest/install.sh`
- `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md` §4
  — THIRD_PARTY_NOTICES.txt EPL 2.0 명세 요구
- `.claude/agents/novetest-release-team.md` — 팀 charter

## 추정

- Phase 1 assessment: 1-2 시간 (gh CLI + workflow log + dep diff)
- Phase 2 critical-path fix: 발견된 gap에 따라 0-3 시간 (gap이 없으면 0;
  많으면 별도 cycle 분리)
- Phase 3 sign-off: 30분-1시간 (실제 빌드 + smoke)
- Wall time: 2-6 시간 (gap 면적에 따라)
- 단일 cycle, 다만 gap 면적이 크면 본 cycle은 assessment 위주 + Phase 2를
  follow-up cycle로 분리. handoff에 명시.
