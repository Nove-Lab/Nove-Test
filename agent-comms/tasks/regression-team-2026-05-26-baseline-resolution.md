---
from: novetest-pm-team
to: novetest-regression-team
type: task
status: pending
created: 2026-05-26
slug: baseline-resolution
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - design/interace-contract/regression.md
  - design/workflows/regression.md
  - design/implementation-plan/delivery-phasing.md
  - src/novetest/regression/compare.py
  - src/novetest/regression/results.py
  - src/novetest/memory/store.py
---

# Task: Regression engine — baseline resolution & availability (`resolve_latest_baseline` + `derive_latest_regression` + `check_regression_availability`)

## Why this task exists

Phase 3 / second engine slice. The foundational comparison surface (`compare_runs`, `derive_regression_facts`, `get_regression_facts`, `RegressionUnavailable` with 6 `REASON_*`, the on-disk `regression_facts.json` layout) shipped 2026-05-26 (commit `9c79792` + handoff). What remains on the **Regression engine surface** before any CLI work can begin is the three baseline-resolution / availability helpers: the seams the upcoming CLI cycle (`novetest regression latest`, `novetest compare`, `inspect` Regression section) will project onto envelopes.

This slice is intentionally engine-only — **no CLI verbs, no `inspect` wiring, no envelope shapes**. Those land in the follow-up cycle once Manual Test can exercise this engine surface end-to-end. Same engine-first → CLI-second → freeze cadence Coverage followed in Phase 2.

After this slice ships, the entire `design/interace-contract/regression.md` engine surface is implemented. The remaining Phase 3 DoD bullets (`regression latest`, `compare`, `inspect` Regression section) become a single follow-up cycle.

## Pre-flight reading (mandatory, in order)

1. **`git fetch && git status`** — confirm `Your branch is up to date with 'origin/main'` before opening a worktree. Refuse to start on stale state (per `agent-comms/history/2026-05-25-duplicate-merge-cycle.md`).
2. `CLAUDE.md` — coding guidelines (Karpathy skill is mandatory on every code edit).
3. `agent-comms/INDEX.md`.
4. `agent-comms/decisions/2026-05-26-regression-facts-json-layout.md` — the contract pinning `RegressionUnavailable` semantics and the `REASON_NO_COMPARABLE_BASELINE` reason this slice activates for the first time.
5. `.claude/agents/novetest-regression-team.md` — your charter.
6. `WORKLOG.md` top 3 entries — most recent context (the two `2026-05-26` entries describe the engine surface this slice extends).
7. `design/interace-contract/regression.md` — the three function signatures being implemented (rows 4, 5, 7 of the interfaces table).
8. `design/workflows/regression.md` — workflow composition: `derive_latest_regression` → `resolve_latest_baseline` → `compare_runs`; `check_regression_availability` → `find_runs_for_target`.
9. `src/novetest/regression/compare.py`, `src/novetest/regression/results.py`, `src/novetest/regression/retrieval.py` — the surface you're extending.
10. `src/novetest/memory/store.py` — read `find_runs_for_target`, `list_run_history`, `retrieve_run_evidence` (and the `RunEvidenceNotFoundError` exception) — the only Memory seams this slice consumes. **Do not modify** Memory.

## Scope (what this slice MUST land)

### Files to edit

**1. `src/novetest/regression/compare.py`** — add two functions alongside the existing `compare_runs` / `derive_regression_facts`:

```python
def resolve_latest_baseline(
    store: ProjectStore,
    target_expression: str,
) -> tuple[RunReference, RunReference] | RegressionUnavailable:
    """Resolve the (baseline, target) pair for the most recent comparable runs
    sharing ``target_expression``. Returns (baseline_run_reference,
    target_run_reference) — older first, newer second — so the result threads
    straight into ``compare_runs(store, baseline, target)``.

    Tombstoned runs are excluded (Memory's default). Fewer than 2 comparable
    runs → ``RegressionUnavailable(reason=REASON_NO_COMPARABLE_BASELINE,
    detail=target_expression)``.
    """
```

