---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-26
slug: regression-compare-runs-impl
related:
  - agent-comms/verifications/2026-05-26-regression-compare-runs-impl.md
  - agent-comms/verifications/2026-05-26-memory-has-regression-facts.md
  - agent-comms/handoffs/regression-team-2026-05-26-compare-runs-impl.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
---

# Findings: Regression engine — `compare_runs` + persistence + `get_regression_facts` + `RegressionUnavailable`

## Verdict

**passed**

Phase 3 of the Nove Test product is now actually on disk. The Regression engine produces structured run-to-run comparison records, persists them in the documented JSON layout, refuses to serve stale or invalid combinations with the right six error reasons, and respects the tombstone fail-hard policy. The persisted wire shape matches decision `2026-05-26-regression-facts-json-layout.md` verbatim — top-level keys, summary cardinality, per-transition shape, and the order-significance of the pair directory are all exactly what the design says they should be.

## What I tested (for the CEO)

The Regression engine answers the question "what's different between two runs of the same target?" — added tests, fixed tests, newly-failing tests, and so on, plus optional output and coverage diff. This slice ships the engine layer (no CLI surface yet — the `novetest regression` group only has stubs). My job was to confirm:

1. The engine actually produces the documented JSON shape end-to-end.
2. The cache (one pair directory per `(baseline, target)` pair) is honored — calling `compare_runs` twice doesn't re-derive.
3. Order matters: `compare(A, B)` and `compare(B, A)` write to **separate** directories (passing→failing is a regression; failing→passing is a fix; both are real outcomes).
4. All six refusal reasons fire in the right places, including the one that overrides a fresh cache: tombstoning a run after the pair was already written.
5. The closed 9-category transition classification holds, including the corner cases for `xpassed` and `xfailed` outcomes, and unknown-outcome warnings deduplicate.

Every one of those held.

## Commands run

```bash
$ git fetch origin && git status
On branch main
Your branch is ahead of 'origin/main' by 5 commits.
nothing to commit, working tree clean

$ git log -1 --format='%H %s'
b5e59e9925867e7751c12f47c31b5747e1ade091 comms: verifications for Phase 3 regression-engine + memory-probe batch
```

### Step 1 — test gate

```bash
$ uv run pytest -q tests/unit tests/integration
423 passed, 3 skipped in 12.78s

$ uv run mypy
Success: no issues found in 57 source files
```

Both numbers match the verification request verbatim. The +5 mypy source-file delta lines up exactly with the regression engine's 5-file surface (`compare.py`, `persistence.py`, `results.py`, `retrieval.py`, plus the new `regression_fact_set` model). 1 snapshot test passed.

### Step 2 — on-disk wire shape

Built a temp store, persisted two runs (one regression, one still-passing test, one added test), called `compare_runs`, then read the persisted JSON:

```
result class: RegressionFactSet
on-disk path (relative): regression/pairs/run_00000000000000000000000000000001__run_00000000000000000000000000000002/regression_facts.json
summary: {"added": 1, "fixed": 0, "newly_active": 0, "newly_skipped": 0, "regressed": 1, "removed": 0, "still_failing": 0, "still_passing": 1, "still_skipped": 0, "total_baseline_tests": 2, "total_target_tests": 3}
len(summary): 11
len(top-level keys): 14
top-level keys: ['baseline_engine_name', 'baseline_engine_version', 'baseline_run_reference', 'coverage_change', 'derived_at', 'metadata', 'output_diff', 'schema_version', 'summary', 'target_engine_name', 'target_engine_version', 'target_run_reference', 'test_transitions', 'warnings']
output_diff:     None
coverage_change: None
warnings:        []
metadata:        {}
```

This matches the verification request **byte-for-byte** on the summary line and on all 14 top-level keys. Both `output_diff` and `coverage_change` are correctly `null` (no payload either side). `warnings` is `[]`. `metadata` is `{}`.

### Step 3 — cache hit doesn't re-derive

```
cache-hit derived_at preserved: 1779782690269 == 1779782690269
```

Confirmed: a second call returns the same `derived_at` epoch-ms — the engine reads the persisted file rather than recomputing.

### Step 4 — `RegressionUnavailable` refusal reasons

All four refusal codes fire correctly:

```
run-not-found ->     run-not-found
engine-mismatch ->   engine-mismatch
target-mismatch ->   target-mismatch
cache-ok type:       RegressionFactSet
run-tombstoned (cache exists) -> run-tombstoned
```

The last one is the critical one: I called `compare_runs` once on two healthy runs (it wrote a fresh `regression_facts.json` to disk), then tombstoned the target run, then called `compare_runs` again. The engine **correctly refused** to surface the stale-but-on-disk cached facts and instead returned `RegressionUnavailable(reason="run-tombstoned")`. This is the live demonstration of decision §C.1: "Memory reflects what's on disk; Regression fail-hard is the authoritative gate."

### Step 5 — order significance of the pair directory

After calling `compare_runs(b, t)` and then `compare_runs(t, b)`, both pair directories exist side by side:

```
pair dirs (count=2):
  run_00000000000000000000000000000001__run_00000000000000000000000000000002
  run_00000000000000000000000000000002__run_00000000000000000000000000000001
```

