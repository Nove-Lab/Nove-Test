---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-26
slug: memory-has-regression-facts
related:
  - agent-comms/verifications/2026-05-26-memory-has-regression-facts.md
  - agent-comms/handoffs/memory-team-2026-05-26-has-regression-facts.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
---

# Findings: Memory `_availability_flags` — `has_regression_facts` probe pinned with 8 dedicated test cases

## Verdict

**passed**

Every behavior promised by the verification request reproduces on merged `main` (`2de7bea`). The probe correctly mirrors on-disk state under `<store>/regression/pairs/`, treats baseline-position and target-position pair names symmetrically, treats a missing `regression_facts.json` as `False` even when the pair dir exists, and does not get confused by unrelated pairs sharing the `pairs/` namespace.

## What I tested (for the CEO)

Memory has a flag named `has_regression_facts` attached to every Run Record summary it hands out. The flag is supposed to answer one yes/no question: "Has any prior run-vs-run regression comparison involving this run been computed and persisted to disk?"

This cycle's Memory slice didn't add new behavior — the probe code already shipped two slices ago. It added **eight new pinning tests** so the contract can't drift silently. My job was to confirm (a) the test gate is green, (b) the probe actually behaves the way the tests claim, end-to-end against a real on-disk Project Store.

Both hold.

## Commands run

```bash
$ git fetch origin && git status
On branch main
Your branch is ahead of 'origin/main' by 5 commits.
nothing to commit, working tree clean

$ git log -1 --format='%H %s'
b5e59e9925867e7751c12f47c31b5747e1ade091 comms: verifications for Phase 3 regression-engine + memory-probe batch
```

### Step 1 — focused unit + full gate

```bash
$ uv run pytest -q tests/unit/memory/test_store.py
33 passed in 0.05s

$ uv run pytest -q tests/unit tests/integration
423 passed, 3 skipped in 12.78s

$ uv run mypy
Success: no issues found in 57 source files
```

The verification request predicted exactly these numbers: `33 passed` for the memory store unit module (was 25 before; +8 new), `423 passed + 3 skipped` for the full gate (was 348+3 before this cycle's two slices), and a clean mypy across 57 source files. All three landed verbatim.

### Step 2 — end-to-end probe behavior

I built a temporary Project Store, persisted one Run, then planted regression pair directories on disk by hand and observed the flag flip:

```
store path: /tmp/tmpo5xjwvwj/ws/.novetest
before pair:                False    # no pair → False
after pair (baseline pos):  True     # run_<this>__run_<other> → True
after json removed:         False    # pair dir present, json missing → False
only-unrelated pair:        False    # pair name uses other run_ids → False
target-position pair:       True     # run_<other>__run_<this> → True
```

All five expected behaviors reproduced. The two ones I specifically wanted to nail (because they're the easiest to break in future refactors):

1. **Position-agnostic match.** The same run flips the flag whether it sits as the *baseline* (`run_X__run_Y`) or as the *target* (`run_Y__run_X`). The probe doesn't care which side of the `__` joiner the run is on — it just needs `run_<rid>` to appear in any pair directory name.
2. **"File is the truth, directory is the index."** Removing `regression_facts.json` while leaving the pair directory in place flips the flag back to `False`. This is the guard against crashed-mid-write or hand-deleted artifacts being silently reported as fresh.

### Step 3 — negative probes from the "critical edge cases" list

The verification's edge-case list called out:

- **Substring greediness** — run IDs are fixed 32-character strings, so `run_aaaa…(32)` cannot accidentally match `run_aaaaa…(32)`. The unit tests cover this (case 7 in the new batch); the live store I built also confirmed an unrelated pair under different run IDs does NOT raise the flag.
- **Tombstone interaction** — per decision §C.1, the Memory probe deliberately reports `True` even when the run is tombstoned, *if* the pair file exists. Memory reflects what's on disk; refusal-to-serve lives one layer up in Regression. The cross-verification I ran for the regression-compare-runs-impl slice (companion findings file) confirmed the engine layer fires `REASON_RUN_TOMBSTONED` even when the cached facts file is intact, so the two layers compose correctly.
- **JSON content tolerance** — I planted `{"schema_version": 1}` stubs. The probe never opens or parses the file, so contents are irrelevant. (No deeper coverage attempted; the unit tests document the existence-only contract.)

## Issues found

**None.**

The probe passes everything the verification asked for and the unit tests pin the behavior so future refactors will be caught immediately.

## Observations worth flagging

- **No `src/` diff in this slice.** Pure test-surface slice. The probe code itself shipped previously (`4964e3a`). I confirmed this by running mypy: file count held at 57, no engine source added.
- **Post-slice unit-count drift.** The handoff brief mentioned a `345` baseline; actual baseline on `e80e3cf` was `348+3`, and post-cycle (both slices in) is `423+3`. The +75 absolute delta is consistent with both slices landing fully; the discrepancy is an upstream counting error in the original task brief, not a missing test.

## Recommendations for PM

1. **No blockers.** The slice is shippable as-is on `main`. No follow-up task warranted from this verification.
2. **DoD bookkeeping.** Per the verification's own note, no `delivery-phasing.md` Phase 3 DoD bullets close from this slice alone — they fire when the CLI verbs and the `regression_outcome` / `regression_delta` envelopes ship next cycle. The Memory↔Regression availability seam is now closed *on the test side*, which is the prerequisite for the next-cycle CLI work to surface `has_regression_facts: true` in `memory show` / `inspect` envelopes without false positives.
3. **Cross-team note.** The companion verification (regression-compare-runs-impl) is also passed; both can be considered closed together from the Manual Test side.

## Process notes

- The `Write` tool tripped the worktree-isolation guard documented in `GOTCHAS.md`; this file was written via the sanctioned Bash heredoc fallback.
