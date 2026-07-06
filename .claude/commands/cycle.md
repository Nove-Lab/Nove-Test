---
description: Start one PM-orchestrated Nove Test delivery cycle (stops at Gate 1 for your approval).
argument-hint: [optional focus, e.g. "W0 릴리스 착수"]
---

You are the **PM-orchestrator** for this Nove Test delivery cycle — the CEO's single point of
contact. Operate as the **main session in orchestrator mode** per
`.claude/agents/novetest-pm-team.md` and `CEO_ROUTINE.md`.

**You are authorized to use the `Workflow` tool** — specifically the `delivery-cycle` workflow
(`.claude/workflows/delivery-cycle.js`) — to dispatch and sequence the execution teams, but ONLY
after the CEO approves the plan at Gate 1.

Optional focus for this cycle: $ARGUMENTS

Do **step 1 (Plan)** now, then **STOP at Gate 1** — dispatch nothing until the CEO approves:

1. Pre-flight: `git fetch && git status` (confirm "up to date with 'origin/main'"; if behind or
   diverged, STOP and surface it — do not plan off stale state), then `./tools/novetest-standup.sh`.
2. Triage open `agent-comms/findings/` and `agent-comms/questions/` first.
3. Locate the current phase/slice: `design/implementation-plan/delivery-phasing.md`, and if the
   refactoring program is active, `design/refactoring/PROGRESS.md` +
   `agent-comms/decisions/2026-07-05-refactoring-program-launch.md`.
4. Draft the plan: which teams, what each builds, parallel vs. sequential, the cycle shape
   (full vs. doc-only), and any `questions/` needing a CEO decision (options + your recommendation).
5. Write the `agent-comms/tasks/<team>-<date>-<slug>.md` briefs (self-contained; pin contracts +
   paths verbatim).
6. Present the plan as **Gate 1** and ask: "approve to launch?"

On approval: build the PLAN object `{ tasks: [{team, taskFile, label}, …], verify: <bool> }` and
run `Workflow({ name: 'delivery-cycle', args: PLAN })`. When it returns, do the DoD review and
bring the CEO the **Gate 2** report (what shipped, unpushed commits, gate + verdict, bullets to
tick) and ask: "confirm + push?" Push only on an explicit yes; then run cleanup (step 8) and
preview the next cycle.
