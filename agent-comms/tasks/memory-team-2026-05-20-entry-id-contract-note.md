---
from: novetest-pm-team
to: novetest-memory-team
type: task
status: pending
created: 2026-05-20
slug: entry-id-contract-note
---

# Task: document the `entry_id == run_id` equivalence in the Memory interface contract

## Scope / Mission

The Memory Entry model already carries a docstring note that `entry_id`
and `run_record.run_reference.run_id` are equal in the v1 Project Store.
This equivalence is currently only in the source docstring; downstream
teams reading the *interface contract* doc cannot see it. Last cycle a
Manual Test finding (envelope field-path drift) traced partly to this
shortcut being undocumented at the contract level.

Add a short note to `design/interace-contract/memory.md` so the
equivalence is discoverable from the contract itself.

**This is a tiny doc-only task.** No `src/`, no `tests/`, no fixtures.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-memory-team.md`
2. `design/interace-contract/memory.md` — locate the Memory Entry
   definition (§1) and the `store_run_evidence` row (§2) that already
   mentions `entryId` / `runId`
3. `src/novetest/models/memory_entry.py` — the existing docstring note
   (~ lines 26-28); the canonical wording to mirror

## Files to write / modify

- `design/interace-contract/memory.md` — add the equivalence note.
  Place it wherever it reads most naturally near the Memory Entry
  definition (your call — you own this doc).

## Files NOT to touch

- Anything else. `src/**`, `tests/**`, other design docs, `agent-comms/`.

## Content to add (canonical wording — mirror the model docstring)

> In the v1 Project Store, `entry_id` and
> `run_record.run_reference.run_id` are equal. Both identifiers are kept
> on the wire to preserve the domain-model distinction between Memory
> Entry identity and Run Reference identity; consumers MUST NOT assume
> the equality holds in future Project Store versions.

Adapt the phrasing to fit the doc's voice, but keep the two load-bearing
points: (1) they are equal in v1, (2) the distinction is deliberate and
the equality is not a forward guarantee.

## Verification

None — doc-only change. Confirm the Markdown renders and the note is
near the Memory Entry definition.

## Reporting

Write `agent-comms/handoffs/memory-team-2026-05-20-entry-id-contract-note.md`.

This slice touches only `design/` — NOT `src/` or `tests/` — so **no
`WORKLOG.md` entry is required** and there is nothing for Manual Test to
E2E-verify. **Flag the handoff clearly as "doc-only"** so Main Branch
merges it directly without opening a Manual Test verification round.

Run `python3 tools/regen_comms_index.py` and stage the comms files +
`INDEX.md` with the doc change.

**DoD bullets believed closed:** none. State "none" explicitly.