Implementation contract:
- Call `find_runs_for_target(store, target_expression, include_tombstoned=False)`.
- Memory guarantees newest-first ordering (see `src/novetest/memory/store.py:152`).
- `len(entries) < 2` → `RegressionUnavailable(reason=REASON_NO_COMPARABLE_BASELINE, baseline_run_reference=None, target_run_reference=None, detail=target_expression)`.
- Otherwise `entries[0]` is the latest (= target), `entries[1]` is the second-latest (= baseline). Return `(entries[1].run_record.run_reference, entries[0].run_record.run_reference)`.
- **Do not** call `compare_runs` here — pure pair-resolution only.
- **Do not** filter by `engine_name` or `target_type` — comparability checks live in `compare_runs` (engine-name mismatch → `REASON_ENGINE_MISMATCH`, target-type drift → warning per decision §C.3). This function trusts the Memory filter.

```python
def derive_latest_regression(
    store: ProjectStore,
) -> RegressionFactSet | RegressionUnavailable:
    """Compose ``resolve_latest_baseline`` + ``compare_runs`` against the
    current Run History. The "active target" is the ``target_expression`` of
    the most recent **non-tombstoned** run in the store.

    Empty store or all-tombstoned store →
    ``RegressionUnavailable(reason=REASON_NO_COMPARABLE_BASELINE,
    detail="no-runs")``.
    """
```

