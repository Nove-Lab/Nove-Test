---
from: novetest-regression-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-26
slug: compare-runs-impl
related:
  - agent-comms/tasks/regression-team-2026-05-26-compare-runs-impl.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/tasks/memory-team-2026-05-26-has-regression-facts.md
---

# Handoff: Regression engine — `compare_runs` + persistence + `get_regression_facts` + `RegressionUnavailable`

## Worktree

- Path: `/home/yjshin/dev/aispace/Nove-Test-regression-compare-runs`
- Branch: `regression-team/compare-runs-impl`
- Base commit: `e80e3cf` (the same commit `main-branch-team` last committed)
- Tip commit: `d3d685b` — single commit on the branch
- Clean: yes (`git status` reports a clean working tree on the branch tip)

## Files written / modified

### New source files (5)

- `src/novetest/models/regression_fact_set.py` — frozen dataclass tree
  (`TestTransition` + `RegressionSummary` + `OutputDiffRecord` +
  `RegressionFactSet`); `SCHEMA_VERSION=1`; `TRANSITION_CATEGORIES`
  closed 9-set; hand-rolled `to_dict`/`from_dict` with read-side
  tolerance per decision §8; `TestTransition` carries
  `__test__: ClassVar[bool] = False` pytest-collection guard mirroring
  `TestResult`.
- `src/novetest/regression/results.py` — `RegressionUnavailable`
  discriminator + the 6 `REASON_*` constants + `KNOWN_REASONS`
  frozenset per decision §7.
- `src/novetest/regression/persistence.py` —
  `regression_pair_dirname` / `regression_pair_dir` /
  `regression_facts_path` / `write_regression_facts` /
  `read_regression_facts_raw` (the raw-dict reader keeps the retrieval
  layer in charge of staleness detection).
- `src/novetest/regression/retrieval.py` — `get_regression_facts`
  (pure cache read, **no Memory call**; surfaces
  `REASON_MISSING_DERIVED_FACTS` for missing pair-dir AND for embedded
  coverage payloads at a stale `schema_version`, per decision §C.6).
- `src/novetest/regression/compare.py` —
  `compare_runs(store, baseline, target)` cache-aware entry point +
  `derive_regression_facts(store, baseline, target)` write-side helper;
  bucketing helpers; `_build_output_diff` chunked-SHA-256s artifact
  bytes (64KB chunks; peak memory bounded for multi-MB stdout/stderr
  captures); `_maybe_coverage_change` embeds
  `CoverageDelta.to_dict()` when both sides have Coverage Facts, else
  `None`.

### Modified source files (1)

- `src/novetest/regression/__init__.py` — re-exports the full public
  surface (`compare_runs`, `derive_regression_facts`,
  `get_regression_facts`; `RegressionFactSet`, `TestTransition`,
  `RegressionSummary`, `OutputDiffRecord`, `TRANSITION_CATEGORIES`;
  `RegressionUnavailable`, `KNOWN_REASONS`, all 6 `REASON_*` constants,
  `SCHEMA_VERSION`).

### Modified design files (1)

- `design/interace-contract/regression.md:28` — single-line edit per
  decision §C.4: `"Pair of Run References (current, previous)"` →
  `"Pair of Run References (baseline_run_reference, target_run_reference)"`.
  Surgical; no other changes.

### New test files (8)

- `tests/unit/regression/__init__.py` — empty package shell.
- `tests/unit/regression/conftest.py` — shared fixtures
  (`initialized_store`, `make_test_result`, `make_run_record`,
  `seed_run_record`).
- `tests/unit/regression/test_regression_fact_set.py` — 19 cases
  covering model round-trip, schema-version mismatch, read-side
  tolerance, and the closed 9-category invariant.
- `tests/unit/regression/test_results.py` — 6 cases on the
  `RegressionUnavailable` shape + `KNOWN_REASONS` membership + wire-
  level reason string pinning.
