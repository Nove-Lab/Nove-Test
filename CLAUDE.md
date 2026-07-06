# Nove Test

Polyglot test orchestration tool. AI-friendly CLI emitting structured JSON envelopes for AI-agent consumption.

This file holds only the project-wide rules every agent needs. Team-specific rules (coding conventions, testing rules, file ownership, reporting format) live in each team's charter: **`.claude/agents/novetest-<your-team>-team.md`** — read your own charter first.

When something fails unexpectedly (e.g. `Write` / `Edit` blocked, recurring tool quirks), check **`GOTCHAS.md`** at the repo root before assuming charter or hook misconfiguration. Policy: `agent-comms/decisions/2026-05-16-gotchas-md-policy.md`.

---

## Coding Guidelines

Whenever you write or modify code (any source file, script, config, hook — anywhere in this repo), you MUST invoke the `andrej-karpathy-skills:karpathy-guidelines` skill via the Skill tool before making the change. It ensures:

1. Think Before Coding
2. Simplicity First
3. Surgical Changes
4. Goal-Driven Execution

This applies to every team that edits code, including PM (utility scripts), Main Branch (merge conflict resolution), and Release (build/CI/install scripts). Manual Test, which only reads source, is exempt by virtue of never editing.

**One-time setup (per environment).** This skill ships as a Claude Code plugin, not in the repo — a fresh clone on a new machine must install it once before any code-editing work:

```
/plugin marketplace add forrestchang/andrej-karpathy-skills
/plugin install andrej-karpathy-skills@karpathy-skills
/reload-plugins
```

Confirm it is live by invoking it once (or checking the skills list for `andrej-karpathy-skills:karpathy-guidelines`). Until installed, the mandate above is unsatisfiable and code-editing agents should flag it rather than silently skip.

---

## Structure

```
src/novetest/                   # Single import root (one PyPI distribution: novetest)
├── cli/                        # CLI transport (Cyclopts, JSON envelope, exit codes)
├── orchestration/              # Top-level workflows + recommendation synthesis
│   ├── workflows/
│   └── recommendation/
├── run/                        # Run engine
│   └── adapters/               # Native test engine adapters
├── memory/                     # Memory engine
├── coverage/                   # Coverage engine
├── regression/                 # Regression engine
├── localization/               # Localization engine
│   └── sbfl/                   # SBFL algorithms
├── replay/                     # Replay engine
├── models/                     # Shared domain entity definitions
├── utils/                      # Shared low-level utilities
└── mcp/                        # MCP transport (post-MVP)

tests/
├── unit/                       # Mirrors src/ tree; one test module per source module
├── integration/                # Cross-component / subprocess-boundary tests
├── fixtures/projects/          # Controlled SuT projects (deterministic, isolated, no novetest imports)
└── manual-test-workspace/      # Human-facing demo scratch space; contents ephemeral (see its README)
```

---

## Multi-Agent Coordination Harness

Coordination uses two layers:

- **`WORKLOG.md`** — immutable per-commit retrospective (committed history).
- **`agent-comms/`** — in-flight coordination (tasks, handoffs, verifications, findings, questions, decisions, history). Protocol: `agent-comms/README.md`.

Each agent's pre-flight reading list and end-of-work routine live in its own charter at `.claude/agents/novetest-<team>-team.md`. PM owns cross-team process oversight and DoD bookkeeping.

### Operating model — PM-orchestrated delivery cycle

Delivery runs as a **PM-orchestrated cycle** (`agent-comms/decisions/2026-07-06-pm-orchestrated-delivery-cycle.md`). The **main session operates as the PM-orchestrator**: on the CEO's kickoff it plans, takes CEO approval (Gate 1), then dispatches the execution teams and sequences merge→verify via `.claude/workflows/delivery-cycle.js`, reports back, takes push authorization (Gate 2), and cleans up. **The execution teams — the `novetest-*-team` agents, Main Branch, Manual Test — are dispatched by the orchestrator, not by the CEO.** `CEO_ROUTINE.md` is the CEO-facing view; `.claude/agents/novetest-pm-team.md` is the orchestrator's operating manual. A `novetest-*-team` subagent dispatched during a cycle simply executes its task brief per its own charter — it need not know who pulled the chain.

**Language.** The orchestrator replies to the CEO in the console in Korean (한국어); everything written to a file or exchanged between agents — task briefs, handoffs, verifications, findings, decisions, history, charters, `WORKLOG.md`, commit messages, code — stays in English. Execution teams always read and write English; the Korean surface is only the CEO-facing console (orchestrator and, when consulted, the Secretary).

### Team communication overview

| Folder | Flow | Purpose |
|---|---|---|
| `agent-comms/tasks/` | PM → Team | Work assignments |
| `agent-comms/handoffs/` | Team → Main Branch | Worktree ready to merge |
| `agent-comms/verifications/` | Main Branch → Manual Test | Merged commit; what to verify |
| `agent-comms/findings/` | Manual Test → PM | E2E results, regressions |
| `agent-comms/questions/` | Any → PM/CEO | Blockers, ambiguities |
| `agent-comms/decisions/` | PM (CEO-approved) → All | Binding directives (permanent) |
| `agent-comms/history/` | PM → All | Curated cycle summaries (permanent) |
