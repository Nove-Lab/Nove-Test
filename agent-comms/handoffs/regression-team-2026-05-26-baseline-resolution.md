---
from: novetest-regression-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-26
slug: baseline-resolution
related:
  - agent-comms/tasks/regression-team-2026-05-26-baseline-resolution.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - design/interace-contract/regression.md
---

# Handoff: Regression baseline resolution & availability (`resolve_latest_baseline` + `derive_latest_regression` + `check_regression_availability`)

## Worktree

- Path: `/home/yjshin/dev/novetest-regression-baseline-resolution`
- Branch: `regression-baseline-resolution`
- Base commit: `0b55baf` (main, after the task was queued)

## Files written / modified

**Src (3 files, 0 new):**
- `src/novetest/regression/compare.py` — appended `resolve_latest_baseline(store, target_expression)` (thin wrapper over `find_runs_for_target(..., include_tombstoned=False)` returning `(baseline=older, target=newer)` per decision §2) + `derive_latest_regression(store)` (composes `list_run_history` → tombstone-filter → take active target from `[0]` → `resolve_latest_baseline` → `compare_runs`). Extended the `from novetest.memory.store import ...` line to pull `find_runs_for_target` and `list_run_history`; added `REASON_NO_COMPARABLE_BASELINE` to the regression-results imports (constant already existed; this slice activates it for the first time).
- `src/novetest/regression/retrieval.py` — appended `check_regression_availability(store, run_reference) -> bool`. Extended the module docstring to cover both functions; extended Memory imports to pull `RunEvidenceNotFoundError`, `find_runs_for_target`, `retrieve_run_evidence`.
- `src/novetest/regression/__init__.py` — re-exports the three new symbols (`resolve_latest_baseline`, `derive_latest_regression`, `check_regression_availability`) and rewrites the module docstring to drop the "out of scope for this slice" disclaimer — the engine surface is now complete.

**Tests (2 new files, 0 modified):**
- `tests/unit/regression/test_baseline_resolution.py` — 17 cases (resolve × 7, derive × 5, check × 5).
- `tests/integration/regression/test_baseline_resolution_e2e.py` — 2 cases (happy-path with cache hit on 2nd call; tombstoned-latest skipped).

**WORKLOG (1 entry appended, top of file).**

**Forbidden files left untouched** (per task brief): `src/novetest/memory/store.py`, `src/novetest/cli/app.py`, `src/novetest/orchestration/**`, `src/novetest/coverage/**`, `design/interace-contract/regression.md`, `design/workflows/regression.md`, `pyproject.toml`.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **442 passed, 3 skipped** (pre-slice baseline on `main` `0b55baf` was 423+3; +19 new tests, all green). The 3 skips are the pre-existing Node-dependent jest integration tests. Slice-scope: `uv run pytest -q tests/unit/regression tests/integration/regression` → 89 passed (was 70 → +19).
- `uv run mypy` → clean, **57 source files** (`--strict`, count unchanged — no new src files).
- Manual smoke (per task brief): built a tmp Project Store with three pytest runs sharing target `tests/` (passed → passed → failed on the same node_id), called `derive_latest_regression`, eyeballed the resulting `RegressionFactSet` (regressed=1, baseline=2nd-latest, target=latest) and the on-disk `regression_facts.json` at the pinned `<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json` path — wire shape matches decision §4 byte-for-byte.

**Pytest baseline drift note for PM:** the task brief quoted a 415-test baseline (taken from `7e5b7a5`). The actual current baseline on `main` (`0b55baf`) is 423+3 — 8 additional tests landed in the comms / verification cycles since. +19 from this slice → 442+3.

## Worklog entry text

