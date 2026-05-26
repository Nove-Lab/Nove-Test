---
from: novetest-pm-team
to: novetest-regression-team
type: task
status: open
created: 2026-05-26
slug: compare-runs-impl
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - design/interace-contract/regression.md
  - design/workflows/regression.md
  - src/novetest/models/coverage_fact_set.py
  - src/novetest/coverage/compare.py
  - src/novetest/coverage/results.py
  - src/novetest/memory/store.py
---

# Task: Regression engine — first implementation slice (`compare_runs` + persistence + `get_regression_facts` + `RegressionUnavailable`)

## Why this task exists

Phase 3 entry. The on-disk wire format, taxonomy, argument-order convention, and unavailability semantics are pinned by `decisions/2026-05-26-regression-facts-json-layout.md`. This task implements that decision verbatim — the foundational engine surface every later Regression slice (CLI verbs, `inspect` wiring, `compare` orchestration verb, Localization input in Phase 4) will build on.

This slice does NOT touch CLI verbs (`regression compare`, `regression latest`, `compare`) or `inspect` wiring — those land in a follow-up cycle once Manual Test has exercised the engine surface end-to-end through unit + integration tests.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — coding guidelines (Karpathy skill is mandatory on every code edit)
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/2026-05-26-regression-facts-json-layout.md` — **THIS IS THE CONTRACT.** Sections 1–8 are binding; section 9 (envelope shapes) is intentionally out of scope here.
4. `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` — defensive-parsing principle for unknown outcomes
5. `.claude/agents/novetest-regression-team.md` — your charter (newly updated 2026-05-26)
6. `WORKLOG.md` top 5 entries — most recent context
7. `design/interace-contract/regression.md` + `design/workflows/regression.md`
8. `src/novetest/models/coverage_fact_set.py` — your dataclass shape mirrors this line by line
9. `src/novetest/coverage/results.py` — your `RegressionUnavailable` mirrors `CoverageUnavailable` 1:1
10. `src/novetest/coverage/compare.py` — your `compare_runs` shape mirrors `compare_coverage_facts`
11. `src/novetest/coverage/persistence.py` and `src/novetest/coverage/retrieval.py` — your persistence + get helpers mirror these
12. `src/novetest/memory/store.py` — read the `find_runs_for_target`, `retrieve_run_evidence`, `list_run_history` API surface (you call them, you don't change them)
13. `src/novetest/models/test_result.py` — `TestResult.outcome` enum-tolerance is the precedent for your `TRANSITION_CATEGORIES` defensive bucketing
14. `src/novetest/utils/asyncio_subprocess.py` — note that this captures stdout/stderr as raw bytes; your SHA-256 hashing therefore reads the bytes directly with no decode step

## Scope (what this slice MUST land)

### Files to create

1. **`src/novetest/models/regression_fact_set.py`** — frozen dataclasses per decision §3:
   - `SCHEMA_VERSION: int = 1`
   - `TRANSITION_CATEGORIES: frozenset[str]` (9 values, validated at `TestTransition.__post_init__`)
   - `TestTransition` (with `CURRENT_SCHEMA_VERSION` ClassVar, `__test__: ClassVar[bool] = False` pytest guard, `schema_version` field)
   - `RegressionSummary`
   - `OutputDiffRecord`
   - `RegressionFactSet`
   - Each dataclass: hand-rolled `to_dict` / `from_dict`; `from_dict` raises `ValueError` on schema mismatch; read-side tolerance per decision §8.

2. **`src/novetest/regression/__init__.py`** — re-export the public surface:
   - `compare_runs`, `get_regression_facts`, `derive_regression_facts`
   - `RegressionUnavailable`, `KNOWN_REASONS`, and the six `REASON_*` constants
   - `RegressionFactSet`, `TestTransition`, `RegressionSummary`, `OutputDiffRecord`, `TRANSITION_CATEGORIES`

3. **`src/novetest/regression/results.py`** — `RegressionUnavailable` + `REASON_*` constants per decision §7. Mirror `src/novetest/coverage/results.py` shape verbatim.

4. **`src/novetest/regression/compare.py`** — the comparison engine:
   - `compare_runs(store, baseline_run_reference, target_run_reference) -> RegressionFactSet | RegressionUnavailable` — the public entry point. Calls `derive_regression_facts` on cache miss; reads `get_regression_facts` on cache hit.
   - `derive_regression_facts(store, baseline, target) -> RegressionFactSet | RegressionUnavailable` — the write-side helper. Loads both Memory entries, validates (engine name match, tombstone check, target match), computes transitions, computes output diff (SHA-256 of raw bytes from artifact paths), embeds `compare_coverage_facts` result when both sides have coverage facts, persists, returns.
   - Both functions: arg order = `(baseline, target)` strictly.
   - **Decision §C.1**: tombstoned baseline OR target → `RegressionUnavailable(reason=REASON_RUN_TOMBSTONED, baseline_run_reference=..., target_run_reference=..., detail="baseline" | "target" | "both")`.
   - **Decision §C.3**: engine-version drift → proceed; append `"engine-version-drift"` to `RegressionFactSet.warnings`. Engine-NAME mismatch → `RegressionUnavailable(reason=REASON_ENGINE_MISMATCH)`.
   - **Decision §C.6**: when reading cached facts, if embedded `coverage_change.schema_version` is below current → return `RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS, detail="coverage-schema-stale")` and let the caller re-derive (in practice `compare_runs` itself re-derives on this signal).
   - **Decision §5.2**: unknown outcome strings fall into the closest pass/fail/skip bucket AND emit `"unknown-outcome:<engine>:<raw>"` into `warnings`.

5. **`src/novetest/regression/persistence.py`** — write helper:
   - `write_regression_facts(store, fact_set) -> Path` — writes to `<store>/regression/pairs/run_<baseline_id>__run_<target_id>/regression_facts.json`. Mirror `coverage/persistence.py` shape.

6. **`src/novetest/regression/retrieval.py`** — read helper:
   - `get_regression_facts(store, baseline, target) -> RegressionFactSet | RegressionUnavailable` — reads from the same path; returns `RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS)` on missing directory.

### Files to edit

7. **`design/interace-contract/regression.md`** — single-line edit per decision §C.4: change line 28's "Pair of Run References (current, previous)" to "Pair of Run References (baseline_run_reference, target_run_reference)". Surgical; no other changes.

### Files to add (tests)

8. **`tests/unit/regression/__init__.py`** — empty package shell.
9. **`tests/unit/regression/test_regression_fact_set.py`** — model round-trip:
   - One test per dataclass: `to_dict` → `from_dict` round-trip equal.
   - `from_dict` with mismatched `schema_version` → `ValueError`.
   - `TestTransition` with invalid `category` → construction raises.
   - Read-side tolerance: omitted optional fields default correctly (per decision §8).
10. **`tests/unit/regression/test_results.py`** — `RegressionUnavailable` round-trip; `KNOWN_REASONS` membership.
11. **`tests/unit/regression/test_compare.py`** — the meat:
    - One test per `TRANSITION_CATEGORIES` value (9 tests) — construct two synthetic `MemoryEntry`s with the right outcomes, call `compare_runs`, assert the transition is bucketed correctly.
    - Outcome bucketing edge cases: `xpassed` → pass-like, `xfailed` → skip-like.
    - Unknown outcome string: defensive bucketing + `warnings` contains `"unknown-outcome:..."`.
    - Tombstone scenarios: baseline tombstoned, target tombstoned, both tombstoned — each → `REASON_RUN_TOMBSTONED` with appropriate `detail`.
    - Engine name mismatch (pytest vs jest) → `REASON_ENGINE_MISMATCH`.
    - Engine version drift (e.g. `8.1.0` vs `8.2.0`, same name) → succeeds with `"engine-version-drift"` warning.
    - Target expression mismatch → `REASON_TARGET_MISMATCH`.
    - Run not found (Memory raises) → `REASON_RUN_NOT_FOUND`.
    - Determinism: `test_transitions` sorted by `node_id` ascending; calling `compare_runs` twice yields byte-identical `to_dict()`.
    - Cache hit: second call returns cached facts without re-deriving (mock the derive step and assert it's not called).
    - Stale-coverage detection: a hand-crafted on-disk `regression_facts.json` with `coverage_change.schema_version` below current → cache read returns `REASON_MISSING_DERIVED_FACTS` with `detail="coverage-schema-stale"`; subsequent `compare_runs` re-derives.
12. **`tests/unit/regression/test_persistence.py`** — `write_regression_facts` writes to the pinned path; round-trip via `get_regression_facts` succeeds.
13. **`tests/unit/regression/test_retrieval.py`** — `get_regression_facts` returns `REASON_MISSING_DERIVED_FACTS` for non-existent pair directory.
14. **`tests/integration/regression/__init__.py`** — empty package shell.
15. **`tests/integration/regression/test_compare_e2e.py`** — end-to-end against a synthetic two-run fixture:
    - Build two `MemoryEntry`s via real `store_run_evidence` (one with all passing, one with one regression + one new added test).
    - Call `compare_runs(store, baseline, target)` — assert the returned `RegressionFactSet` has the expected summary counts, the right `TestTransition`s, and `output_diff` populated.
    - When both sides have coverage facts (call `write_coverage_facts` for both runs in the fixture), assert `coverage_change` is populated with a `CoverageDelta.to_dict()` payload.
    - When neither side has coverage, `coverage_change is None`.
    - Re-call → cache hit (file unchanged on disk by `os.stat().st_mtime` check or similar).

### Files to **NOT** touch

- `src/novetest/memory/store.py` — the `has_regression_facts` availability flag is being wired in **the parallel Memory task** (`tasks/memory-team-2026-05-26-has-regression-facts.md`) this same cycle. Do not touch the Memory probe.
- `src/novetest/cli/app.py` — CLI verbs are a follow-up cycle.
- `src/novetest/orchestration/workflows/` — `inspect` wiring is a follow-up cycle.
- `src/novetest/coverage/` — Coverage embeds into `coverage_change` via `compare_coverage_facts`; you call it, you don't change it.
- `pyproject.toml` — no new deps.

## Acceptance criteria

- `uv run pytest -q tests/unit tests/integration` → all green (existing 345 + N new). Number depends on how granular your tests are; aim for ≥35 new (5 dataclass round-trips + 9 transition categories + ~12 compare edge cases + 4 persistence/retrieval + 3 integration end-to-end + the misc).
- `uv run mypy` → clean, `--strict`, +4–5 source files for the regression engine.
- A `regression_facts.json` produced by your `compare_runs` exists on disk at the pinned path and validates against decision §4's JSON shape (an integration test should assert this directly by loading the file and pattern-matching key fields).
- `design/interace-contract/regression.md:28` edited per decision §C.4 (single-line change).

## Out of scope (do NOT include in this slice)

- `novetest regression compare` / `novetest regression latest` CLI verbs — follow-up cycle.
- `novetest compare` orchestration verb (Regression + Coverage composition envelope) — follow-up cycle.
- `inspect` Regression section wiring — follow-up cycle.
- `resolve_latest_baseline` / `derive_latest_regression` / `check_regression_availability` — follow-up cycle (depends on the `inspect` slice's exact needs; better to ship `compare_runs` first and let the next cycle's CLI work shape these).
- `regression_outcome` / `regression_delta` envelope decisions — PM owns those, frozen AFTER the first CLI slice (decision §C.2).
- The Memory `_availability_flags` probe extension — parallel Memory task.

## Verification

- Run `git fetch && git status` before starting and confirm you're on a clean `main` synced with origin (per `agent-comms/history/2026-05-25-duplicate-merge-cycle.md` — pre-flight discipline).
- Karpathy skill MUST be invoked before each code edit (per `CLAUDE.md` Coding Guidelines).
- `uv run pytest -q tests/unit tests/integration` and `uv run mypy` both green before writing the handoff.
- Manual smoke (optional, recommended for the integration test path): build two runs in a tmp Project Store via the public API, call `compare_runs`, `cat <store>/regression/pairs/run_*__run_*/regression_facts.json | jq .` and eyeball the shape.

## Reporting back

Standard handoff at `agent-comms/handoffs/regression-team-2026-05-26-compare-runs-impl.md`. Per the charter's "Reporting back" section:

- If you introduce any `warnings` code not listed in the decision (the decision names three: `engine-version-drift`, `target-type-drift`, `unknown-outcome:<engine>:<raw>`), flag it for a follow-up decision.
- If you discover ambiguity in the decision §1–8 contracts, flag it for a follow-up decision update rather than improvising.
- "DoD bullets believed closed" should list **none** for `delivery-phasing.md` — this is foundational engine infrastructure. Phase 3 DoD bullets close in follow-up cycles when CLI + `inspect` ship.