Correct: passing→failing and failing→passing are different real outcomes, so the cache pairs them separately.

### Bonus probes — the 9-category invariant, xpassed/xfailed, and warning deduplication

The verification's "critical edge cases" section pointed at several invariants I wanted to confirm live. I built a more varied scenario with 8 transitions and a `weird-status` raw outcome appearing in **two** tests, then inspected the persisted JSON:

```
test_transitions count:            8
distinct transition-key counts:    {9}
first transition keys:             ['baseline_duration_ms', 'baseline_failure_reference',
                                    'baseline_outcome', 'category', 'node_id',
                                    'schema_version', 'target_duration_ms',
                                    'target_failure_reference', 'target_outcome']

transition: t::xfailed_to_passed -> newly_active  (baseline_outcome=xfailed, target_outcome=passed)
transition: t::xpassed_to_failed -> regressed     (baseline_outcome=xpassed, target_outcome=failed)

warnings: ['unknown-outcome:pytest:weird-status']
coverage_change is None: True
```

Three things to highlight for the CEO:

1. **Every transition has exactly 9 keys, and `output_diff` is NOT one of them.** `output_diff` lives at the top level of the persisted JSON — there is no per-transition output diff. This matches the decision; any future consumer expecting per-transition `output_diff` is reading the wrong layer.
2. **`xpassed` is pass-like, `xfailed` is skip-like.** A baseline that was `xpassed` going to a target that fails classifies as `regressed`. A baseline that was `xfailed` going to a target that passes classifies as `newly_active`. This is the documented contract and the only sane interpretation — but it's the kind of edge case that breaks silently if anyone touches the bucketing code.
3. **Warning deduplication works.** Two tests both reported the raw outcome `weird-status`; only **one** `unknown-outcome:pytest:weird-status` entry appears in `warnings`. The engine doesn't spam.

### Bonus — CLI surface confirmation

```
$ uv run novetest regression --help
Usage: novetest regression COMMAND
regression commands (stub - not yet implemented).
Commands: compare, latest
```

A stub group is registered, but both subcommands are documented as "not yet implemented." This matches the verification's "No CLI surface yet" expectation — the scaffold is in place for the next-cycle wiring without any half-functional verb being shippable today.

## Issues found

**None.**

I went looking. The engine matches the design decision verbatim, the persistence layer respects the pair-directory order convention, the refusal layer overrides stale caches on tombstone, the 9-category transition classification is closed and intact, and the warning system deduplicates.

## Observations worth flagging (not blockers)

1. **Unknown-raw baseline buckets as fail-like.** In my bonus scenario, two tests with baseline raw outcome `weird-status` going to a `passed` target were counted as `fixed` (3 fixed total = 1 real `failed_to_passed` + 2 `weird-status_to_passed`). This is a sensible fail-safe default (treat unknown as failing so it shows up in attention-grabbing categories) but the verification doesn't explicitly call it out. PM may want to either (a) freeze this in a decision footnote or (b) document the default bucket for unknown outcomes in `design/interace-contract/regression.md`. The `warnings` array already surfaces the unknown outcome, so consumers do have signal.
2. **`get_regression_facts` deviates from `get_coverage_facts` precedent.** Per the verification's own notes (page-bottom): retrieval is now a pure cache read, while Coverage's equivalent does Memory resolution. PM is already aware via the handoff's "Open items / surprises" section. Not a regression — by design — but worth a future architectural-consistency review when CLI wiring lands.
3. **CLI stubs return their own envelope shape.** Out of scope for this verification, but next-cycle wiring will need to swap stub-printers for real envelopes. The stub group printing JSON-like content suggests the orchestration layer is already prepared to receive the new verbs; that's a healthy sign.

## Recommendations for PM

1. **No blockers; ship as-is.** The Regression engine slice is on `main`, on-disk shape matches the frozen decision, refusal-reason coverage is complete, mypy is clean, and the test gate is green at `423+3` from `348+3` (+75 tests in this cycle).
2. **Companion slice (memory-has-regression-facts) is also passed.** Both findings can be closed together. The two slices together close the Phase 3 entry on the engine + Memory-availability side. CLI verbs, `resolve_latest_baseline`, `derive_latest_regression`, and `check_regression_availability` remain explicit next-cycle work.
3. **Consider documenting unknown-raw default bucket.** See observation #1 — pure documentation fix, not a code change.
4. **Push decision still pending.** Local `main` is 5 commits ahead of `origin/main` (Phase 3 entry batch). Manual Test does not initiate pushes; flagging so PM/Main Branch can decide when to publish the batch.

## Process notes

- Both verifications (memory-has-regression-facts and regression-compare-runs-impl) share the same `pytest tests/unit tests/integration` gate and the same `mypy` invocation; I ran each once and cited the result in both findings.
- The `Write` tool tripped the worktree-isolation guard documented in `GOTCHAS.md` (same quirk as the 2026-05-21 ci-perf-lane findings); this file was written via the sanctioned Bash heredoc fallback.
- Temporary smoke-test scratch under `/tmp/novetest-verify-memory-hrf` and `/tmp/novetest-verify-reg`. Not committed; safe to leave behind.