- `tests/unit/regression/test_persistence.py` — 9 cases on the
  load-bearing path layout, filename constant, write/read round-trip,
  overwrite semantics, and trailing-newline JSON formatting.
- `tests/unit/regression/test_retrieval.py` — 5 cases on missing
  pair-dir, cached-facts return, coverage-schema-stale detection,
  null-coverage pass-through, and argument-order significance.
- `tests/unit/regression/test_compare.py` — 31 cases: one per
  `TRANSITION_CATEGORIES` value (9), bucketing edge cases (`xpassed` →
  pass-like, `xfailed` → skip-like, unknown-outcome defensive bucketing
  + warning, warning dedup across tests), tombstones (baseline /
  target / both / cache-override-after-tombstone), engine name
  mismatch, engine version drift (warning), target expression
  mismatch, target type drift (warning), run-not-found
  (baseline-side + target-side), determinism (transitions sorted by
  node_id; two calls byte-identical), cache-hit-doesn't-re-derive
  (monkeypatch sentinel), stale-coverage triggers re-derive,
  output_diff SHA-256 / None / identical paths, and a direct
  `derive_regression_facts` smoke.
- `tests/integration/regression/__init__.py` — empty package shell.
- `tests/integration/regression/test_compare_e2e.py` — 5 cases:
  end-to-end summary + per-test categories, persisted-file path +
  decision-§4 key-level shape (incl. `len(summary) == 11`), embedded
  `coverage_change` round-trip via `CoverageDelta.from_dict`,
  `coverage_change is None` when neither side has facts, and
  `st_mtime_ns`-stable cache-hit.

### Worklog

- `WORKLOG.md` — new top entry under `## 2026-05-26 — phase3 /
  regression-compare-runs-impl`.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **415 passed + 3
  skipped** (was 345 + 3 before this slice; **+70 new tests**, all
  green; the 3 skips are the pre-existing Node-dependent jest
  integration tests).
- `uv run mypy` → **clean**, `--strict`, **57 source files** (was 52;
  +5 new regression engine files).
- Manual smoke (recommended by the task): built a tmp Project Store
  with two synthetic runs (`tests/x.py::a` regresses, `::b`
  still_passing, `::c` added on target), called `compare_runs`, and
  eyeballed `<store>/regression/pairs/run_..__run_../regression_facts.json`.
  The wire shape matches decision §4 exactly (literal `__` joiner; both
  `run_` prefixes; 9-category taxonomy + 2 totals = 11 summary keys;
  `test_transitions` sorted by node_id; `output_diff` / `coverage_change`
  null when absent; `warnings: []`; `metadata: {}`).

## Worklog entry text

