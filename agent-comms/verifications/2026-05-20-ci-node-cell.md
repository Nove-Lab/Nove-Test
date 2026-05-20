---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-20
slug: ci-node-cell
related:
  - handoffs/release-team-2026-05-20-ci-node-cell.md
  - handoffs/memory-team-2026-05-20-entry-id-contract-note.md
---

# Verification: CI Node.js cell + Memory contract note (no Manual Test action)

This doc records two slices merged this cycle that have **no Manual Test
verification surface**. It exists for PM bookkeeping and to tell Manual
Test explicitly: nothing to run here.

## 1. ci-node-cell (Release team)

- Merged: `68a4dcb` — `ci: add Node.js + jest fixture deps so jest
  integration tests run`; `cc729d3` — `comms: stage release-team
  ci-node-cell handoff`.
- Source handoff: `handoffs/release-team-2026-05-20-ci-node-cell.md`.
- Scope: `.github/workflows/ci.yml` only (+26 lines, two appended steps —
  `actions/setup-node@v4` node 20 + a fixture `npm install` loop). No
  `src/`, no `tests/`, no `pyproject.toml`.
- **Verification is GHA observation, owned by the Release team** — this
  was an explicit **pre-merge handoff** (`verdict:
  pre-merge-pending-gha-observation`). CI fires only on push to `main`;
  Release will observe the run once `main` is pushed and supersede their
  handoff with a `status: done` version carrying the run URL + whether
  the jest integration tests report as *run* (not *skipped*).
- **Manual Test: no action.** You cannot trigger GHA; the local jest
  tests still skip without Node.js.
- Watch point flagged by Release for the post-merge observation:
  `windows-latest` jest cross-OS reliability; documented fallback is
  restricting the fixture-install step to `ubuntu-latest` if flaky.

## 2. entry-id-contract-note (Memory team)

- Merged: `5c65665` — `docs(memory): document entry_id == run_id v1
  equivalence in interface contract`.
- Source handoff: `handoffs/memory-team-2026-05-20-entry-id-contract-note.md`.
- Scope: `design/interace-contract/memory.md` only — one bullet added to
  the `## Notes` section recording the v1
  `entry_id == run_record.run_reference.run_id` equivalence. **Doc-only.**
- The handoff explicitly states: "Main Branch may merge directly — no
  Manual Test verification round is needed." No `src/`, no `tests/`, no
  schema change.
- **Manual Test: no action.**

## Merge notes

- Both slices were based on `3a84aab`; rebased cleanly onto current main
  (the only intervening commit, `215a941`, is comms-only — disjoint).
  No conflicts.
- These two slices contributed nothing to the test gate (CI YAML + a
  design doc). The combined post-merge gate for the cycle —
  `uv run pytest -q` -> 334 passed / 3 skipped, `uv run mypy` -> clean
  (52 files) — is reported in the sibling verification docs.

## Reporting

No findings file required for these two slices. If Manual Test wants to
acknowledge, a single line in any of this cycle's findings docs is
sufficient.
