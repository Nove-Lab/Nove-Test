---
from: novetest-main-branch-team
to: novetest-pm-team
type: question
status: resolved
created: 2026-05-25
resolved: 2026-05-25
slug: duplicate-merge-cycle
related:
  - decisions/2026-05-25-supported-engine-matrix.md
---

# Question: Two worktrees ready to merge appear to DUPLICATE work already on origin/main

## TL;DR

CEO asked me to merge two completed worktrees. Before touching them I
re-ran the pre-flight and discovered the **local `main` checkout is 12
commits behind `origin/main`**, and **origin/main already contains
equivalent work for both slices** (committed 2026-05-21). The teams
appear to have re-done already-shipped work in worktrees branched from
the stale local `main` (`492f7b9`).

Merging either worktree as-is would force-supersede an already-merged
implementation with a divergent one — an architectural decision I do
not have the authority to make. Holding both merges pending PM/CEO
direction.

## Concrete state

### Local working tree (main checkout)

- `HEAD = 492f7b9` (last commit I pushed on 2026-05-21 night).
- `git status`:
  - **Modified (uncommitted):** `agent-comms/INDEX.md` — locally
    regenerated to include the two untracked files below.
  - **Untracked:** `agent-comms/decisions/2026-05-25-supported-engine-matrix.md`,
    `agent-comms/tasks/release-team-2026-05-25-gha-deprecations.md`.
  These look like in-flight PM artifacts (CEO-approved decision; new
  task dispatch). I have not touched them.

### `origin/main` is 12 commits ahead

```
1d7c79d comms: close ci-perf-lane cycle — perf CI lane live, non-blocking, 9/9+perf green
1a92ea0 comms: manual-test findings for ci-perf-lane slice
cb7a538 comms: verification request for ci-perf-lane merge
12cf04d ci: add non-blocking tests/perf lane + harden install-script test encoding
c598eb3 comms: close 2026-05-21 batch — Phase 2 complete (DoD #4), queue ci-perf-lane
7fb7366 comms: manual-test findings for 2026-05-21 merge batch
ec5c891 comms: verification requests for 2026-05-21 merge batch
5489c7e test(coverage): NFR-COV-002 50k-location perf benchmark for coverage diff
ed0992b comms: handoff for release-team ci-maintenance (Slice A)
57cdf0d ci: bump GHA actions to Node 24 runtime majors
310bc87 fix(run): pin encoding=utf-8 on CLI test-harness subprocess capture
69c6c74 comms: queue CI-maintenance + jest-charmap tasks (2026-05-21 PM cycle)
```

### The two "ready" worktrees

| Worktree | Branch | Head | Base |
|---|---|---|---|
| `/home/yjshin/dev/novetest-coverage-compare-perf` | `coverage-compare-perf` | `d0a7f7d` | `492f7b9` (stale main) |
| `/home/yjshin/dev/novetest-gha-deprecations` | `worktree-gha-deprecations` | `94e7411` | `492f7b9` (stale main) |

Both rebase cleanly onto `492f7b9` (current local main) — but that's
the stale main. They will conflict heavily against `origin/main`.

## Per-slice overlap with origin/main

### Slice 1: coverage-compare-perf

**Origin/main has:** `5489c7e test(coverage): NFR-COV-002 50k-location
perf benchmark for coverage diff` (2026-05-21).
- Adds `tests/perf/__init__.py`, `tests/perf/coverage/__init__.py`,
  `tests/perf/coverage/generate_large_fact_set.py`,
  `tests/perf/coverage/test_perf_compare.py`.
- Same NFR target (≤5.0s for 50k locations), same general approach
  (programmatic generator + median-of-N assertion).
- Observed `median = 0.024s` on the merged version.

**Worktree (`d0a7f7d`) re-creates the SAME files** with different
content:
- Different generator API (`generate_fact_set(run_id, num_files,
  lines_per_file, branches_per_file, *, file_offset=0)`).
- Different delta sketch (450 common / 50 added / 50 removed, vs
  origin's split which I haven't diffed line-by-line).
- Observed `median = 0.094s` on this worktree's box.
- Slightly more conservative pinned-shape guards.
- Phase 2 DoD #4 is **already closed** on origin/main per `c598eb3`.

**Plus:** origin/main subsequently added `12cf04d ci: add non-blocking
tests/perf lane` — the perf lane was wired into `ci.yml`. The
worktree's handoff explicitly avoids touching `ci.yml`, so a merge
would not regress that, but Coverage Team's "out of scope: CI perf
lane wiring is a separate Release task" framing is now stale (Release
already shipped it).

### Slice 2: gha-deprecations

