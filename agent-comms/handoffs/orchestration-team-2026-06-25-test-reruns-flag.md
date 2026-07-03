---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-03
slug: test-reruns-flag
related:
  - agent-comms/tasks/orchestration-team-2026-06-25-test-reruns-flag.md
  - agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md
  - agent-comms/questions/orchestration-team-2026-07-03-reruns-replay-api-mismatch.md
---

# Handoff: `novetest test --reruns N` + Replay integration (Wave 1)

- **Worktree / branch**: `orchestration/test-reruns-flag` @ `0a6cddf`, off main `5e7d5b5` (current main tip — pure FF expected; no other slice is in flight on these files).
- **Task**: `orchestration-team-2026-06-25-test-reruns-flag` (Wave 1 of the CEO-approved 2026-07-03 cycle plan; its gate — reset on main — was satisfied by `419be0c`+`3b0d206`).
- **Goal shipped**: the `flaky_suspected` recommendation category is now reachable through a single user command. `novetest test --reruns N` (default 0 = byte-identical prior behavior) opts into one whole-run Replay Attempt when the run has failed tests; an `inconsistent` classification produces a `flaky_suspected` recommendation with a resolvable `replay_result` citation.

## ⚠ One deliberate deviation from the brief (PM ratification filed, non-blocking)

The brief's pseudocode loops `replay_run(..., target=test_id)` per failed test and catches `ReplayUnavailableError`. **Neither exists in the shipped Replay API**: `replay_run(store, original_ref, *, reruns, timeout)` is whole-run-granular (no `target` param), returns (never raises) `ReplayResult | ReplayUnavailable`, and persists ONE result per original run id (loop iterations would overwrite each other and re-execute the full suite `N_failed × N` times). Implemented as **one whole-run attempt**; every element of the decision's frozen surface (flag signature, default-0 identity, envelope diffs, error paths, exit codes, persistence) ships exactly as pinned. Full analysis + asks: `agent-comms/questions/orchestration-team-2026-07-03-reruns-replay-api-mismatch.md`. **This does not gate the merge** — the decision's exit conditions are met; the question exists so PM can amend the brief's pseudocode or kick back.

## Files (20 in commit `0a6cddf`)

**src (5 MOD, all Orchestration-owned):**
- `src/novetest/cli/app.py` — `--reruns` keyword flag on `test_cmd`; negative → `invalid-flag` exit 2 (mirrors `--formula`, validated after `_require_store` like localization); forwards `reruns=` to the workflow. Handler/envelope projection untouched.
- `src/novetest/orchestration/workflows/test.py` — step 6b (post-Localization, pre-synthesis): `reruns > 0 AND record_has_failed_tests(record)` → `await replay_run(store, ref, reruns=reruns, timeout=timeout)`; Memory Entry refreshed on success (availability flag); `_build_stage_eligibility(..., replay_outcome=)` maps None→`not_run`/`replay_not_run`, ReplayResult→`available`/None, ReplayUnavailable→`unavailable`/reason; `build_test_outcome_from_run_id` re-derive folds in cached `get_replay_result` (round-trip parity).
- `src/novetest/orchestration/recommendation/fact_bundle.py` — **brief §3 rename**: `FactBundle.replay_result: ReplayResult | None` → `replay_results: tuple[ReplayResult, ...] = ()`; `build_fact_bundle` kwarg follows; new `record_has_failed_tests(record)` (public, `has_failed_tests` delegates — one fail-detection semantic for matcher + workflow).
- `src/novetest/orchestration/recommendation/categories.py` — `match_flaky_suspected` iterates the tuple (one hit per `inconsistent`, tuple order); `match_all_green` suppressed by ANY inconsistent element.
- `src/novetest/orchestration/recommendation/citations.py` — flaky citation resolves the hit's OWN source result via `(run_reference, test_id)` payload match (correct for multi-element tuples).