```
## 2026-05-26 — phase3 / regression-compare-runs-impl

- Landed: foundational Regression engine surface implementing
  `decisions/2026-05-26-regression-facts-json-layout.md` §1–§8
  verbatim. 5 new src files — `src/novetest/models/regression_fact_set.py`
  (frozen dataclass tree: `TestTransition` + `RegressionSummary` +
  `OutputDiffRecord` + `RegressionFactSet`; `SCHEMA_VERSION=1`;
  `TRANSITION_CATEGORIES` closed 9-set; `__test__: ClassVar[bool]
  = False` pytest collection guard on `TestTransition` mirroring
  `TestResult`; hand-rolled `to_dict`/`from_dict` with read-tolerance
  for the optional fields decision §8 enumerates);
  `src/novetest/regression/results.py` (`RegressionUnavailable`
  discriminator + the 6 `REASON_*` constants + `KNOWN_REASONS`
  frozenset per decision §7); `src/novetest/regression/persistence.py`
  (`regression_pair_dirname` / `regression_pair_dir` /
  `regression_facts_path` / `write_regression_facts` /
  `read_regression_facts_raw` — the raw-dict reader keeps the
  retrieval layer in charge of staleness detection);
  `src/novetest/regression/retrieval.py` (`get_regression_facts` —
  pure cache reader, no Memory call, surfaces
  `REASON_MISSING_DERIVED_FACTS` for missing pair-dir AND for embedded
  coverage payloads with stale `schema_version` per decision §C.6);
  `src/novetest/regression/compare.py` (`compare_runs(store, baseline,
  target)` cache-aware entry + `derive_regression_facts(store,
  baseline, target)` write-side helper; bucketing helpers;
  `_build_output_diff` reads artifact bytes via `store.path /
  rel_path` and chunked-SHA-256s them — 64KB chunks keep peak memory
  bounded for multi-MB stdout/stderr captures).
  `src/novetest/regression/__init__.py` re-exports the full public
  surface. 1 design file edited — `design/interace-contract/regression.md:28`
  per decision §C.4: `"Pair of Run References (current, previous)"`
  → `"Pair of Run References (baseline_run_reference,
  target_run_reference)"` (single-line surgical change). Tests: 70
  new across `tests/unit/regression/` (19 model round-trip + 6
  results + 9 persistence + 5 retrieval + 31 compare) and
  `tests/integration/regression/` (5 end-to-end). Every
  `TRANSITION_CATEGORIES` value has at least one compare test
  exercising its construction (9 categories — `regressed` / `fixed`
  / `still_failing` / `still_passing` / `still_skipped` /
  `newly_skipped` / `newly_active` / `added` / `removed`); every
  `REASON_*` constant has at least one return-path test
  (`REASON_RUN_NOT_FOUND` baseline-side + target-side;
  `REASON_RUN_TOMBSTONED` baseline / target / both /
  cache-override-after-tombstone; `REASON_ENGINE_MISMATCH`;
  `REASON_TARGET_MISMATCH`; `REASON_MISSING_DERIVED_FACTS` missing-dir
  + coverage-schema-stale; `REASON_NO_COMPARABLE_BASELINE` not
  exercised here — it's a follow-up-slice concern when
  `resolve_latest_baseline` lands). Determinism is asserted via
  `json.dumps(..., sort_keys=True)` byte-equality on two successive
  calls (the second is a cache hit, so `derived_at` is preserved).
  Cache-hit-doesn't-re-derive is asserted via a
  `monkeypatch.setattr(compare_module, "derive_regression_facts",
  sentinel)` after the first call. The integration suite builds two
  real `RunRecord`s via real `store_run_evidence` +
  `write_coverage_facts`, asserts the persisted `regression_facts.json`
  lands at the pinned path, that its key-level shape matches decision
  §4 (incl. `len(summary) == 11`), and that `coverage_change`
  round-trips via `CoverageDelta.from_dict` when both sides have
  facts.

- Verified: `uv run pytest -q tests/unit tests/integration` → 415
  passed + 3 skipped (was 345 + 3 before this slice; +70 new tests,
  all green; the 3 skips are the pre-existing Node-dependent jest
  integration tests). `uv run mypy` → clean (57 source files,
  `--strict`; +5 over baseline for the regression engine). Manual
  smoke: built a tmp-store with two synthetic runs (a regression on
  `tests/x.py::a`, `tests/x.py::b` still_passing, `tests/x.py::c`
  added on target), called `compare_runs`, and eyeballed
  `<store>/regression/pairs/run_..__run_../regression_facts.json` —
  the wire shape matches decision §4 exactly (literal `__` joiner;
  both `run_` prefixes; 9-category taxonomy + 2 totals = 11 summary
  keys; `test_transitions` sorted by node_id; `output_diff` /
  `coverage_change` null when absent; `warnings: []`; `metadata: {}`
  for read-side tolerance).

