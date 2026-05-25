---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-25
slug: duplicate-merge-cycle
related:
  - decisions/2026-05-25-supported-engine-matrix.md
---

# History: Duplicate-merge incident — PM dispatched off a 4-day-stale local main

A coordination break, not a team-output failure. PM planned today's
cycle from a local `main` checkout that was 12 commits behind origin;
the two dispatched teams correctly executed work origin had already
shipped on 2026-05-21. Main Branch caught it at pre-flight and surfaced
a question rather than merging. PM resolved by discarding the
working-tree duplicates while preserving both branches as historical
refs, executing the fast-forward reconcile directly under CEO
authorization.

## Timeline

| Time (KST) | Event |
|---|---|
| 2026-05-21 14:18 – 15:52 | A *separate* PM session dispatched + closed the 2026-05-21 batch (Phase 2 DoD #4 perf, GHA Node-24 bump, jest charmap fix, ci-perf-lane). All pushed to origin/main as 12 commits ending at `1d7c79d`. |
| 2026-05-25 (today)  | Today's PM session opened on local `main` @ `492f7b9` — never pulled. Read local INDEX, planned a "Phase 2 closing" cycle that was already closed on origin. Dispatched Coverage + Release tasks. |
| 2026-05-25  | Two teams completed worktrees branched off `492f7b9`. Main Branch's pre-flight noticed local was 12 behind origin AND that both worktrees' content was already present (in different implementations) on origin. STOP-and-surfaced via `questions/main-branch-team-2026-05-25-duplicate-merge-cycle.md`. |
| 2026-05-25  | CEO routed the question to PM. PM analyzed both slices, concluded discard for both (origin's implementations are equivalent or better). CEO authorized PM-direct reconcile. PM executed: fast-forward pull + `git worktree remove` (branches NOT deleted) + comms commit `0ac0e84`. |

## What closed

- Nothing on `delivery-phasing.md` (Phase 2's #4 was already closed by
  origin's `5489c7e`; this incident's commit is comms-only).
- Cycle closed cleanly: 0 in-flight, 0 pending, 0 open questions,
  working tree at `origin/main` (now `0ac0e84`).

## Load-bearing learnings

### 1. PM pre-flight discipline — `git fetch && git status` is mandatory

The whole incident stems from a stale local `main`. PM's pre-flight
reading list started with `agent-comms/INDEX.md` — but `INDEX.md` only
reflects whatever the local checkout knows about. A `git fetch && git
status` check would have shown "12 behind origin" instantly, and the
entire mis-dispatch would have been impossible.

**Fix (this commit cycle): PM charter pre-flight gains a step 0** —
`git fetch && git status`, confirming "Your branch is up to date with
'origin/main'" before reading INDEX. Any "behind / diverged" state
becomes a STOP-and-ask moment.

### 2. The EnterWorktree harness creates parallel-session reality

A previous PM session ran while *this* PM session was offline; its
pushes were not reflected on this checkout because PM never fetched.
On a single desktop running multiple Claude sessions, parallel PM
sessions are a real possibility. The pre-flight `git fetch` is the
defensive layer.

### 3. "No loss" preservation via branch refs, not merge

Literal "merge both" was incoherent — both slices conflict at the
content level (same paths for Coverage; mutually-exclusive YAML values
for GHA). But preservation does not require merge: `git worktree
remove` without `git branch -D` keeps the worktree's commits alive as
dormant refs forever, at zero cost. Future cherry-picks are one
`git checkout` away.

Preserved branches:

| Branch | Head | Origin counterpart | Cherry-pick candidate |
|---|---|---|---|
| `coverage-compare-perf` | `d0a7f7d` | `5489c7e` (already on main) | None identified — origin's is materially faster (0.024s vs 0.094s median). |
| `worktree-gha-deprecations` | `94e7411` | `57cdf0d` (already on main) | **`@v8.1.0` immutable-pin for `astral-sh/setup-uv`** — supply-chain hardening (astral-sh stopped publishing floating tags from v8.0.0). Deferred to a future Release housekeeping slice; cherry-pick from this branch when picked up. |

### 4. PM-direct reconcile principle (new)

PM is authorized to execute a reconcile (pull + worktree teardown +
comms commit) directly, bypassing Main Branch dispatch, **iff**:

1. The pull is fast-forward (zero conflict resolution required), AND
2. The reconcile commit touches only `agent-comms/**` and / or
   PM-owned files (no `src/**`, no `tests/**`, no
   `.github/workflows/**`, no `pyproject.toml`), AND
3. There is no source-tree merge to perform (worktrees discarded or
   their content is already on origin).

Any deviation reverts to Main Branch territory. This codifies an
efficient path for fast-forward incident cleanup while preserving the
charter's separation of concerns for substantive merges. Recorded
here, not lifted into the PM charter, until a second instance
justifies the abstraction.

## Open follow-ups (low priority)

1. **`@v8.1.0` immutable-pin port** — port from
   `worktree-gha-deprecations @ 94e7411` into both
   `.github/workflows/ci.yml` and `release-test.yml`. Surgical, 2-line
   change + comment. NOT urgent — origin's `@v7` is functional and the
   2026-06-02 Node-24 deadline is met. Belongs to a future Release
   housekeeping slice.
2. **Phase 3 entry preparation** — Phase 2 is complete on origin (4/4
   DoD). The next sub-product cycle is Regression. PM's prior
   commitment ("background prep during the cycle") is moot since the
   cycle never had a real workload; carry this commitment to the next
   cycle planning conversation.

## Process notes

- This is the second incident in the project's life where a stale
  local view caused planning error (the first was a missed DoD tick in
  the 2026-05-16 cleanup, corrected in 2026-05-21 history). The
  pattern is consistent: PM trusts local INDEX without verifying its
  upstream-currency. The `git fetch` pre-flight closes the loop.
- Main Branch's STOP-and-surface (instead of merging blind) is the
  reason this incident cost only a comms commit and not a force-push
  recovery on origin. Pattern to reinforce: when pre-flight discovers
  unexpected state, write a question with the diagnosis + a suggested
  resolution path. Main Branch's question file was the working
  document PM used to make the discard call.