**tests (4 NEW = 25 tests, 7 MOD):**
- NEW `tests/unit/cli/test_test_cmd_reruns_flag.py` (9) — forwarding 0/1/5/100, default-0, `-1` → `invalid-flag` + workflow-not-called, bare vs `--reruns 0` byte-identity, default-envelope snapshot, `--reruns` happy-envelope snapshot.
- NEW `tests/unit/orchestration/workflows/test_workflow_reruns_integration.py` (4) — call shape pinned (`args == (store, ref)`, `kwargs == {reruns, timeout}`), skip-on-passing (eligibility byte-matches no-flag), default-0 never calls, ReplayUnavailable best-effort (unavailable_analysis lists `replay`).
- NEW `tests/unit/orchestration/recommendation/test_match_flaky_suspected_list.py` (10) — tuple contract incl. brief §4's "2 inconsistent + 1 reproducible → 2 hits, deterministic order", empty-`test_id` degradation, all_green suppression, per-hit citations.
- NEW `tests/integration/cli/test_test_cmd_with_reruns.py` (2) — **subprocess e2e** on `flaky-python` with counter pre-seeded `"1"` (original run FAILS odd; rerun #1 PASSES even → divergence): exit 3, `stage_eligibility.replay == "available"`, exactly one `flaky_suspected` (`reruns_total 2, reruns_failed 1`, focal `test_id`), `replay_result.json` on disk, replay reruns as first-class Memory Entries (`memory list` count 3), `--reruns=-1` → exit 2 with counter untouched. **Placement**: charter's `tests/integration/cli/` (subprocess lifecycle surface) vs the brief's `tests/integration/` root — same carried-forward PM item as the reset cycle.
- MOD rename ripple: `test_categories.py`, `test_fact_bundle.py`, `test_synthesizer.py`, `test_citations.py`, `test_test_handler.py`; `test_recommendation_round_trip.py` replay branch now RESOLVES via `get_replay_result` (was `pytest.skip("Phase 5")`).
- MOD **cross-team (flagged)**: `tests/integration/replay/test_flaky_suspected_synthesis.py` — mechanical `replay_result=result` → `replay_results=(result,)` kwarg + comment; mandated by brief §3 "check every read site and update. Use grep to confirm coverage." No behavioral change to Replay-team assertions.

**snapshots (+3, all NEW `.ambr`)**: `tests/unit/cli/__snapshots__/test_test_cmd_reruns_flag.ambr` (default + happy envelopes), `tests/integration/cli/__snapshots__/test_test_cmd_with_reruns.ambr` (run-id-normalized flaky recommendation). **Zero pre-existing snapshots modified.**

**doc**: `design/workflows/orchestration.md` — §2 test row + new §"Integrated replay sub-workflow" (trigger, outcome-mapping table, API-adaptation note, error paths).

## Verification (all `env -u PYTHONPATH`, in-worktree)

| Gate | Result |
|---|---|
| `uv run mypy --strict src/novetest` | **Success: no issues found in 114 source files** |
| `uv run pytest -q tests/unit tests/integration` | **1373 passed / 3 skipped / 0 failed, 47 snapshots passed** (= 1348 baseline + 25 new; 3 skips = pre-existing jest/Node-12 host issue) |
| Snapshot stability | full suite re-run WITHOUT `--snapshot-update` → all 47 pass |
| Real-CLI smoke (temp workspace) | `init` → `test --reruns 2` → `ok: true`, `replay: "available"`, `flaky_suspected` summary "Test `…` flaky: 1/2 reruns failed." |
| Default-path zero-regression | bare vs `--reruns 0` byte-identical; all pre-existing test-verb/lifecycle snapshots untouched |

## Envelope-schema implications

None to `novetest/v1` (no bump). Additive behavior only, per decision §"Envelope": `data.stage_eligibility.replay` can now read `"available"` / `"unavailable"` (previously always `"not_run"`); `data.recommendations[]` can now contain `category: "flaky_suspected"` (kind `replay_result` citations resolvable via `replay/get_replay_result`). Envelope SHAPE unchanged; exit-code matrix unchanged.

## Merge notes for Main Branch

- Base `5e7d5b5` = current main tip → expect pure FF. No file overlap with the three Wave-2 anchored-pin slices currently pending (Memory/Run/Regression briefs); merging THIS first keeps the Wave-2 Orchestration slice (`anchored-init-and-verb-resolution`, which will touch `app.py`/`workflows/test.py` again) on a current base.
- Pre-merge gate to re-run: `mypy --strict src/novetest` (expect Success, 114) + full suite (expect 1373/3/0, 47 snapshots).
- One cross-team test file touched (`tests/integration/replay/test_flaky_suspected_synthesis.py`, mechanical kwarg) — call it out in the verification request so Manual Test/Replay eyes land on it.

## DoD bullets believed closed (PM verifies + ticks)

Per the task's acceptance criteria (no DoD checklist exists for this post-MVP slice; PM adds the bullet after merge per the brief):
1. New + updated tests green (1373/3/0 local; CI matrix = Main Branch gate).
2. Existing no-flag `novetest test` snapshot surface unchanged byte-for-byte.
3. `--reruns 5`-path snapshot merged and pinned (unit happy-envelope + e2e distilled recommendation).
4. `match_flaky_suspected` iterates `replay_results`; old `replay_result` field removed everywhere (grep-verified: remaining hits are module imports / unrelated locals).
5. `WORKLOG.md` entry (top, 2026-07-03).
6. This handoff with worktree pointer + envelope diffs for PM's user-doc pass.

NOT self-merged, NOT pushed. Two open PM items: the API-adaptation ratification question + the e2e path placement carry-forward.