**Origin/main has:** `57cdf0d ci: bump GHA actions to Node 24 runtime
majors` (2026-05-21).
- Pins: `checkout@v6`, `setup-node@v6`, **`setup-uv@v7` (floating major)**,
  `upload-artifact@v7`, `download-artifact@v8`, `gh-release@v3`,
  `rust-toolchain@stable` untouched.

**Worktree (`bfa8ed4`) makes the SAME bumps EXCEPT setup-uv:**
- Pins: same as origin, except **`setup-uv@v8.1.0` (immutable release tag)**
  — chosen because v8.0.0 release notes state the project stopped
  publishing floating major/minor tags for supply-chain hardening.
- Adds 8 lines of explanatory comments to both workflow files about
  the immutable-tag pinning policy.
- Side-finding in the handoff: `setup-uv@v3` had no `python-version`
  input declared at all (added in v4.1.0) — the `python-version` line
  was a silent no-op on `@v3`. Origin's `57cdf0d` commit message
  acknowledges the same point.

The version-pin disagreement (`@v7` vs `@v8.1.0`) is the substantive
difference. Both work; the worktree's choice is more conservative
re: supply-chain risk, but origin's is already live and (per the
post-merge GHA observation) presumably green.

## Most likely root cause

PM's local working tree was never updated after my 2026-05-21 pushes:
`492f7b9` (where my prior session left `main`) is exactly the head PM
appears to have been building on. The two new tasks (the local
untracked task file + the still-pending `coverage-team-2026-05-20-...`
in the local INDEX) were dispatched off that stale state, the teams
worked in worktrees branched from it, and the result is duplicate
implementations of work that origin has already shipped.

This is a coordination break, not a team-output failure. Both
worktrees did exactly what their tasks asked. PM was unaware origin
had moved.

## What I have NOT done (deliberately)

- **No `git pull`** on local main. Pulling is mechanically safe (the
  two untracked PM files don't conflict; INDEX.md is auto-generated)
  but I don't want to advance HEAD before PM has reasoned about which
  branch of history is canonical.
- **No worktree merges.** Both worktree heads conflict with
  origin/main in non-trivial ways (same paths, divergent content).
  Merging without direction would amount to architectural override.
- **No worktree teardown.** Both worktrees + branches are intact for
  PM to inspect / cherry-pick from / discard as appropriate.
- **No edits to PM's local files** (decision, task, INDEX
  modification). They remain exactly as I found them.

## What PM/CEO needs to decide

1. **Coverage worktree (`d0a7f7d`) — discard, partial cherry-pick, or supersede origin's `5489c7e`?**
   - Discard: simplest. Coverage team's slice is already shipped under
     a different implementation; the new implementation has no
     observable advantage.
   - Cherry-pick: if any of the worktree's pinned-shape guards or
     generator-API decisions are wanted, PM can dispatch a Coverage
     follow-up to port specific bits into the live `tests/perf/`.
   - Supersede: replace origin's implementation with the worktree's.
     This would require a fresh merge / force-push narrative on `main`
     and is high-friction; I do NOT recommend it unless the worktree's
     implementation is materially better in a way I'm missing.

2. **GHA-deprecations worktree (`94e7411`) — discard, port the
   `@v8.1.0` immutable-pin change, or supersede `57cdf0d`?**
   - Discard: simplest. The 2026-06-02 deprecation deadline is
     already cleared by origin's `57cdf0d`.
   - Port the `@v8.1.0` pin: surgical change (1 line in `ci.yml`, 1 in
     `release-test.yml` + comment block). Worth doing if the
     supply-chain-hardening rationale is endorsed.
   - Supersede: same high-friction caveat as above; not recommended.

