---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-14
slug: team-structure-and-protocol
---

# Decision: Multi-agent team structure and coordination protocol

CEO-approved on 2026-05-14. This file is the durable record of the org-design
decisions made while bootstrapping the multi-agent setup; the charters and
`CLAUDE.md` are the implementation, this is the rationale of record.

**Effective date:** 2026-05-14. Binding on all teams from their next dispatch.

**Supersedes:** the pre-charter ad-hoc agent usage (agents run before
`.claude/agents/novetest-*-team.md` existed are retired; restart fresh under
the charters).

---

## 1. Team roster — 11 teams

`PM`, `Run`, `Memory`, `Coverage`, `Orchestration`, `Main Branch`, `Manual Test`,
`Release`, `Regression`, `Localization`, `Replay`. Each is a Claude Code subagent
defined at `.claude/agents/novetest-<team>-team.md`.

- **Active now:** PM, Main Branch, Manual Test, Coverage (Phase 2 entry). Run /
  Memory / Orchestration on standby (Phase 1 done; re-activate as their work
  arrives). Release activates to close Phase 0 leftovers.
- **Dormant until their phase:** Regression (Phase 3), Localization (Phase 4),
  Replay (Phase 5) — placeholder charters with explicit activation gates.

## 2. Engine adapters belong to Run Team

The six native-engine adapters (pytest, jest, go test, JUnit, dotnet, cargo)
are owned by Run Team, not a separate Adapters team. **Why:** same directory
tree (`src/novetest/run/adapters/`), same `NativeAdapter` Protocol — one team
keeps cohesion. Run Team recruits per-language specialist subagents
(`golang-pro`, `rust-engineer`, etc.) for the non-Python adapters.

## 3. CLI transport and Orchestration are one team

`src/novetest/cli/` and `src/novetest/orchestration/` are owned by a single
Orchestration Team. **Why:** CLI is a thin transport; the business logic lives
in orchestration. Splitting them would scatter one logical concern across two
teams. Revisit only if the Phase 6 recommendation synthesizer grows unwieldy.

## 4. Release Team is separate (not absorbed into Main Branch)

Packaging, CI matrix, PyApp pipeline, install scripts, and the dev-deps surface
are owned by a dedicated (temporary) Release Team. **Why:** Main Branch's job is
merge integrity; mixing release engineering into it would blur both.

## 5. Coordination protocol — two layers

- `WORKLOG.md` — immutable per-commit retrospective (committed history).
- `agent-comms/` — in-flight coordination across seven channels
  (`tasks`/`handoffs`/`verifications`/`findings`/`questions`/`decisions`/`history`),
  PM hub-and-spoke, auto-indexed by `tools/regen_comms_index.py`.

Full protocol: `agent-comms/README.md`. Both layers are kept — they serve
different audiences and lifecycles (decided as "option A": no consolidation).

## 6. CLAUDE.md holds only project-wide rules

`CLAUDE.md` carries what every agent needs regardless of role (Coding
Guidelines, Structure, the Coordination Harness overview). Team-specific rules —
coding conventions, testing rules, file ownership, pre-flight/post-flight
checklists, DoD bookkeeping — live in the per-team charters. DoD bullet ticking
in `delivery-phasing.md` is PM-only.

## 7. Every team recruits specialist subagents

Each `novetest-*-team` carries the Agent tool and a `## Recruiting specialists`
clause: within its scope, a team recruits the repo's general specialist agents
(`python-pro`, `debugger`, `code-reviewer`, etc.) for focused sub-tasks, while
keeping all team-level coordination in its own hands. PM's variant is narrower:
PM recruits *planning* specialists for itself but never dispatches the
`novetest-*-team` agents — team dispatch stays the CEO's role.

---

## Affected files

- `.claude/agents/novetest-*-team.md` (11 charters)
- `CLAUDE.md`
- `agent-comms/**`, `tools/regen_comms_index.py`
- `CEO_ROUTINE.md`

## Open follow-up

- Whether Claude Code supports nested subagents (a team agent spawning a
  specialist via the Agent tool) is unverified — to be confirmed on the first
  real cycle. If unsupported, decision #7's mechanism shifts to "CEO co-dispatches
  specialists alongside the team," but the org intent stands.
