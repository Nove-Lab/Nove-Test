# CEO Operating Routine

How the CEO runs a delivery cycle now that the **PM orchestrates** it. Your only job in a
cycle is two decisions; the PM-orchestrator does the dispatching, sequencing, and reporting
in between.

This is the human-facing companion to `agent-comms/README.md` (the protocol),
`.claude/agents/novetest-pm-team.md` (the orchestrator's operating manual), and
`agent-comms/decisions/2026-07-06-pm-orchestrated-delivery-cycle.md` (why it works this way).

---

## The model in one paragraph

You talk to **one** thing: the **PM-orchestrator**, which is your main Claude Code session
itself (not a spawned `@novetest-pm-team` subagent — see "How to start a cycle" for why).
It plans the day, shows you the plan, and — once you approve — dispatches every team,
merges, verifies, and reports back. You step in exactly twice: to **approve the plan** and to
**confirm the report + authorize the push**. Everything else is automated beneath the PM.

---

## The cycle at a glance

```
1. PM plans          orchestrator: status-check → triage → draft tasks/ + plan
        ↓
2. YOU approve       ── GATE 1 ── approve the plan (+ answer any questions/)
        ↓
3. Work teams        orchestrator dispatches teams in parallel → handoffs/
        ↓
4. Main Branch       merge + test gate (pytest+mypy) + commit → verifications/
        ↓
5. Manual Test       E2E verification → findings/           (doc-only cycles skip this)
        ↓
6. PM reviews        orchestrator: DoD check + reads findings → reports to YOU
        ↓
7. YOU confirm       ── GATE 2 ── confirm report + authorize push
        ↓
8. PM finalizes      DoD tick + history/ + delete transients → push (delivery+cleanup) → preview next
```

Steps 3–5 run as one background **`delivery-cycle` workflow** (fan-out → merge → verify).
You are not in the loop for any of it — the PM is.

---

## How to start a cycle (invocation)

Talk to your **main session directly**. Do **not** address `@novetest-pm-team` — that spawns
a planning-only subagent that *cannot pause for your approval*, so it can't run the full cycle
with its two gates. The orchestrator has to be the main session so it can hand control back to
you at each gate.

Two equivalent ways to kick off:

- **Slash command (preferred):** `/cycle`
  Expands to the orchestrator kickoff (includes the workflow authorization). Optionally pass a
  focus, e.g. `/cycle W0 릴리스 착수`.
- **Plain phrase with the workflow opt-in:** include the word **`ultracode`** so the session is
  authorized to run the delivery workflow, e.g.
  `ultracode 오늘의 사이클 시작하자` / `ultracode, start today's cycle`.

Either way the session will: run `git fetch && git status` + the standup, triage
`findings/`+`questions/`, draft the plan, and **stop at Gate 1 for you.**

> Quick status without starting a cycle? Just ask the session "지금 상태 어때? / where are we?"
> (or consult `novetest-secretary` for a read-only briefing). No `ultracode` needed for a
> read-only glance.

---

## Your two decisions (the only manual steps)

### Gate 1 — Approve the plan (after step 1)

The orchestrator shows you:
- The task breakdown (which teams, what each builds, parallel vs. sequential).
- Any `questions/` needing a **CEO call**, each with concrete options + a recommendation.
- Scope/risk notes and whether Manual Test E2E is needed (doc-only cycles skip it).

You: approve as-is, adjust, or decide the open questions. On your word the orchestrator writes
any `decisions/` and launches the workflow. **Nothing is dispatched until you approve.**

### Gate 2 — Confirm the report + authorize push (after step 6)

The orchestrator reports:
- What each team shipped + the merged commit(s) (still local — **not pushed**).
- The test-gate result and the Manual Test verdict (`passed`/`failed`/`partial`).
- DoD bullets it intends to tick, and any risks/regressions.

You: confirm and say **push** (or hold). Push happens **only** on your explicit word. On your yes
the orchestrator finalizes — runs the cleanup bookkeeping, then a **single push** covering the
delivery commit(s) *and* the cleanup commit — and closes with a one-line summary + a preview of the
next cycle.

### Escalations (mid-cycle, only if something breaks)

If the test gate fails at step 4, or Manual Test returns `failed`/`partial`, or a team hits a
blocker, the workflow surfaces it and the orchestrator brings it to you **at the next gate or
immediately** with options — it does not silently retry forever or push broken code. A blocked
slice loops back through `questions/` → re-plan, exactly as before, but the PM drives the loop.

---

## Decisions the CEO keeps (never delegated)

1. **Approving the plan** — Gate 1.
2. **Answering `questions/`** — cross-team contract or direction calls (surfaced at Gate 1 or as an escalation).
3. **Authorizing `push`** — Gate 2. Per-push, never standing.
4. **Acting on failed `findings/`** — whether a regression rides the next cycle or gets a hotfix.

Everything else — planning, team dispatch, merge mechanics, verification sequencing, cleanup —
is the PM-orchestrator's job.

---

## Operating tips

- **Parallelism ceiling.** ~3 concurrent work teams per cycle keeps merges clean and the plan
  reviewable. If the PM proposes more, it will phase the rest; you can ask it to at Gate 1.
- **Not every cycle runs all 8 steps.** Charter / design-doc-only changes skip Manual Test
  (steps 4/8 still merge + clean up, but no E2E). The PM tells you which shape a cycle is at
  Gate 1. Only work touching `src/` or `tests/` runs the full cycle.
- **You never dispatch a team by hand anymore.** If you find yourself typing
  `@novetest-run-team`, stop — that's the PM's job now. Give direction at Gate 1 instead.
- **The PM stops at gates, not for everything.** Between Gate 1 and Gate 2 it runs autonomously.
  If you want a peek, `/workflows` shows live progress of the delivery workflow.
