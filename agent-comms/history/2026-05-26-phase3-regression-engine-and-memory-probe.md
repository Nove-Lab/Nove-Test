---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-26
slug: phase3-regression-engine-and-memory-probe
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/history/2026-05-26-phase3-entry.md
  - agent-comms/history/2026-05-25-duplicate-merge-cycle.md
---

# History: Phase 3 Regression engine + Memory probe — cycle closed clean

Second Phase 3 cycle. Foundational Regression engine (`compare_runs`,
persistence, `RegressionUnavailable` + 6 reasons, `get_regression_facts`)
landed on disk, and Memory's `has_regression_facts` probe was pinned
with 8 dedicated tests. Both slices passed Manual Test + 9-cell CI on
first push. No DoD bullets closed (CLI verbs are next cycle).

## Cycle summary

| Slice | Commit | Manual Test | CI |
|---|---|---|---|
| Memory: `has_regression_facts` probe pinning | `2de7bea` | passed | 9/9 + perf green |
| Regression: `compare_runs` engine | `9c79792` | passed | 9/9 + perf green |

Final post-merge test gate: **423 passed + 3 skipped** (baseline 348+3,
+75 across the two slices). mypy clean, 57 source files (+5 for the
regression engine).

## What closed

- **Nothing on `delivery-phasing.md`.** Both handoffs and findings
  explicitly say so. Phase 3 DoD bullets fire when CLI verbs ship
  (`novetest regression compare/latest`, `novetest compare`, `inspect`
  Regression section) — that is the next cycle's work.
- **`agent-comms/decisions/2026-05-26-regression-facts-json-layout.md`**
  (614 lines, committed the same morning) was implemented verbatim:
  14 top-level keys, 11 summary keys, 9 per-transition keys, 9-element
  closed `TRANSITION_CATEGORIES`, 6 `REASON_*` constants, pair-keyed
  order-significant directory layout (`run_<a>__run_<b>__`). All 7
  C-section resolutions are now demonstrable behavior on disk.

## Load-bearing learnings

### 1. Decision §C.1 (tombstone fail-hard) overrides a stale cache live

Manual Test ran the canonical scenario end-to-end: `compare_runs(A, B)`
on healthy runs (writes `regression_facts.json` to disk), then
`delete_run_evidence(store, B.run_reference)` (tombstones B), then
`compare_runs(A, B)` again — got `RegressionUnavailable(reason="run-tombstoned")`
**even though the cached facts file is still on disk and intact**. This
is the live demonstration that **Memory reflects what's on disk; the
Regression engine layer is the authoritative gate against stale data**.

**Why this matters for Phase 4+:** Localization will consume
`get_regression_facts` to focus on changed behavior. If Localization
calls `get_regression_facts` directly on a pair where the target has
since been tombstoned, **it will get the stale cached facts back** —
because the retrieval seam is a pure cache read (see learning #3
below). Localization MUST go through `compare_runs` for any
freshness-sensitive query, or check the Memory entry's tombstoned-state
before trusting `get_regression_facts` output.

### 2. Unknown-outcome default bucket = fail-like (implicit, not pinned)

Decision §5 constraint #2 says unknown outcome strings "fall into the
closest bucket defensively" but does NOT pin **which** bucket the
default is. The Regression engine's implementation defaults to
**fail-like** — Manual Test verified this with a `weird-status` baseline
going to `passed`, which classified as `fixed` (not `still_passing`).

Rationale (inferred from the implementation): a fail-like default
guarantees unknown outcomes show up in attention-grabbing categories
(`regressed`, `still_failing`, `fixed`) where humans/Localization will
notice them, rather than getting absorbed silently into `still_passing`
where they would be invisible signal.

The `warnings` array already surfaces `unknown-outcome:<engine>:<raw>`
(deduplicated per `(engine, raw)` pair), so consumers DO have a signal
to escalate. **This is a sensible default, but it is undocumented as a
default.** Two follow-up options for a future cycle (low priority,
non-blocking):

- (a) Add a one-line footnote to decision §5 constraint #2 pinning
  fail-like as the default bucket.
- (b) Have the Regression team add the same line to
  `design/interace-contract/regression.md` next time they edit it.

Either works; (a) is PM territory and zero-overhead.

### 3. `get_regression_facts` is a PURE cache read — Memory resolution lives at `compare_runs`

Deliberate design deviation from Coverage's `get_coverage_facts` (which
DOES resolve Memory inside the retrieval seam):

- `get_regression_facts(store, baseline_run_id, target_run_id)` —
  reads `<store>/regression/pairs/run_<a>__run_<b>/regression_facts.json`
  and returns either `RegressionFactSet` (via `from_dict`) or
  `RegressionUnavailable(REASON_MISSING_DERIVED_FACTS)`. **No Memory
  call. No tombstone check. No engine-name validation.**
- `compare_runs(store, baseline_ref, target_ref)` — does Memory
  resolution, tombstone validation, engine-name match, target-expression
  match, and ONLY THEN consults the cache via `get_regression_facts` or
  derives via `derive_regression_facts`. **This is the layer that
  enforces freshness and validity.**

**Why this matters for Phase 4 + next-cycle CLI work:** any caller that
wants live freshness MUST go through `compare_runs`. Calling
`get_regression_facts` directly is correct only when the caller has
already done its own freshness/validity check (e.g. a `regression latest`
verb that first calls `resolve_latest_baseline` to get a known-fresh
pair, then uses `get_regression_facts` for the read).

The asymmetry with Coverage is intentional but a **trap for next-cycle
CLI implementers** who'd assume symmetry. The next cycle's CLI tasks
must explicitly state which retrieval path each verb uses, and the
`inspect` slice in particular needs to call `compare_runs` (not
`get_regression_facts`) for the Regression section to honor tombstones.