- Left open: No `delivery-phasing.md` Phase 3 DoD bullet closes from
  this slice alone — this is foundational engine infrastructure that
  Regression's CLI verbs (`novetest regression compare` / `novetest
  regression latest` / `novetest compare`) and `inspect` Regression
  section wiring will consume in the next cycles. The actual Phase 3
  DoD bullets fire when those CLI verbs ship and Manual Test fields
  the `regression_outcome` / `regression_delta` envelope shapes (per
  decision §C.2, PM freezes those in companion decisions AFTER the
  first CLI slice ships — same ship→field-test→freeze cadence the
  two Coverage envelope decisions followed). `resolve_latest_baseline`
  / `derive_latest_regression` / `check_regression_availability`
  deferred to the same next-cycle CLI slice (the task explicitly
  listed them out of scope — better to let the CLI work shape their
  exact signatures). No new `warnings` codes, `REASON_*` constants,
  or `TRANSITION_CATEGORIES` values beyond what decision §3 / §5 /
  §7 / §8 already pinned — no follow-up decision needed for this
  slice.

- Gotcha: `get_regression_facts` does NOT call `retrieve_run_evidence`
  — it's a pure cache read (file-system existence + JSON parse +
  embedded-coverage-schema check). This deviates from Coverage's
  `get_coverage_facts` precedent (which does resolve Memory to
  surface a clean `run-not-found` signal), but the task explicitly
  described the retrieval layer that way
  (`tasks/regression-team-2026-05-26-compare-runs-impl.md` line 77:
  "reads from the same path; returns
  `RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS)` on
  missing directory"). Memory resolution + tombstone validation
  happens once at `compare_runs` time, avoiding a redundant Memory
  walk on every cache lookup. Second gotcha: tombstone check overrides
  cached facts even when a stale `regression_facts.json` already
  exists on disk (decision §C.1). The cached file is intentionally
  NOT deleted on tombstone (option (c) in the question doc; PM
  rejected it as too aggressive for v1) — left on disk for audit, but
  `compare_runs` returns `REASON_RUN_TOMBSTONED` before touching the
  cache. Third gotcha: `coverage_change` carries the embedded
  `CoverageDelta.to_dict()` verbatim, but `RegressionFactSet.from_dict`
  does NOT re-validate its embedded `schema_version` — that check
  lives ONE LAYER UP in `get_regression_facts` (so a direct
  `RegressionFactSet.from_dict(payload)` will happily round-trip a
  stale-coverage payload; the engine seam is the place enforcing
  cross-schema consistency per decision §C.6). Fourth gotcha:
  output_diff SHA-256 reads chunked (64KB) bytes — `read_bytes()` on
  a multi-MB stdout capture would peak unnecessarily; the chunked
  `iter(lambda: handle.read(65536), b"")` keeps peak memory bounded
  while staying deterministic (raw bytes from
  `utils/asyncio_subprocess.run_subprocess` — no decode step). Fifth:
  unknown-outcome warnings are deduplicated per `(engine, raw)` pair
  within a single `derive_regression_facts` call (a `weird-status`
  outcome on 100 tests emits the `"unknown-outcome:pytest:weird-status"`
  warning exactly once, not 100 times) — the decision §5.2 phrasing
  "one-shot warning" is preserved this way. Sixth: engine_name match
  is checked BEFORE target_expression in `derive_regression_facts` —
  same engine + different target produces `REASON_TARGET_MISMATCH`,
  but DIFFERENT engines short-circuit to `REASON_ENGINE_MISMATCH`
  even when the target also differs (more informative error for the
  common cross-language mistake).

- Next: CLI slice — `novetest regression compare <run_id1> <run_id2>`
  + `novetest regression latest` + `novetest compare` orchestration
  verb + `inspect` Regression section wiring. That slice introduces
  `resolve_latest_baseline` (uses Memory's `find_runs_for_target`
  from the 2026-05-25 prereq) + `derive_latest_regression` +
  `check_regression_availability` (already-pinned signatures in
  `design/interace-contract/regression.md`) + the `regression_outcome`
  / `regression_delta` envelope shapes (PM freezes both AFTER Manual
  Test fields them per decision §C.2). The engine surface this slice
  ships is the foundation those verbs project onto envelopes — no
  contract churn needed.
```

