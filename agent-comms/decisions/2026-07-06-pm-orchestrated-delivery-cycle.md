---
from: novetest-pm-team
to: all
type: decision
status: active
created: 2026-07-06
slug: pm-orchestrated-delivery-cycle
related:
  - CEO_ROUTINE.md
  - .claude/agents/novetest-pm-team.md
  - .claude/workflows/delivery-cycle.js
supersedes:
  - agent-comms/decisions/2026-05-14-team-structure-and-protocol.md
---

# Decision: PM-오케스트레이션 딜리버리 사이클 (CEO 접점 = 2개 게이트)

CEO-approved on 2026-07-06. 이 문서는 운영 체계의 **디스패치 모델 전환**을 기록하는
바인딩 결정이다. 구현(헌장 + `CEO_ROUTINE.md` + workflow)이 실체이고, 이 문서는 근거의 기록이다.

**Effective date:** 2026-07-06. 다음 사이클부터 모든 팀에 적용.

**Amends:** `2026-05-14-team-structure-and-protocol.md` — §1의 "team dispatch = CEO의 역할"과
§7의 "PM은 `novetest-*-team`을 절대 디스패치하지 않는다"를 **역전**한다. 팀 로스터·채널·
어댑터 소속(§2)·CLI+Orchestration 통합(§3)·2계층 코디네이션(§5)은 그대로 유효하다.

---

## 무엇이 바뀌나 (한 줄)

**CEO는 더 이상 매 사이클마다 팀을 수동으로 순차 디스패치하지 않는다.** CEO의 접점은
**2개의 승인 게이트**로 축소되고, 그 사이의 모든 디스패치·시퀀싱·집계는 **PM-오케스트레이터**가
책임진다.

## PM-오케스트레이터 = 메인 세션 (핵심 설계 결정)

PM-오케스트레이터는 **CEO가 대화하는 메인 Claude Code 세션 그 자체**다. 별도로 스폰되는
`@novetest-pm-team` 서브에이전트가 아니다.

**왜 서브에이전트가 아니라 메인 세션인가:** 이 체계에는 사이클 중간에 사람 CEO의 승인이
필요한 게이트가 2개 있다(계획 승인, 푸시 승인). 게이트는 "실행을 멈추고 → 사람에게 제어를
넘기고 → 사람의 답을 받아 문맥을 유지한 채 재개"를 요구한다. 이 인터리빙은 **메인 세션만**
자연스럽게 할 수 있다. 디스패치된 서브에이전트는 한 번 실행되면 완료까지 달리며 사람의 승인을
기다리려고 중간에 멈출 수 없다. 따라서 오케스트레이터 역할은 메인 세션이 맡고, 실행 팀들은
그 아래로 디스패치된다.

**호출 규칙의 귀결:** CEO는 `@novetest-pm-team`으로 부르지 않는다(그건 게이트 불가한
계획-전용 서브에이전트를 스폰함). CEO는 **메인 세션에 직접** 말한다 — `/cycle` 커맨드 또는
"ultracode, 오늘 사이클 시작하자". 자세한 호출법은 `CEO_ROUTINE.md`.

## 새 사이클 (8단계)

```
1. PM 계획        오케스트레이터가 상태 점검·트리아지 후 tasks/ 작성 + 계획 제시
       ↓
2. CEO 승인       [게이트 1] 계획·질문 승인 → 필요시 decisions/ 기록
       ↓
3. 병렬 실행      워크팀 병렬 디스패치 → 각자 worktree 작업 → handoffs/
       ↓
4. 메인 브랜치    머지 + 테스트 게이트(pytest+mypy) + 커밋 → verifications/
       ↓
5. 매뉴얼 테스트  E2E 검증 → findings/   (문서-전용 사이클은 생략)
       ↓
6. PM 재검토      handoff/verification/findings 검토 + DoD 검증 → CEO 보고
       ↓
7. CEO 확인       [게이트 2] 보고 확인 + 푸시 승인
       ↓
8. PM 마무리      DoD 틱 + history/ + transient 삭제 + INDEX 재생성 → 푸시(딜리버리+클린업) → 다음 사이클 간략 제시
```