PM may want to recommend a CLI-wiring-time architectural-consistency
review when the CLI tasks are dispatched, to confirm this asymmetry is
the right long-term shape (vs unifying both engines on one of the two
patterns).

### 4. Manual-Test-before-push is sequencing-safe (correctness-wise), but push-before-Manual-Test is the recommended ORDER

CEO dispatched Manual Test before pushing the merge batch. **This
worked correctly** — Manual Test ran in the shared checkout at the
post-merge tip (`b5e59e9`), verified merged code, no surprises.

Push happened in parallel with Manual Test's work; CI cleared all 9
cells + perf in ~10 min. Both signals landed cleanly.

**Sequencing rule for future cycles:**
- Manual-Test-before-push is **correctness-safe** (Manual Test reads
  the shared checkout, which is the post-merge tip regardless of push
  state).
- Push-before-Manual-Test is **recommended** (CI signal starts earlier,
  parallel with Manual Test's exploratory work; cycle wall-clock is
  shorter).
- The 2026-05-25 duplicate-merge incident's "push before next-cycle
  planning" rule is the ONE non-negotiable. Manual Test sequencing is
  a wall-clock optimization, not a correctness gate.

If Manual Test ever pulls from origin (instead of using the shared
checkout's local `main`), the calculus changes — but the standard
verification scripts in `verifications/` use `git -C <shared-path>
fetch + checkout main`, which is safe regardless of push state.

### 5. Decision-before-impl pattern: contract-clarification questions during impl = 0

The Regression engine slice landed against the 614-line
`decisions/2026-05-26-regression-facts-json-layout.md` that was
committed ~4 hours before the impl slice was dispatched. The
implementing team raised **zero** contract-clarification questions
during the slice — they cited specific decision sections in the handoff
and implemented to those.

Contrast with Coverage's "ship-then-freeze" pattern (envelope shapes
post-Manual-Test): both patterns work, but for **different surfaces**.

- **Decision-before-impl** is right for **cross-engine on-disk shapes**
  — multiple consumers (Memory's probe, Localization in Phase 4,
  Orchestration's `inspect` wiring) need to agree on field names before
  any code is written. Pre-locking removes a coordination round.
- **Ship-then-freeze** is right for **CLI envelope shapes** — only one
  consumer (the user / AI agent reading the envelope), and Manual Test
  is the cheapest first audience. Pre-locking adds friction without
  catching anything Manual Test wouldn't catch.

This is a useful PM heuristic going forward: if the contract has ≥2
internal consumers, decision-before-impl; if 1 external consumer,
ship-then-freeze.

### 6. First push of a new sub-product engine cleared all 9 CI cells (clean Windows)

Regression is the third sub-product engine (after Memory, Coverage)
and **the first to clear all 9 CI cells + perf lane on first push** —
including the historically tricky `windows-latest` × Python 3.11/3.12/3.13
cells. No charmap warnings, no platform-specific failures, no flaky
tests.

The accumulated Coverage-era conventions paid off:
- Coverage's `parser.py` / `persistence.py` / `retrieval.py` /
  `results.py` shape directly transplanted to Regression's tree.
- Coverage's `_run_in_text_mode_with_utf8` discipline (history
  `2026-05-21-phase2-3-inspect-and-jest-coverage.md`) was already on
  every subprocess seam Regression's tests touch.
- The `_FACT_PATH_FOR_RUN` style helpers from Coverage's persistence
  module are pattern-matched into Regression's `regression_facts_path`.

**Implication:** the 4th sub-product engine (Localization at Phase 4)
can expect a similar smoothness if it continues to clone Coverage's
module shape line-for-line.

## Open follow-ups (PM-tracked, deferred)

1. **Document fail-like as the unknown-outcome default bucket** (per
   learning #2). One-line footnote to decision §5 constraint #2, or a
   parallel one-line edit to `design/interace-contract/regression.md`.
   Defer to a future PM bookkeeping cycle; not urgent.
2. **CLI-wiring-time architectural-consistency review of
   `get_regression_facts` vs `get_coverage_facts` symmetry** (per
   learning #3). Recommend including in the next-cycle CLI task brief
   for Orchestration team — they should explicitly choose retrieval
   path per verb and confirm `inspect` goes through `compare_runs` (not
   the bare cache reader) for Regression section composition.
3. **Phase 3 CLI verbs + `inspect` wiring** — actual Phase 3 DoD work.
   Three CLI surfaces (`regression compare`, `regression latest`,
   `compare`) + `inspect` Regression section + Orchestration-level
   `resolve_latest_baseline` / `derive_latest_regression` /
   `check_regression_availability`. Next cycle's primary workload.
   Per decision §C.2, the `regression_outcome` / `regression_delta`
   envelope decisions land AFTER the CLI slice's Manual Test pass.
4. **`@v8.1.0` astral-sh/setup-uv immutable pin** (carried from
   `history/2026-05-25-duplicate-merge-cycle.md` follow-ups) — still
   not urgent; will roll into a future Release housekeeping cycle.
5. **Defensive-parsing audit / floor-version CI lane / readiness-probe
   enhancement** (carried from
   `decisions/2026-05-25-supported-engine-matrix.md` future-cycle
   candidates) — pick up after CLI verbs ship.

## Process notes

- Cycle ran cleanly — 2 slices, both green on first push, both passed
  Manual Test with verdict `passed` and "Issues found: None."
- PM-side cleanup (this entry + transient deletes + INDEX regen +
  commit) wraps the cycle. Five `agent-comms/` channels remain at zero
  in-flight after this commit.
- The "Manual Test before push" sequence-of-events is recorded as a
  process-safe pattern (learning #4), not a recurring incident — the
  pre-flight rule from 2026-05-25 stays as the load-bearing constraint.
