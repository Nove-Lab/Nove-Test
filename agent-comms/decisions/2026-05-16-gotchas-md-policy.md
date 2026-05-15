---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-16
slug: gotchas-md-policy
related:
  - GOTCHAS.md
---

# Decision: Operational quirks live in `GOTCHAS.md` (not CLAUDE.md)

CEO-approved on 2026-05-16. Establishes a permanent home for harness / tool / runtime quirks and the sanctioned workarounds, separate from project rules.

## Decision

Timeless **operational quirks** — known failure modes we cannot fix in source, the workarounds that consistently resolve them, and the diagnostic context future agents need — live in **`GOTCHAS.md`** at the repo root. `CLAUDE.md` is for project-wide rules only and contains a one-line pointer to `GOTCHAS.md`.

### Information-architecture map

| Information kind | Home |
|---|---|
| Project rules, structure, ownership | `CLAUDE.md` |
| Team-specific rules and conventions | `.claude/agents/novetest-*-team.md` |
| Per-commit narrative (landed / verified / left open / gotcha / next) | `WORKLOG.md` |
| Cycle-scoped learnings (distilled at cleanup) | `agent-comms/history/<date>-<topic>.md` |
| Binding directives | `agent-comms/decisions/<date>-<slug>.md` |
| **Timeless operational quirks + sanctioned workarounds** | **`GOTCHAS.md`** |

## Rationale

- CLAUDE.md's stated mission is "project-wide rules every agent needs" (line 1). Operational quirks are field reports about runtime behavior we cannot control, not rules. Mixing dilutes CLAUDE.md's signal as a rules surface.
- `WORKLOG.md` and `agent-comms/history/` are time-scoped (per-commit and per-cycle respectively). A quirk that recurs across cycles needs a permanent home, not a buried log entry.
- `agent-comms/decisions/` is for binding directives; documenting a workaround is closer to a how-to than a directive. A workaround can be *promoted* to a decision when CEO commits to a dispatch convention that prevents the quirk; the decision then supersedes the GOTCHAS entry.
- A single root-level `GOTCHAS.md` is the lowest-friction structure: append a section per quirk; no INDEX, no per-topic file proliferation. Volume of operational quirks in a project this size is low; one file suffices.

## Maintenance discipline

- **New quirk** → append a section to `GOTCHAS.md`. PM is the typical author; any team may propose via `agent-comms/questions/<team>-<date>-<slug>.md`.
- **Workaround changes / upstream resolves** → edit the entry in place. Mark resolved when fixed; do **not** delete (history matters for "we already chased this once").
- **Acceptance test** (re-stated from `GOTCHAS.md` itself): an entry belongs there iff (1) the symptom can recur, AND (2) the response is operational, not code-level. Code-level gotchas codified in source + a `WORKLOG.md` "Gotcha" line do **not** belong here.

## Affected teams / files

- **All teams** — when something fails unexpectedly, check `GOTCHAS.md` before assuming charter / hook misconfiguration.
- **PM** — owns `GOTCHAS.md`. Appends quirks during cycle cleanup, or sooner when one is biting active work. Promotes a GOTCHAS entry to a `decisions/` file when CEO commits to a dispatch / convention that prevents the quirk.
- **CLAUDE.md** — top-summary gains a one-line pointer to `GOTCHAS.md`. The `## Harness quirks` section introduced in commit `eebd5d5` is removed; its content relocates to `GOTCHAS.md`.

## Effective date

2026-05-16.

## Supersedes

Partially supersedes commit `eebd5d5` — the harness-quirk *content* lives in `GOTCHAS.md` going forward, not in CLAUDE.md. The Run-team charter cleanup from that commit stands.