```
## 2026-05-26 — phase3 / regression-baseline-resolution

- Landed: the three remaining baseline-resolution / availability helpers on the Regression engine surface, completing the entire `design/interace-contract/regression.md` Internal interface table. **2 src modules edited** (no new src files): `src/novetest/regression/compare.py` gains `resolve_latest_baseline(store, target_expression) -> tuple[RunReference, RunReference] | RegressionUnavailable` (thin wrapper over `find_runs_for_target(..., include_tombstoned=False)` — returns `(baseline=older, target=newer)` per decision §2; fewer than 2 comparable runs → `RegressionUnavailable(REASON_NO_COMPARABLE_BASELINE, detail=target_expression)`; deliberately does NOT pre-filter by `engine_name`/`target_type` — those live in `compare_runs`) and `derive_latest_regression(store) -> RegressionFactSet | RegressionUnavailable` (composes `list_run_history` → filter `tombstoned_at is None` → take `[0].target_expression` as active target → `resolve_latest_baseline` → `compare_runs`; empty/all-tombstoned store → `REASON_NO_COMPARABLE_BASELINE, detail="no-runs"`; single-run target propagates `resolve_latest_baseline`'s Unavailable as-is so the `detail` keeps the more informative target_expression rather than getting overwritten to `"no-runs"`). `src/novetest/regression/retrieval.py` gains `check_regression_availability(store, run_reference) -> bool` (try-resolve via `retrieve_run_evidence`; `RunEvidenceNotFoundError` → False missing-tolerant; `find_runs_for_target` for siblings filtered by `run_id != input.run_id`; `len(filtered) >= 1`; tombstoned input still computes against its historical target per the task brief). `src/novetest/regression/__init__.py` re-exports the three new symbols + the docstring rewritten to drop the "out of scope for this slice" disclaimer (the engine surface is now complete). No `REASON_*` / `TRANSITION_CATEGORIES` / `warnings` codes added — the slice activates the existing `REASON_NO_COMPARABLE_BASELINE` constant for the first time. Tests: **17 new unit + 2 new integration** = 19. `tests/unit/regression/test_baseline_resolution.py` exercises all three functions against the real Project Store via `store_run_evidence` + `delete_run_evidence` (no Memory mocks): `resolve_latest_baseline` × 7 (empty / single-match / exact-two / reverse-insertion-still-orders-by-created_at / three-runs / tombstoned-middle / mixed-targets); `derive_latest_regression` × 5 (empty / single-run-propagates-target-detail / all-tombstoned / latest-tombstoned-falls-back-to-live-earlier-target / happy-path); `check_regression_availability` × 5 (unknown-id / no-siblings / one-sibling / all-siblings-tombstoned / tombstoned-input-with-live-sibling). `tests/integration/regression/test_baseline_resolution_e2e.py` builds three real `RunRecord`s + asserts the on-disk `regression_facts.json` lands at the pinned `<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json` path with `summary.regressed=1`, plus that a second call preserves `derived_at` (cache hit); a second integration case asserts tombstoned-latest is skipped and the next-most-recent live runs anchor the active target.
- Verified: `uv run pytest -q tests/unit tests/integration` → **442 passed + 3 skipped** (was 423+3 on `main` `0b55baf` — the task brief quoted 415 from the older `7e5b7a5` baseline; +19 new tests, all green; the 3 skips are the pre-existing Node-dependent jest integration tests). `uv run mypy` → clean, 57 source files (no new src files, count unchanged), `--strict`. Sanity smoke: built a tmp Project Store with three pytest runs (passed → passed → failed on the same node_id), called `derive_latest_regression`, eyeballed the resulting `RegressionFactSet` (regressed=1, baseline=2nd-latest run, target=latest run) and the on-disk `regression_facts.json` at the pinned path — wire shape matches decision §4 byte-for-byte (`schema_version=1`, 11-key summary, sorted `test_transitions`).
- Left open: **No `delivery-phasing.md` Phase 3 DoD bullet closes from this slice alone** — engine surface completion only. The remaining Phase 3 DoD bullets (`novetest regression compare` / `novetest regression latest` / `novetest compare` / `inspect` Regression section) all close in the next cycle, which projects this engine surface onto envelopes. Per decision §C.2, `regression_outcome` and `regression_delta` envelope shapes are frozen by PM AFTER Manual Test fields them — same ship→field-test→freeze cadence Coverage followed.
- Gotcha: `derive_latest_regression`'s "active target" anchor is the latest **non-tombstoned** run's target_expression — NOT the latest run unconditionally. The unit test `test_derive_latest_skips_tombstoned_latest_and_uses_live_earlier_target` pins this: when the literal newest run is tombstoned on a different target, the active target falls back to the latest **live** run, which can be on a completely different target_expression. Without this filter, `derive_latest_regression` would pass the tombstoned target's expression to `resolve_latest_baseline` and get `REASON_NO_COMPARABLE_BASELINE` even though a perfectly comparable pair sits one rung down the history. Second gotcha: `resolve_latest_baseline`'s single-run case returns `detail=target_expression` (not `"no-runs"`), and `derive_latest_regression` PROPAGATES that detail rather than re-wrapping it — verified by `test_derive_latest_single_run_propagates_resolve_detail`. The "no-runs" detail is reserved for the truly empty / all-tombstoned case where the active target itself cannot be determined. Third gotcha: `check_regression_availability` filters the input run out of its own candidate set by `run_id` — needed because the input run may or may not appear in `find_runs_for_target`'s result depending on its tombstone state (tombstoned inputs are excluded by Memory; live inputs ARE in the result), so the explicit `run_id != input.run_id` filter normalizes both cases. Without it, a single live run on a target would falsely return True (it would see itself in the sibling set). Fourth gotcha: the task brief quoted a 415-test baseline; the actual pre-slice baseline on `main` is 423 — 8 tests drifted in since `7e5b7a5` (Manual Test verification probably triggered some snapshot updates). +19 new lands at 442 regardless; the delta is the load-bearing number.
- Next: Orchestration team's CLI slice — `novetest regression compare <run_id1> <run_id2>` + `novetest regression latest` + `novetest compare` verb + `inspect` Regression section wiring. Those verbs project this engine surface onto envelopes; PM freezes the `regression_outcome` and `regression_delta` shapes AFTER Manual Test fields them (decision §C.2). The Localization team's Phase 4 activation will consume `derive_latest_regression` + `check_regression_availability` + `get_regression_facts` directly — no new engine surface needed there either.
```

