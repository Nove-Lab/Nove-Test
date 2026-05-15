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