Implementation contract:
- Call `list_run_history(store)`. Filter out tombstoned entries (`entry.tombstoned_at is None`).
- Empty filtered list → `RegressionUnavailable(reason=REASON_NO_COMPARABLE_BASELINE, baseline_run_reference=None, target_run_reference=None, detail="no-runs")`.
- Take `filtered[0].run_record.target_expression` as the active target.
- Call `resolve_latest_baseline(store, active_target)`.
- If `RegressionUnavailable` → propagate (do not re-wrap).
- Else unpack `(baseline_ref, target_ref)` and call `compare_runs(store, baseline_ref, target_ref)`. Return the result as-is (either `RegressionFactSet` or `RegressionUnavailable` from compare_runs's own validation path).

**2. `src/novetest/regression/retrieval.py`** — add one function alongside the existing `get_regression_facts`:

```python
def check_regression_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Return True iff a comparable prior (non-tombstoned) run exists in the
    same Test Target as ``run_reference``. Used by Orchestration eligibility
    evaluation (Phase 6) and Localization (Phase 4).

    Unknown ``run_reference`` → False (missing-tolerant; eligibility
    evaluation treats absence as "not available", never an error).
    Tombstoned ``run_reference`` → still computes availability against its
    historical target (tombstone is a deletion gesture, not an opaque-id
    error).
    """
```

Implementation contract:
- Wrap `retrieve_run_evidence(store, run_reference)` in `try` / `except RunEvidenceNotFoundError` → `return False`.
- Get `entry.run_record.target_expression` from the resolved entry.
- Call `find_runs_for_target(store, target_expression, include_tombstoned=False)`.
- Filter out the input run itself by `run_id` match (the input run may or may not be in the result depending on tombstone state — explicit filter, do not assume).
- Return `len(filtered) >= 1`.

**Why a bool, not a typed result?** The internal contract row (`design/interace-contract/regression.md:31`) calls it an "Availability flag"; orchestration eligibility and Localization both want a yes/no read. A typed `RegressionUnavailable` here would be redundant — the only failure mode is "no comparable prior", which is the very meaning of `False`. This matches the bool/string-flag pattern Memory's `_availability_flags` uses.

**3. `src/novetest/regression/__init__.py`** — extend the public re-export to include the three new symbols:

```python
from .compare import (
    compare_runs,
    derive_regression_facts,
    resolve_latest_baseline,        # NEW
    derive_latest_regression,       # NEW
)
from .retrieval import (
    get_regression_facts,
    check_regression_availability,  # NEW
)
```

Keep the existing exports in place; this is additive only.

### Files to add (tests)

**4. `tests/unit/regression/test_baseline_resolution.py`** — covers all three new functions in a single module (cohesive cluster):

- **`resolve_latest_baseline`** (≥6 cases):
  - Empty store → `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE)` with `detail` carrying the target_expression.
  - Single matching run → `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE)`.
  - Exactly two matching runs in chronological insertion order → returns `(older.run_reference, newer.run_reference)`.
  - Two matching runs inserted in REVERSE chronological order (target's `created_at` earlier than baseline's `created_at`) → still returns the older-by-`created_at` first; assert Memory's newest-first guarantee is the load-bearing invariant.
  - Three matching runs → picks the two most recent (latest=target, 2nd-latest=baseline); the oldest is dropped.
  - Tombstoned baseline candidate excluded by default — e.g. three runs where the middle one is tombstoned → result is (oldest non-tombstoned, latest) — but make sure to set this up so the assertion is on what got picked, not just that tombstone is skipped.
  - Mixed targets — only the matching `target_expression` is considered; other targets ignored.

- **`derive_latest_regression`** (≥5 cases):
  - Empty store → `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE, detail="no-runs")`.
  - Single run → propagates `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE)` from `resolve_latest_baseline` (assert reason; the detail will be the target_expression at this layer — sanity-check that propagation does NOT overwrite it to `"no-runs"`).
  - All-tombstoned store → `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE, detail="no-runs")`.
  - Latest run is tombstoned but earlier runs share a comparable target → active target is taken from the latest **non-tombstoned** run; happy path comparison succeeds.
  - Happy path with two non-tombstoned runs sharing a target → returns a `RegressionFactSet` (not a `RegressionUnavailable`). Inspect at least one `TestTransition` to confirm compose actually fired.

- **`check_regression_availability`** (≥5 cases):
  - Unknown `run_reference` (random `run_id` not in store) → `False`.
  - Known run with no siblings on same target → `False`.
  - Known run with one comparable sibling → `True`.
  - Known run with siblings that are all tombstoned → `False` (siblings excluded by Memory's default).
  - Tombstoned input run with a live sibling on the same target → `True` (tombstone of the input is irrelevant; we measure whether a comparable prior exists).

Use the same `store_run_evidence` + `delete_run_evidence` public-seam pattern the find-runs-for-target tests established (`tests/unit/memory/test_store.py`, find-runs-for-target section). No mocking of Memory.

**5. `tests/integration/regression/test_baseline_resolution_e2e.py`** — 1–2 end-to-end cases against a real Project Store:

- Build three real `RunRecord`s via `store_run_evidence` — same target, real outcomes (one with a real regression introduced on the latest run). Call `derive_latest_regression(store)`. Assert: a `RegressionFactSet` lands on disk at `<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json`; the `summary` reflects the regression. Re-call → cache hit (the file's `derived_at` is preserved across calls).
- A second scenario where the latest run is tombstoned: assert `derive_latest_regression` skips it and produces a `RegressionFactSet` for the two next-most-recent live runs.

### Files to **NOT** touch

- **`src/novetest/memory/store.py`** — Memory's surface is exactly what you need. No new helpers, no signature changes. If you find yourself reaching for a new Memory function, stop and raise it as a `question` — almost certainly the existing seams compose to what you want.
- **`src/novetest/cli/app.py`**, **`src/novetest/orchestration/**`** — CLI verbs and `inspect` wiring are the NEXT cycle's territory. Do not touch.
- **`src/novetest/coverage/**`** — out of scope.
- **`design/interace-contract/regression.md`**, **`design/workflows/regression.md`** — the surface this slice implements is already pinned in those docs verbatim. No edits expected.
- **`pyproject.toml`** — no new dependencies.

## Frozen contracts (binding — do not relitigate)

- **Argument order:** `resolve_latest_baseline` returns `(baseline, target)` = `(older, newer)`. `compare_runs` consumes `(baseline, target)` positionally. Identical to Coverage's `(baseline, target)` convention. (Decision §C.4 + charter.)
- **`REASON_NO_COMPARABLE_BASELINE`** is the only reason this slice activates for the first time — no new `REASON_*` constants. If you find yourself wanting one, stop and write a question.
- **No new `warnings` codes.** The three already pinned (`engine-version-drift`, `target-type-drift`, `unknown-outcome:<engine>:<raw>`) cover everything in this scope. If you find a case that doesn't fit, stop and write a question.
- **Memory's `find_runs_for_target` ordering is load-bearing** (newest-first by `created_at` desc). `resolve_latest_baseline`'s correctness depends on it. Do not re-sort defensively in regression code.
- **Tombstone semantics:** Memory excludes tombstoned by default in `find_runs_for_target`; `derive_latest_regression` filters tombstoned from `list_run_history` to find the "active" target. Stale cached `regression_facts.json` for tombstoned pairs is Regression's concern (handled in `compare_runs` per decision §C.1); not relevant in this slice (cached-fact stale-detection is in `get_regression_facts`, not exercised here).

## Acceptance criteria

- `uv run pytest -q tests/unit tests/integration` → all green. Baseline at HEAD = `7e5b7a5` is **415 passed + 3 skipped** (the 3 skips are pre-existing Node-dependent jest integration tests). Aim for ≥16 new tests (~16 unit + 2 integration); the final count is whatever passes — don't pad.
- `uv run mypy` → clean, `--strict`. No new source files (you're extending two existing modules); mypy file count stays at 57.
- `src/novetest/regression/__init__.py` re-exports the three new symbols.
- No `delivery-phasing.md` Phase 3 DoD bullets close from this slice alone — this is engine surface completion. The follow-up CLI cycle closes all three remaining Phase 3 DoD bullets at once. PM verifies and does NOT tick on merge of this slice.

## Out of scope (do NOT include)

- `novetest regression compare` / `novetest regression latest` / `novetest compare` CLI verbs — follow-up cycle (Orchestration team).
- `inspect` Regression section wiring — follow-up cycle.
- `regression_outcome` / `regression_delta` envelope shape decisions — PM owns those, frozen AFTER the CLI slice has Manual Test fielding.
- Cargo / JUnit / dotnet adapters — Run team's Phase 3 closeout, dispatched separately.
- The OQ#20 marker-file index (`<store>/memory/by_target/`) — still deferred; `find_runs_for_target`'s O(N) file scan is acceptable at v1.
- Any change to Memory.

## Verification

- `git fetch && git status` clean on `main` before opening the worktree (per the duplicate-merge incident lesson).
- Karpathy skill invoked before each code edit (per `CLAUDE.md` Coding Guidelines).
- `uv run pytest -q tests/unit tests/integration` and `uv run mypy` both green before writing the handoff.
- Optional manual smoke: build a tmp Project Store with three runs sharing a target, call `derive_latest_regression(store)`, eyeball the returned `RegressionFactSet` and the on-disk `regression_facts.json` — they should match.

## Reporting back

Standard handoff at `agent-comms/handoffs/regression-team-2026-05-26-baseline-resolution.md`. Required sections per `agent-comms/README.md` + charter:

- **DoD bullets believed closed:** `none` — engine surface completion only; Phase 3 DoD closes on the follow-up CLI cycle.
- If you discover any ambiguity in the decision (`2026-05-26-regression-facts-json-layout.md`) or the interface contract while implementing — STOP and write a `questions/regression-team-2026-05-26-<slug>.md`; do not improvise on contract surfaces.
- If you introduce any `warnings` code beyond the three pinned, any new `REASON_*` constant, or any new `TRANSITION_CATEGORIES` value — flag it as a contract change needing a `decisions/` follow-up (per charter "Reporting back").
- Note expected test count delta in the handoff so PM can sanity-check against the post-merge pytest baseline.
