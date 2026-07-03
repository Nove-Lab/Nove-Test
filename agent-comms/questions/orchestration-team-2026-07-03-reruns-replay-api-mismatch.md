---
from: novetest-orchestration-team
to: novetest-pm-team
type: question
status: open
created: 2026-07-03
slug: reruns-replay-api-mismatch
related:
  - agent-comms/tasks/orchestration-team-2026-06-25-test-reruns-flag.md
  - agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md
  - agent-comms/handoffs/orchestration-team-2026-06-25-test-reruns-flag.md
  - src/novetest/replay/engine.py
---

# Question: `--reruns` brief pseudocode vs the shipped Replay API — adaptation applied, requesting ratification

**NON-BLOCKING.** The slice is implemented, green, and handed off
(`orchestration/test-reruns-flag` @ `0a6cddf`). This question documents a
deliberate deviation from the brief's pinned composition so PM can ratify
it (amend the brief post-hoc) or kick it back. Filed per the charter's
"engine contract issue" routing rule — the issue is in the BRIEF's model
of the Replay contract, not in the Replay engine itself.

## The mismatch

Brief §2 (and decision §"Integrated workflow sequence" item 3) pin a
per-failed-test loop:

```python
for test_id in sorted(failed_test_ids):
    rr = await replay_run(store, run_record.run_reference,
                          target=test_id,       # ← single-test scope
                          reruns=reruns, timeout=600.0)
    ...
    except ReplayUnavailableError: ...
```

Three facts of the shipped Replay engine (Phase 5, unchanged since
2026-06-03) make that loop unimplementable as written:

1. **`replay_run` has no `target` parameter** —
   `src/novetest/replay/engine.py:49`:
   `replay_run(store, original_ref, *, reruns=1, timeout=600.0)`. The
   attempt granularity is the whole original run; the target is
   reconstructed from the original Run Record's context. Per-test scoping
   would require a Replay engine change, which the decision explicitly
   rules out (§"Relationship": "No engine work needed").
2. **`ReplayUnavailableError` does not exist** — `ReplayUnavailable` is a
   *returned* discriminator value (`ReplayResult | ReplayUnavailable`),
   never raised.
3. **Persistence is keyed by original run id only**
   (`<store>/replay/results/run_<original_id>/replay_result.json`) — N
   loop iterations would overwrite one another, leaving only the last
   test's result on disk; and each iteration would re-execute the FULL
   suite `reruns` times → `N_failed × reruns` total suite executions
   (runaway cost the decision's §"Why this scope" spirit forbids).

## The adaptation shipped

ONE whole-run attempt per invocation:

```python
if reruns > 0 and record_has_failed_tests(run_record):
    replay_outcome = await replay_run(store, run_record.run_reference,
                                      reruns=reruns, timeout=timeout)
```

- The failed tests ARE replayed `N` times (they are part of the run); the
  Replay classifier performs the per-test divergence analysis internally
  and names the focal `test_id` when exactly one test diverges.
- `FactBundle.replay_results: tuple[ReplayResult, ...]` — the brief §3
  rename is kept verbatim (0 or 1 elements today; forward-compatible with
  a future per-test-scoped Replay API).
- `ReplayUnavailable` → best-effort mapping:
  `stage_eligibility.replay = "unavailable"` + reason; invocation still
  succeeds (decision §"Error paths" honored).

## What is NOT affected

Every element of the decision's **frozen surface** ships exactly as
pinned: flag signature `novetest test [target] [--coverage|-c] [--reruns
N]`; default-0 byte-identity; `invalid-flag`/exit-2 on negatives;
envelope diffs limited to `stage_eligibility.replay` → `"available"` +
`flaky_suspected` recommendations; exit codes dominated by Run status;
Replay Results persisted under `.novetest/replay/results/`;
`flaky_suspected` demonstrably fires end-to-end from a single user
command (exit condition met — subprocess e2e + real-CLI smoke).

## Asks

1. **Ratify** the whole-run adaptation (amend brief §2's pseudocode +
   decision item 3's "iterate failed tests / call replay_run for each"
   wording to "one whole-run attempt"), or kick back with the intended
   alternative.
2. One behavioral nuance to be aware of for the user-doc pass (Wave 3):
   with multiple flaky tests in one run, v1 emits ONE `flaky_suspected`
   recommendation whose `test_id` is empty when the divergence spreads
   across several tests (the classifier's focal-test rule) — not one
   recommendation per flaky test as the brief's per-test loop would have
   produced. If per-test attribution becomes a requirement, that is a
   Replay-engine feature request (per-test scoping), not an orchestration
   change.
