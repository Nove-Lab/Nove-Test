---
from: novetest-regression-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-07-03
slug: engine-scoped-baseline
related:
  - agent-comms/tasks/regression-team-2026-07-03-engine-scoped-baseline.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Handoff: Regression — engine-scoped baseline resolution (D5)

## ⚠ CROSS-TEAM FILES IN THIS WORKTREE (flagged per the task brief)

This slice edits **two Orchestration-owned source files** —
`src/novetest/orchestration/workflows/inspect.py` and
`src/novetest/orchestration/workflows/status.py` — plus **four
Orchestration-owned unit-test files** whose monkeypatch seams broke by
necessity (they stubbed `find_runs_for_target` in the inspect/status module
namespaces; the reroute removes those imports, so `monkeypatch.setattr`
would hard-fail with AttributeError). The source edits are PM-pre-authorized
in the task §2 ("PM pre-authorizes this cross-team edit as part of this
slice"); the test edits are the necessary companion. **Order any concurrent
Orchestration-team merge relative to this one accordingly** — in particular
the pending `orchestration-team-2026-07-03-anchored-init-and-verb-resolution`
task, if it lands in the same window, should be conflict-checked against
these six files.

Deliberately NOT touched (Orchestration territory, not in my pinned list):
`orchestration/workflows/test.py:290` — a third engine-blind bypass site
discovered during the §4 audit; reported in the question file instead.

## Worktree

- **Path:** `/home/yjshin/dev/aispace/novetest-regression-engine-scoped-baseline`
- **Branch:** `regression-team/engine-scoped-baseline`
- **Base:** `5e7d5b5` (main tip at slice start)
- **Commits:** `8885fca` (code + tests + docs + WORKLOG), plus one comms
  commit (this handoff + audit question + INDEX regen)

## What landed

**Rule (D5):** baseline/candidate selection for cross-run analyses filters
by the target run's `engine_name`. Mechanism: one shared selector, all
consumers route through it.

| File | Change |
|---|---|
| `src/novetest/regression/compare.py` | NEW public `resolve_baseline_for_run(store, memory_entry) -> RunReference \| None` — newest strictly-older live sibling, same `target_expression` AND same `engine_name`; the D5 filter lives here and nowhere else. `resolve_latest_baseline` rerouted through it: target = newest live run on the expression (engine-agnostic, unchanged); baseline = newest older same-engine run. Superseded "comparability is not narrowed here" docstring paragraph replaced per task §1. |
| `src/novetest/regression/retrieval.py` | `check_regression_availability` gains the same engine filter (scope addition — see below). |
| `src/novetest/regression/__init__.py` | Exports `resolve_baseline_for_run` (package-path import, matching Regression's existing re-export convention). |
| `src/novetest/orchestration/workflows/inspect.py` | `_resolve_inspect_regression` composes `resolve_baseline_for_run` + `compare_runs`; local sibling filter deleted; `find_runs_for_target` import removed. Unavailable shape unchanged (reason/detail/refs identical to pre-D5 for the reachable-before cases). |
| `src/novetest/orchestration/workflows/status.py` | `_latest_regression_available` composes the shared selector + cache-only `get_regression_facts`; local filter deleted; import removed. status/inspect agreement now by construction (same selector). |
| `design/interace-contract/regression.md` | New `resolve_baseline_for_run` interface row; engine-scoped wording on `resolve_latest_baseline` / `check_regression_availability`; Notes pin D5, the detail convention, and ENGINE_MISMATCH-as-defense-in-depth. |
| `design/workflows/regression.md` | Sequence rows + notes updated for the new selector. |
| `WORKLOG.md` | Entry `2026-07-03 — anchored-pin D5 / regression engine-scoped baseline` (pasted below). |

**Behavior deltas an observer can see:**

1. Mixed series [pytest, cargo-test, pytest]: `regression latest` /
   `inspect` / `status` now resolve the pytest↔pytest pair (pre-D5:
   unavailable via the guaranteed-mismatch neighbor).
2. `inspect` of a run whose only same-target priors are cross-engine now
   surfaces `REASON_NO_COMPARABLE_BASELINE` — previously
   `REASON_ENGINE_MISMATCH`. The mismatch reason remains reachable via
   explicitly user-picked `regression compare <a> <b>` pairs
   (`compare_runs` guard untouched per task §3).
3. New `detail` convention on `REASON_NO_COMPARABLE_BASELINE` from
   `resolve_latest_baseline`: `"<target> (engine=<name>)"` **only** when
   older runs exist but none share the target's engine (a state
   unreachable pre-D5). The plain `detail=<target>` and `"no-runs"` forms
   are byte-identical to before — pure single-engine series emit exactly
   the pre-D5 payloads (the task's "pure series unchanged" snapshot is the
   untouched 7-case block in `test_baseline_resolution.py`, all green).
4. No new `REASON_*`, no `TRANSITION_CATEGORIES` change, no schema bump,
   no envelope-shape change (2026-05-28 freeze untouched) → no
   `decisions/` follow-up required by my charter's contract-change rule.
   `resolve_baseline_for_run` is a new **Internal** interface documented in
   the contract doc.

**Scope addition (flagging honestly):** the task's in-scope list did not
name `check_regression_availability`, but leaving it engine-blind would
have it answer "available" for comparisons `compare_runs` is guaranteed to
refuse — the exact noise class D5 kills — and its docstring's "engine
checks deferred to compare_runs" rationale was superseded by the decision
text ("any cross-run analysis"). Zero production callers today (grep:
only a docstring mention in `localization/retrieval.py`), file is
Regression-owned, +2 tests pin it. Revert is one hunk if PM disagrees.

## Tests

- `tests/unit/regression/test_baseline_resolution.py` (+9): mixed-engine
  acceptance case ([pytest, cargo-test, pytest] → same-engine pair),
  engine-agnostic target selection with engine-suffixed detail,
  single-run-per-engine unavailable, 3 direct selector cases (skip
  newer+cross-engine / only-cross-engine → None / tombstoned same-engine
  prior skipped), mixed-engine `derive_latest_regression` produces facts
  (`fixed == 1`), 2 availability engine cases.
- `tests/integration/regression/test_engine_scoped_baseline_e2e.py` (NEW,
  3 tests): real store, real selector, real workflows — `derive_latest`,
  `build_inspect_view`, `build_status_view` (unavailable-before /
  available-after pair-cache derivation) against the canonical mixed
  store.
- Orchestration unit re-seams: `test_inspect_regression.py` (seam swap
  `siblings=` → `baseline_ref=`; `test_engine_mismatch_between_inspected_
  and_prior_propagated` REWRITTEN as `test_cross_engine_prior_surfaces_
  no_comparable_baseline` because it pinned the D5-retired behavior; +2
  new composition pins), `test_status.py` (same swap + selector call-log +
  1 new pin), `test_inspect.py` / `test_inspect_localization.py`
  (mechanical stub swaps, selector → None).

## Verification result (all `env -u PYTHONPATH`, in the worktree)

- `uv run mypy` (exact CI gate: strict via `[tool.mypy]`) → **Success, 114
  source files**. (Test-tree `mypy --strict` shows 18 errors — confirmed
  byte-identical on unmodified main; outside the CI gate; not introduced
  here.)
- `uv run pytest -q tests/unit/regression tests/integration/regression
  tests/unit/orchestration/workflows` → **153 passed**.
- `uv run pytest -q tests/unit tests/integration` → **1362 passed, 3
  skipped, 0 failed; 44 snapshots passed** (3 skips = pre-existing
  jest/Node host issue per the 2026-06-25 WORKLOG entry).

## §4 audit result (task deliverable — report only, full detail in the question file)

`questions/regression-team-2026-07-03-d5-cross-run-audit.md`:

- **Coverage — genuine corruption path:** `compare_coverage_facts` has no
  engine guard (`coverage/compare.py:182-243`); `coverage diff` /
  `compare` CLI verbs (`cli/app.py:663,788`) feed it user-supplied pairs
  resolved by `run_id` only → a pytest×cargo diff silently emits a
  meaningless `CoverageDelta`. Recommended priority fix (Coverage team).
- **Localization — noise:** `try_get_latest_regression_facts`
  (`derive.py:670-729`) replicates the engine-blind sibling selection; in
  mixed stores it now misses the same-engine pair cache my slice makes
  derivable, silently dropping the FLUCCS reweighting. All three SBFL
  modes otherwise strictly single-run.
- **Orchestration — third bypass site:**
  `test.py:290 build_test_outcome_from_run_id` — same pattern, cache-only,
  one-line fix via the shared selector once PM authorizes.
- `orchestration/workflows/test.py:191` (run-workflow step 5) needs no
  edit — it calls `resolve_latest_baseline` and inherits the fix.

## Worklog entry text

(as committed in `8885fca`; see `WORKLOG.md` top entry
`## 2026-07-03 — anchored-pin D5 / regression engine-scoped baseline` —
reproduced verbatim there; not duplicated here to avoid drift.)

## DoD bullets believed closed

**None.** The only unchecked bullets in
`design/implementation-plan/delivery-phasing.md` are the two MCP items
(lines 276-277), untouched by this slice. (D5 is a decision-implementation
slice; the decision itself already resolved Open Q #17 bookkeeping.)

## Open items / surprises

1. **Audit question filed** (non-blocking) — routing for the 3 external
   engine-blind sites, above.
2. **Stale CLI test docstring, not fixed (Orchestration-owned):**
   `tests/unit/cli/test_regression_latest.py::test_regression_latest_
   propagates_engine_mismatch` stubs `derive_latest_regression` returning
   `REASON_ENGINE_MISMATCH` — post-D5 that outcome is unreachable from
   `derive_latest_regression` (the resolver guarantees a same-engine
   pair). The test still passes (pure projection pin) and the shape it
   pins remains valid for `regression compare`; docstring is now
   historically framed. Left for Orchestration's next touch.
3. **Karpathy skill mandate:** no Skill tool in this session's toolset
   (same as the 2026-06-08 session) — could not invoke
   `andrej-karpathy-skills:karpathy-guidelines`; principles applied
   manually.
4. **`PYTHONPATH` leak** on this host (ROS2/3.10 profile export) breaks
   any bare `uv run` via a numpy C-ext crash; every verification above ran
   with `env -u PYTHONPATH`. GOTCHAS.md entry proposed in the question
   file (PM owns GOTCHAS per the 2026-05-16 policy).
5. **Double history scan note:** `resolve_latest_baseline` now walks
   `find_runs_for_target` twice (its own call + the selector's). Accepted
   deliberately — keeps the D5 filter in exactly one function; run
   histories are file-per-run JSON reads and small at current scale. Flag
   for `performance-engineer` only if store sizes grow past Phase 5.

## Suggested Manual Test scenarios

1. Mixed-engine store (real pytest fixture run + `--engine`-overridden or
   hand-seeded cargo-test run + second pytest run): `novetest regression
   latest` → `kind: fact-set` pairing the two pytest runs; `novetest
   inspect <newest>` regression section agrees; `novetest status` flips
   regression to `available` after the compare.
2. Two-run store, one engine each: `regression latest` →
   `kind: unavailable`, `reason: no-comparable-baseline`,
   `detail: "<target> (engine=<newest engine>)"`.
3. Pure single-engine store regression flows → byte-identical envelopes to
   the pre-D5 baseline (no drift).