3~5단계는 하나의 **`delivery-cycle` 워크플로우**(`.claude/workflows/delivery-cycle.js`)로
묶여 fan-out(워크팀) → merge(메인 브랜치) → verify(매뉴얼 테스트) 파이프라인으로 실행된다.
게이트 1은 워크플로우 시작 **전**, 게이트 2는 워크플로우 종료 **후**에 오므로, 워크플로우는
사람 승인을 위해 멈출 필요가 없다.

## 유지되는 불변식 (v1에서 그대로)

- **CEO의 유보 권한은 그대로다:** `questions/` 답변, `push` 승인, 실패한 `findings/`의 처리
  방향 결정. 다만 이제 이것들은 CEO가 수동 디스패치로 확인하는 게 아니라, 오케스트레이터가
  **게이트에서 CEO에게 올려** 결정을 받는다.
- 7개 채널·파일명 규약·frontmatter·`INDEX.md` 자동생성 — 무변경.
- WORKLOG 규율, **DoD 틱은 PM 전용**, worktree 격리, 테스트 게이트 — 무변경.
- `decisions/`는 여전히 **CEO 승인 후** PM이 기록.
- pre-flight의 `git fetch && git status` 규율(2026-05-25 duplicate-merge 교훈) — 무변경.
- Main Branch → Manual Test의 `verifications/` 직접 채널은 데이터 핸드오프로 유지. 다만
  **트리거는 오케스트레이터**(워크플로우가 merge 다음에 verify를 시퀀싱)다.

## 역할 변화 요약

| 역할 | v1 | v2 |
|---|---|---|
| CEO(사람) | 상태확인 + 6회 수동 디스패치 + 2게이트 | **PM과만 대화 + 2게이트** |
| PM | 계획·프롬프트만, 디스패치 금지 | **오케스트레이터**: 계획+디스패치+시퀀싱+보고+마무리 |
| 워크팀/Main Branch/Manual Test | CEO가 디스패치 | **오케스트레이터가 디스패치** |
| Secretary | 수동 루틴 단계 안내 | 읽기전용 상태 브리퍼(선택적)로 슬림화 |

## Affected files

- `CEO_ROUTINE.md` (재작성)
- `.claude/agents/novetest-pm-team.md` (오케스트레이터로 재정의)
- `.claude/agents/novetest-secretary.md` (읽기전용 상태 브리퍼로 슬림)
- `.claude/agents/novetest-main-branch-team.md` (푸시 승인이 CEO→PM 경유; 오케스트레이터가 디스패치)
- `.claude/agents/novetest-manual-test-team.md` (findings 1차 독자 = PM; 오케스트레이터가 디스패치)
- `agent-comms/README.md` (허브 서술 + 라이프사이클 트리거 갱신)
- `CLAUDE.md` (운영 모델 포인터 추가)
- `.claude/workflows/delivery-cycle.js` (신규 — 실행단계 워크플로우)
- `.claude/commands/cycle.md` (신규 — `/cycle` 킥오프 커맨드)

## Open follow-up

- **첫 오케스트레이션 사이클에서 검증할 것:** 워크플로우의 `agent()`로 디스패치된
  `novetest-*-team`이 자신의 Agent 툴로 스페셜리스트를 재귀 리크루트할 수 있는지. 가능하면
  기존과 동일. 불가하면 팀은 스페셜리스트 없이 직접 작업(각 헌장이 이미 허용 — 리크루팅은
  "혼자 다 하지 말라"는 권고이지 의무가 아님). 2026-05-14 §7 open-follow-up의 연장선.
- `andrej-karpathy-skills:karpathy-guidelines` 스킬이 이 환경에 **미설치**다(CLAUDE.md가
  코드 수정 전 필수로 요구). 별도 트랙으로 설치 또는 CLAUDE.md 규칙 조정 필요.
