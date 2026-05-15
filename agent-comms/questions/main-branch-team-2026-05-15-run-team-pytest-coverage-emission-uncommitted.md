---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: open
created: 2026-05-15
slug: run-team-pytest-coverage-emission-uncommitted
related:
  - tasks/run-team-2026-05-14-pytest-coverage-emission.md
---

# Question: Run Team's `pytest-coverage-emission` worktree has uncommitted work, no handoff committed

## What I see

The CEO asked Main Branch to merge three completed slices. Two are clean and
landed today:

- `worktree-phase0-release-ci-and-distribution` → `74a6ce4` on `main`
- `worktree-phase2-coverage-foundation` → `dee3252` on `main`

The third worktree at
`/home/yjshin/dev/aispace/Nove-Test.worktrees/phase2-pytest-coverage-emission`
is **not finalized for merge**:

- Branch HEAD = `fe28479` (identical to the pre-merge `main` HEAD).
- `git log main..worktree-phase2-pytest-coverage-emission` is empty — **zero
  commits**.
- The working tree has uncommitted changes to:
  - `src/novetest/run/adapters/pytest_adapter.py` (modified)
  - `tests/unit/run/adapters/test_pytest_adapter.py` (modified)
  - `tests/unit/run/conftest.py` (modified)
  - `pyproject.toml` (modified — adds `pytest-cov>=5.0`, `coverage[toml]>=7.0`)
  - `uv.lock` (modified)
  - `WORKLOG.md` (modified)
  - `agent-comms/INDEX.md` (modified)
- The following are untracked in the worktree:
  - `agent-comms/handoffs/run-team-2026-05-15-pytest-coverage-emission.md`
  - `tests/fixtures/projects/pytest-coverage/`

The handoff file content lists `status: ready` (the other two used
`status: done`) and describes substantive work — new fixture, adapter
changes, test suite up to 187 passed, mypy clean. So a session clearly
ran; it just never committed.

## Why I'm not merging

Per the Main Branch charter:

> Identify mergeable handoffs (worktree path + base commit + verification
> result green).

There is no commit to merge here — the branch and `main` point at the same
SHA. Cherry-picking from the working tree would require me to author commits
on the Run Team's behalf, which the charter forbids:

> All `src/**` and `tests/**` files for NEW logic (you only merge; you do
> not write features or fixes)

## What I need from PM

One of:

1. **(Preferred) Dispatch Run Team to finalize.** Ask them to stage their
   work + the new fixture + the handoff file, commit on
   `worktree-phase2-pytest-coverage-emission`, re-run their test gate, then
   flip the handoff front-matter from `status: ready` → `status: done`. Main
   Branch will merge in a follow-up pass.

2. Authorize Main Branch to commit on behalf of Run Team this once,
   explicitly suspending the charter clause. (I don't recommend this — the
   provenance breaks and the WORKLOG entry would need to be authored by me
   without ground truth on what was actually exercised.)

3. Decide the slice should not land yet — close the task, abandon the
   worktree, and Run Team picks it up in the next planning cycle.

## Downstream impact

The Coverage engine (`dee3252`) already on `main` is built to consume the
`coverage.json` payload that THIS slice produces. Until Run Team's slice
lands, end-to-end (`novetest run --coverage` → `derive_coverage_facts` →
`coverage_facts.json`) cannot be exercised. The Coverage engine's
*unit tests* and Python-API surface are fully green (256 passed). Manual
Test can verify everything that's mergeable today; the end-to-end gap is
called out in
`agent-comms/verifications/2026-05-15-phase0-release-and-phase2-coverage-foundation.md`.

## Reproducer

```
cd /home/yjshin/dev/aispace/Nove-Test.worktrees/phase2-pytest-coverage-emission
git status                  # shows the modified + untracked files above
git log main..HEAD --oneline  # empty
```

Awaiting PM direction before touching this worktree.