## DoD bullets believed closed

**None.** Engine surface completion only — this slice finishes the `design/interace-contract/regression.md` Internal interface table but no `delivery-phasing.md` Phase 3 DoD bullet ticks from it alone. The remaining Phase 3 DoD bullets (`novetest regression compare` / `novetest regression latest` / `novetest compare` verb / `inspect` Regression section) all close together when the follow-up Orchestration CLI cycle ships and Manual Test fields the `regression_outcome` / `regression_delta` envelopes.

## Open items / surprises

1. **No contract changes.** No new `REASON_*` constants, no new `TRANSITION_CATEGORIES` values, no new well-known `warnings` codes, no new envelope shapes. The slice activates the pre-existing `REASON_NO_COMPARABLE_BASELINE` constant for the first time but that's already pinned in decision §7. No `decisions/` follow-up needed.
2. **No contract-doc edits.** `design/interace-contract/regression.md` and `design/workflows/regression.md` already describe the three function signatures verbatim (the prior `compare-runs-impl` slice handled the §C.4 ambiguity edit at line 28). This slice's signatures match those docs without further edits.
3. **`design/interace-contract/regression.md` engine surface is now complete.** All 7 rows of the interface table are implemented. The follow-up CLI cycle is pure projection: CLI verbs → engine entry points → envelopes.
4. **`check_regression_availability` returns a plain `bool`, not a typed result.** Justified in the docstring + task brief — the only failure mode is "no comparable prior" which is exactly what `False` means. Mirrors Memory's `_availability_flags` flag pattern.
5. **No Memory edits.** Task forbade them and Memory's existing `find_runs_for_target` / `list_run_history` / `retrieve_run_evidence` / `RunEvidenceNotFoundError` surface composed exactly to what was needed. The OQ#20 marker-file index (`<store>/memory/by_target/`) remains deferred — the current O(N) file scan is fine at v1.
6. **Pytest baseline drift.** The task brief quoted 415 (from `7e5b7a5`); the actual `main` (`0b55baf`) baseline is 423. +19 new from this slice → 442+3. Just a brief inconsistency, not a blocker; PM may want to update the next task brief to reference `0b55baf` baseline.
7. **No CLI / orchestration / coverage edits.** Strictly within the regression engine territory.