## DoD bullets believed closed

**None.** This slice is foundational engine infrastructure (cache-aware
`compare_runs` + persistence + Unavailable enum), one of two parallel
Phase-3-entry slices (the other is Memory's `has_regression_facts`
probe under `tasks/memory-team-2026-05-26-has-regression-facts.md`).
The Phase 3 `delivery-phasing.md` DoD bullets only close when the CLI
verbs ship and Manual Test fields the envelope shapes — that's the
next cycle, not this one.

## Open items / surprises

### Contract changes vs the binding decision — none

This slice introduced **no new `regression_facts.json` schema fields,
no new `REASON_*` constants, no new `TRANSITION_CATEGORIES` values,
and no new well-known `warnings` codes beyond what decision
`2026-05-26-regression-facts-json-layout.md` already pinned**:

- The 9 `TRANSITION_CATEGORIES` values are §3 verbatim.
- The 6 `REASON_*` constants are §7 verbatim.
- Three warning codes are used (`"engine-version-drift"`,
  `"target-type-drift"`, `"unknown-outcome:<engine>:<raw>"`); all three
  are explicitly named in §5.2 / §8.
- Persisted JSON shape is §4 verbatim — the smoke output and the
  integration `test_compare_runs_writes_facts_at_pinned_path` both
  pattern-match it at key level.

Per the charter's reporting-back hint, this means **no follow-up
`decisions/` entry is needed for this slice**.

### Anticipated follow-up decisions (PM-tracked, NOT for this cycle)

Per decision §C.2, the **next** Regression slice (CLI verbs +
`inspect` wiring) will introduce two envelope shapes — `regression_outcome`
(single-run "is a baseline resolvable?" section in `inspect`) and
`regression_delta` / `regression_pair` (two-run comparison body in
`regression compare` / `compare`). PM freezes both shapes in companion
`decisions/` entries AFTER Manual Test fields them, same cadence the
two Coverage envelope decisions followed. Flagging now so PM can
schedule the freeze cycle when the CLI slice handoff lands.

### Coordination touchpoints

- Memory's parallel slice (`tasks/memory-team-2026-05-26-has-regression-facts.md`)
  implements the `_availability_flags` probe scanning
  `<store>/regression/pairs/` for `run_<run_id>` substrings — that
  layout is what this slice persists, so the two slices compose
  cleanly. **Confirmed** by reading
  `src/novetest/memory/store.py:_any_regression_pair_exists` on the
  main branch (already merged): it scans pair directory names for
  the `run_<run_id>` substring and checks for
  `regression_facts.json`. The probe and this slice's persistence
  layer line up byte-identically (`_RUN_DIR_PREFIX = "run_"` matches
  Memory's identical constant).
- Coverage's `CoverageDelta.to_dict()` is embedded verbatim in
  `regression_facts.json.coverage_change` per decision §C.6. The
  retrieval-layer staleness check uses
  `CoverageDelta.SCHEMA_VERSION` directly — when Coverage v2 lands,
  it will trigger the documented stale-on-read path automatically
  (no Regression-side change needed unless the embedding shape
  itself changes).

### Manual-test exit-criteria recommendation

For the verification round that follows this merge, Manual Test
should exercise:

1. The on-disk JSON at `<store>/regression/pairs/run_..__run_../regression_facts.json`
   pattern-matches decision §4 (run a fresh `derive_regression_facts`
   in a tmp store; load + eyeball with `jq .`).
2. Tombstoning a run AFTER cache creation still returns
   `REASON_RUN_TOMBSTONED` (decision §C.1 — the "don't surface stale
   data as fresh signal" principle).
3. The pair directory layout is order-significant —
   `compare_runs(A, B)` and `compare_runs(B, A)` produce distinct
   directories.

No CLI surface to exercise yet — the verbs land in the next cycle.
