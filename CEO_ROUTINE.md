# CEO Daily Operating Routine

How the CEO leads communication across the Nove Test multi-agent teams, in order.

This is the human-facing companion to `agent-comms/README.md` (the protocol) and
`.claude/agents/novetest-*-team.md` (the team charters). Read those for mechanics;
read this for the daily sequence.

---

## The cycle at a glance

```
0. CEO checks directly     INDEX + findings + questions
        ↓
1. Convene PM              resolve questions (CEO decides → decisions/) + write tasks/
        ↓
2. CEO → work teams        dispatch teams per tasks/ (parallel where independent) → handoffs/
        ↓
3. CEO → Main Branch       merge + test gate → verifications/
        ↓
4. CEO → Manual Test       E2E verification → findings/
        ↓
5. CEO → PM again          cycle cleanup: DoD tick + history + delete transient files
        ↓
   (next day → step 0)
```

---

## Step 0 — Status check (≈5 min, CEO does this directly)

No PM, no teams. Run the standup script for a one-command briefing:

```bash
./tools/novetest-standup.sh
```

It refreshes `agent-comms/INDEX.md`, then prints — in priority order — open
blockers (`questions/`), findings awaiting review, in-flight work per channel,
recent decisions, recent commits, and stale worktrees, ending with a suggested
entry point into this routine. Read-only except for the index refresh.

If you prefer to read the raw files, the three that matter are:

- `agent-comms/INDEX.md` — what was in progress yesterday, open questions, blockers.
- `agent-comms/findings/` — Manual Test verification results. Failures or regressions here are top priority.
- `agent-comms/questions/` — anything a team is blocked on.

Do not skip this step. Going straight to step 1 means PM plans on stale assumptions.

## Step 1 — Convene PM (plan the day + clear blockers)

Dispatch `novetest-pm-team`. Ask it to:

- Triage the `findings/` and `questions/` from step 0.
- Propose the task breakdown for today's phase work.

PM produces:

- For each open `questions/` item: options for the CEO. **The CEO decides.** PM records the decision in `agent-comms/decisions/`.
- `agent-comms/tasks/<team>-<date>-<slug>.md` files — the work briefs for today.
- Parallelizability and dependency notes.

PM does **not** dispatch anyone. It only writes the prompts (the `tasks/` files).

## Step 2 — Dispatch the work teams (parallel)

Read the `tasks/` files PM wrote. Dispatch the named team for each.

- Independent tasks → dispatch teams concurrently (e.g. `novetest-coverage-team` + `novetest-run-team` in parallel).
- Dependent tasks → dispatch in the order PM specified.

Each team works per its charter: isolated worktree → `WORKLOG.md` entry → `agent-comms/handoffs/<team>-...md`, then stops. If a team gets blocked, it writes to `agent-comms/questions/` and stops — that loops back to step 1.

## Step 3 — Dispatch Main Branch (merge)

Once teams have written `handoffs/`, dispatch `novetest-main-branch-team`.

- It reads the handoffs, merges the worktrees, runs the test gate (`pytest` + `mypy`), and commits.
- Gate fails → Main Branch bounces the slice back via `questions/`; the originating team fixes it (back to step 2).
- Gate passes → Main Branch writes `agent-comms/verifications/<date>-<slug>.md` telling Manual Test what to verify.
- **Push happens only when the CEO explicitly authorizes it.**

## Step 4 — Dispatch Manual Test (E2E verification)

Once `verifications/` is posted, dispatch `novetest-manual-test-team`.

- It runs real CLI end-to-end per the verification guide, plus its own edge-case probing.
- It writes `agent-comms/findings/<date>-<slug>.md` — verdict (`passed` / `failed` / `partial`) plus a CEO-readable narrative.
- Regression found → Manual Test does not fix it; it writes a detailed report in `findings/`. The CEO picks it up at the next step 0.

## Step 5 — Convene PM again (cycle cleanup)

When a `findings/` closes as `passed`, dispatch `novetest-pm-team` again for cleanup:

- Read the four transient files for the cycle (task + handoff + verification + findings).
- Verify the handoff's "DoD bullets believed closed" list; **PM ticks** the satisfied bullets in `design/implementation-plan/delivery-phasing.md`.
- Distill anything load-bearing into `agent-comms/history/<date>-<topic>.md`.
- Delete the four transient files, regenerate `INDEX.md`, commit the cleanup.

Then the next day starts again at step 0.

---

## Decisions the CEO must keep (never delegated)

1. **Answering `questions/`** — cross-team contract or direction calls (step 1).
2. **Dispatching teams** — who runs, when, in what parallelism (step 2).
3. **Authorizing `push`** — when Main Branch asks (step 3).
4. **Acting on `findings/`** — whether a regression goes into the next cycle or gets a hotfix (step 4 → step 0).

Everything else — planning, merge mechanics, verification execution, cleanup — is handled by the team charters.

---

## Operating tips

- **Parallelism ceiling.** ~3 concurrent teams per day is the practical limit for the CEO to hold context. If PM splits work finer than that, ask it to phase the rest to "tomorrow."
- **Never skip step 0.** Planning without reading `findings/` and `questions/` first means PM works from stale premises.
- **Not every cycle runs all six steps.** Charter / design-doc-only changes can skip the Manual Test E2E pass (steps 3–4 still merge, but no end-to-end verification needed). Only work touching `src/` or `tests/` runs the full cycle.
- **When blocked, always route back through `questions/` → step 1.** At any step, a blocked team comes back via PM. The only sanctioned team-to-team direct channel is Main Branch → Manual Test (the `verifications/` handoff).
