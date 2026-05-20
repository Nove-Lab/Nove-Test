---
from: novetest-memory-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-20
slug: entry-id-contract-note
doc-only: true
---

# Handoff: document the `entry_id == run_id` equivalence in the Memory interface contract

## Summary

**Doc-only change.** Added a note to `design/interace-contract/memory.md`
making the v1 `entry_id == run_record.run_reference.run_id` equivalence
discoverable from the interface contract itself. Mirrors the existing
docstring in `src/novetest/models/memory_entry.py` (~lines 26-28).

No `src/`, no `tests/`, no fixtures touched. **Main Branch may merge
directly — no Manual Test verification round is needed.**

## Worktree

- Worktree: `../novetest-entry-id-contract-note`
- Branch: `memory-entry-id-contract-note`
- Base: `3a84aab`

## Files changed

- `design/interace-contract/memory.md` — one bullet added to the `## Notes`
  section, immediately after the "Memory does not derive ..." note and
  near the §1/§2 interface tables. Keeps the two load-bearing points:
  (1) `entryId` and `runRecord.runReference.runId` are equal in v1,
  (2) the distinction is deliberate and the equality is not a forward
  guarantee.
- Plus the regenerated `agent-comms/INDEX.md` and these comms files.

## Verification

None required — doc-only change. Markdown renders; the note sits in the
`## Notes` section adjacent to the Memory Entry / `store_run_evidence`
definitions.

## Worklog

No `WORKLOG.md` entry — this slice touches only `design/`, not `src/`
or `tests/` (per the task's reporting instructions).

## Schema-version implications

None. No model, schema, or persisted-entity change. The note documents
an existing v1 property; it does not introduce or alter a contract.

## DoD bullets believed closed

None.