3. **PM's local untracked files** —
   - `decisions/2026-05-25-supported-engine-matrix.md` is independent
     and substantive (no overlap with origin); ready to commit + push
     as-is.
   - `tasks/release-team-2026-05-25-gha-deprecations.md` is the
     duplicate-dispatch task. Likely should be **closed without
     merging the handoff** (added to history with a "superseded by
     origin's 57cdf0d" note) rather than committed as a live task.
   - `agent-comms/INDEX.md` modification is stale (built off
     `492f7b9`); should be regenerated after the local PM files are
     committed (or discarded).

4. **Operational follow-up:** PM should `git pull` before any further
   dispatch cycle. This duplicate cycle would have been caught at the
   pre-flight step had origin been current.

## Suggested resolution path (if helpful — final call is PM's)

If CEO agrees the simplest outcome is best:

1. CEO confirms "discard both worktrees, keep PM's decision file, drop
   the duplicate task file".
2. PM commits + pushes
   `decisions/2026-05-25-supported-engine-matrix.md` alone (with
   regenerated INDEX), no task file.
3. Main Branch pulls origin/main into local main (now a no-op for
   working tree; HEAD advances from `492f7b9` → `1d7c79d`).
4. Main Branch removes both worktrees + deletes both branches via
   `git worktree remove --force` + `git branch -D`.
5. PM optionally dispatches a tiny Release follow-up to port the
   `@v8.1.0` immutable-tag pin if the supply-chain rationale is
   accepted.

Awaiting CEO/PM direction before any merge / pull / worktree teardown.
---

## PM resolution (2026-05-25)

**Decision: PM executes the reconcile directly. Discard the working-tree
duplicates; preserve both branches as historical refs.**

CEO authorized PM to do the reconcile in-line rather than round-tripping
through a fresh Main Branch dispatch. The work is pure git plumbing
(`git pull --ff-only` + `git worktree remove`) plus comms; no `src/**`
or `tests/**` edits, no workflow edits. Future principle: PM may execute
a reconcile directly when (a) fast-forward, (b) no source/test/workflow
edits, (c) commits are comms-only. Any deviation reverts to Main Branch
territory. To be codified in PM charter at cleanup.

### Per-slice rationale (unchanged from the prior block)

**Coverage worktree (`d0a7f7d`)** — discard.
- Origin's `5489c7e` already closed Phase 2 DoD #4 with an identical NFR
  target and equivalent methodology.
- Performance favors origin: median `0.024s` vs the worktree's `0.094s`
  (both under the 5.0s NFR; origin is ~4x faster).
- Cherry-pick value: zero observable.

**GHA-deprecations worktree (`94e7411`)** — discard.
- Origin's `57cdf0d` already cleared the 2026-06-02 deadline with
  Node-24 majors across all actions.
- Sole substantive difference: `astral-sh/setup-uv@v8.1.0` (immutable
  tag) vs origin's `setup-uv@v7` (floating). Supply-chain rationale is
  sound but **not urgent** — current state is deadline-compliant.

### "No loss" preservation — branches kept

Per CEO's intent that team output not be discarded:

- `git worktree remove --force` was used to remove only the working-tree
  directories.
- **`git branch -D` was NOT used.** Both branches survive as dormant git
  refs:
  - `coverage-compare-perf` @ `d0a7f7d`
  - `worktree-gha-deprecations` @ `94e7411`
- Future cherry-pick is one `git checkout <branch>` away. In particular,
  the `@v8.1.0` immutable-pin idea from `worktree-gha-deprecations` is
  the recommended candidate for a future Release housekeeping slice —
  the branch is the source of truth, no need to re-implement.

### PM execution log

Captured for audit (executed on the main checkout, 2026-05-25):

```
$ git pull --ff-only origin main
Updating 492f7b9..1d7c79d
Fast-forward
  ... 14 files changed, 606 insertions(+), 172 deletions(-)
$ git log -1 --format='%H %s'
1d7c79d8ff1756f260ac27532a47164f7b0330e3 comms: close ci-perf-lane cycle …

# Verified origin's shipped work:
$ ls tests/perf/coverage/
__init__.py  generate_large_fact_set.py  test_perf_compare.py
$ grep -c 'checkout@v6' .github/workflows/ci.yml
1
# Phase 2 DoD #4 confirmed ticked in delivery-phasing.md.

$ git worktree remove --force /home/yjshin/dev/novetest-coverage-compare-perf
$ git worktree remove --force /home/yjshin/dev/novetest-gha-deprecations
$ git worktree list
/home/yjshin/dev/Nove-Test  1d7c79d [main]
$ git branch
  coverage-compare-perf
* main
  worktree-gha-deprecations
```

### Surviving PM artifacts

- `decisions/2026-05-25-supported-engine-matrix.md` — kept; permanent
  contract; no overlap with origin.
- `tasks/release-team-2026-05-25-gha-deprecations.md` — deleted from
  working tree (never committed; obsolete duplicate dispatch).
- `tasks/main-branch-team-2026-05-25-reconcile-duplicate-cycle.md` —
  deleted from working tree (PM executed directly; the dispatch never
  happened).
- `agent-comms/INDEX.md` — will be regenerated next.

### Charter update commitment (PM cleanup)

`.claude/agents/novetest-pm-team.md` pre-flight reading list will be
revised to mandate `git fetch && git status` as the FIRST step, before
reading `agent-comms/INDEX.md`. This is the load-bearing learning of
this incident: a stale local `main` made the entire today's dispatch
plan operate on 4-day-old reality. The hook-blocked Write tool already
forces PM to use Bash heredocs (GOTCHAS.md sanctioned fallback); the
new pre-flight step makes "current upstream" equally mandatory.

### Thank you

Main Branch team's STOP-and-surface saved a duplicate push to origin
and an architectural override of already-shipped work. The question
file's slice-by-slice diagnosis was load-bearing for PM's discard
decision. The pattern (pre-flight → discrepancy → STOP → question with
diagnosis + suggested resolution path) is exactly the bar future
incidents should meet.

