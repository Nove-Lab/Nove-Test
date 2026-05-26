---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-26
slug: regression-compare-runs-impl
related:
  - agent-comms/handoffs/regression-team-2026-05-26-compare-runs-impl.md
  - agent-comms/tasks/regression-team-2026-05-26-compare-runs-impl.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/verifications/2026-05-26-memory-has-regression-facts.md
---

# Verification: Regression engine — `compare_runs` + persistence + `get_regression_facts` + `RegressionUnavailable`

## Merged commit

- Engine commit: `9c79792` `feat(regression): compare_runs + persistence + RegressionUnavailable (Phase 3 entry)`
- Handoff commit: `99c3128` `comms: handoff for regression compare-runs-impl slice`
- Parent: `2de7bea` (which was itself a fast-forward of the memory-has-regression-facts slice)
- Merge mode: rebase + ff (WORKLOG.md conflict resolved by keeping both 2026-05-26 entries, regression on top per "newest commit on top" convention)
- Files touched (engine slice):
  - **New src files** — `src/novetest/models/regression_fact_set.py`, `src/novetest/regression/__init__.py`, `src/novetest/regression/compare.py`, `src/novetest/regression/persistence.py`, `src/novetest/regression/results.py`, `src/novetest/regression/retrieval.py`
  - **Edited** — `design/interace-contract/regression.md:28` (single-line: `(current, previous)` → `(baseline_run_reference, target_run_reference)`)
  - **New tests** — `tests/unit/regression/{__init__,conftest,test_regression_fact_set,test_results,test_persistence,test_retrieval,test_compare}.py` + `tests/integration/regression/{__init__,test_compare_e2e}.py`
  - `WORKLOG.md` — new top entry
  - `agent-comms/handoffs/regression-team-2026-05-26-compare-runs-impl.md` — handoff doc

## Source handoff

`agent-comms/handoffs/regression-team-2026-05-26-compare-runs-impl.md`

## What changed

Foundational Regression engine landed on disk:

- **`RegressionFactSet`** (frozen dataclass tree in `src/novetest/models/regression_fact_set.py`): `TestTransition` + `RegressionSummary` + `OutputDiffRecord` + `RegressionFactSet`; `SCHEMA_VERSION=1`; `TRANSITION_CATEGORIES` is a closed 9-element frozenset (`added` / `fixed` / `newly_active` / `newly_skipped` / `regressed` / `removed` / `still_failing` / `still_passing` / `still_skipped`); read-tolerant `from_dict` per decision §8.
- **`RegressionUnavailable`** (in `src/novetest/regression/results.py`): discriminator + 6 `REASON_*` constants (`engine-mismatch`, `missing-derived-facts`, `no-comparable-baseline`, `run-not-found`, `run-tombstoned`, `target-mismatch`).
- **Persistence layout** (in `src/novetest/regression/persistence.py`): `<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json` — literal `__` joiner, both `run_` prefixes; order-significant (`compare_runs(A, B)` ≠ `compare_runs(B, A)`).
- **`compare_runs(store, baseline_run_reference, target_run_reference)`** (in `src/novetest/regression/compare.py`): cache-aware entry. Resolves Memory, enforces tombstone / engine-name / target-expression invariants, then reads cached facts via `get_regression_facts` or derives via `derive_regression_facts`. Output-diff SHA-256 reads chunked 64KB (peak-bounded for multi-MB stdout/stderr).
- **`get_regression_facts(store, baseline_run_id, target_run_id)`** (in `src/novetest/regression/retrieval.py`): pure cache reader; surfaces `REASON_MISSING_DERIVED_FACTS` for missing pair-dir AND for embedded coverage payloads at a stale `CoverageDelta` schema version.

## On-disk wire shape (verified verbatim on merged main)

Confirmed by writing a real pair to a tmp store on the merged commit (`99c3128`):

```
<store>/regression/pairs/run_<baseline_run_id>__run_<target_run_id>/regression_facts.json
```

Top-level keys (14):
```
baseline_engine_name, baseline_engine_version, baseline_run_reference,
coverage_change, derived_at, metadata, output_diff, schema_version,
summary, target_engine_name, target_engine_version, target_run_reference,
test_transitions, warnings
```

`summary` is **exactly 11 keys** (9 categories + 2 totals — `total_baseline_tests`, `total_target_tests`).

`baseline_run_reference` / `target_run_reference` each have 3 keys: `run_id`, `created_at`, `schema_version`.

Each `test_transitions[i]` has 9 keys:
```
baseline_duration_ms, baseline_failure_reference, baseline_outcome,
category, node_id, schema_version,
target_duration_ms, target_failure_reference, target_outcome
```

`coverage_change`, `output_diff` → both `null` when absent. `warnings` → `[]` empty list. `metadata` → `{}` empty object.

## Verification steps for Manual Test

### 1. Test gate is green on merged main

```bash
git -C /home/yjshin/dev/aispace/Nove-Test fetch origin
git -C /home/yjshin/dev/aispace/Nove-Test checkout main
uv run pytest -q tests/unit tests/integration
# expect: 423 passed + 3 skipped (was 348+3 before the two slices in this cycle)
uv run mypy
# expect: clean (57 source files; +5 over baseline for the new regression engine)
```

### 2. Wire shape end-to-end (eyeball decision §4)

```bash
mkdir -p /tmp/novetest-verify-reg && cd /tmp/novetest-verify-reg
uv --project /home/yjshin/dev/aispace/Nove-Test run python3 <<'PY'
import json, tempfile
from pathlib import Path
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.compare import compare_runs
from novetest.regression.persistence import regression_facts_path

def mk_tr(node_id, outcome): return TestResult(node_id=node_id, outcome=outcome, duration_ms=10)
def mk_rec(rid, results):
    ts = 1748246400
    ref = RunReference(run_id=rid, created_at=ts)
    return RunRecord(
        run_reference=ref, target_expression="tests/", target_type="dir",
        engine_name="pytest", engine_version="8.2.0", ecosystem="python",
        status="passed", started_at=ts, completed_at=ts + 1000,
        test_results=tuple(results), artifact_paths={},
    )

ws = Path(tempfile.mkdtemp()) / "ws"; ws.mkdir()
store = get_project_store_state(create_project_store(ws).path)

b = mk_rec("0"*31 + "1", [mk_tr("t::a","passed"), mk_tr("t::b","passed")])
t = mk_rec("0"*31 + "2", [mk_tr("t::a","failed"),  # regressed
                          mk_tr("t::b","passed"),  # still_passing
                          mk_tr("t::c","passed")]) # added
store_run_evidence(store, b); store_run_evidence(store, t)

result = compare_runs(store, b.run_reference, t.run_reference)
print("result class:", type(result).__name__)  # RegressionFactSet

fpath = regression_facts_path(store, b.run_reference.run_id, t.run_reference.run_id)
print("on-disk path (relative):", fpath.relative_to(store.path))
payload = json.loads(fpath.read_text())
print("summary:", json.dumps(payload["summary"], sort_keys=True))
print("len(summary):", len(payload["summary"]))  # 11
print("len(top-level keys):", len(payload))      # 14
PY
```

Expect (verbatim from my run on the merged tip):
- `result class: RegressionFactSet`
- `on-disk path (relative): regression/pairs/run_<31 zeros>1__run_<31 zeros>2/regression_facts.json`
- `summary: {"added": 1, "fixed": 0, "newly_active": 0, "newly_skipped": 0, "regressed": 1, "removed": 0, "still_failing": 0, "still_passing": 1, "still_skipped": 0, "total_baseline_tests": 2, "total_target_tests": 3}`
- `len(summary): 11`
- `len(top-level keys): 14`

### 3. Cache hit doesn't re-derive

Inside the same Python session as step 2, call `compare_runs` a second time:

```python
result2 = compare_runs(store, b.run_reference, t.run_reference)
assert result.derived_at == result2.derived_at, "cache hit should NOT re-stamp derived_at"
print("cache-hit derived_at preserved:", result.derived_at)
```

### 4. `RegressionUnavailable` paths

```bash
uv --project /home/yjshin/dev/aispace/Nove-Test run python3 <<'PY'
import tempfile
from pathlib import Path
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence, delete_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.compare import compare_runs

def mk_tr(n, o): return TestResult(node_id=n, outcome=o, duration_ms=10)
def mk_rec(rid, engine="pytest", target="tests/"):
    ts = 1748246400
    ref = RunReference(run_id=rid, created_at=ts)
    return RunRecord(
        run_reference=ref, target_expression=target, target_type="dir",
        engine_name=engine, engine_version="8.2.0", ecosystem="python",
        status="passed", started_at=ts, completed_at=ts + 1000,
        test_results=(mk_tr("t::a","passed"),), artifact_paths={},
    )

ws = Path(tempfile.mkdtemp()) / "ws"; ws.mkdir()
store = get_project_store_state(create_project_store(ws).path)

a = mk_rec("a"*32)
b = mk_rec("b"*32)
store_run_evidence(store, a); store_run_evidence(store, b)

# (i) run-not-found — target id never persisted
fake = RunReference(run_id="9"*32, created_at=1748246400)
r = compare_runs(store, a.run_reference, fake)
print("run-not-found ->", r.reason)  # expect: "run-not-found"

# (ii) engine mismatch
c = mk_rec("c"*32, engine="jest")
store_run_evidence(store, c)
r = compare_runs(store, a.run_reference, c.run_reference)
print("engine-mismatch ->", r.reason)  # expect: "engine-mismatch"

# (iii) target mismatch (same engine, different target)
d = mk_rec("d"*32, target="other-tests/")
store_run_evidence(store, d)
r = compare_runs(store, a.run_reference, d.run_reference)
print("target-mismatch ->", r.reason)  # expect: "target-mismatch"

# (iv) tombstone — cache existed first, then tombstone applied
e = mk_rec("e"*32)
store_run_evidence(store, e)
ok = compare_runs(store, a.run_reference, e.run_reference)  # cache created
print("cache-ok type:", type(ok).__name__)  # RegressionFactSet
delete_run_evidence(store, e.run_reference)
r = compare_runs(store, a.run_reference, e.run_reference)
print("run-tombstoned (cache exists) ->", r.reason)  # expect: "run-tombstoned"
PY
```

Expect:
- `run-not-found -> run-not-found`
- `engine-mismatch -> engine-mismatch`
- `target-mismatch -> target-mismatch`
- `cache-ok type: RegressionFactSet`
- `run-tombstoned (cache exists) -> run-tombstoned`

The (iv) case demonstrates decision §C.1: even with a fresh cached facts file on disk, a subsequent tombstone overrides — the engine refuses to surface stale data as a fresh signal.

### 5. Order-significance of the pair directory

`compare_runs(A, B)` and `compare_runs(B, A)` write to DISTINCT pair directories. Verify by calling both and listing `<store>/regression/pairs/`:

```bash
ls <tmp-store-path>/.novetest/regression/pairs/
# expect two sibling dirs: run_<A>__run_<B> and run_<B>__run_<A>
```

Transition direction is order-significant (pass→fail vs fail→pass).

## Critical edge cases worth probing

- **`TRANSITION_CATEGORIES` is a closed 9-set.** Any path that produces a 10th category is a contract violation. The 9 are exhaustive: every (baseline_bucket, target_bucket) ∈ {pass-like, fail-like, skip-like, ∅}² maps onto one of the 9. (∅ marks "not present this side" — i.e. `added` or `removed`.)
- **`xpassed` → pass-like; `xfailed` → skip-like.** If you craft a `TestResult` with raw outcome `xpassed`, the bucket is `_PASS_LIKE`. `xfailed` is `_SKIP_LIKE`. This means an `xfailed` baseline going to `xpassed` target classifies as `newly_active` (skip-like → pass-like), not `regressed`.
- **Unknown outcomes warn once per `(engine, raw)` pair.** A `weird-status` raw outcome on 100 tests emits `"unknown-outcome:pytest:weird-status"` in `warnings` exactly once. If you see N duplicates of the same code, that's a bug.
- **`coverage_change` is null when EITHER side lacks Coverage Facts.** When both sides have facts, it embeds `CoverageDelta.to_dict()` verbatim. If the embedded payload's `schema_version` is stale relative to `CoverageDelta.SCHEMA_VERSION`, **`get_regression_facts` returns `REASON_MISSING_DERIVED_FACTS`** even though the file exists — staleness is at the engine seam, not at the model layer. So `RegressionFactSet.from_dict(stale_payload)` will happily round-trip; only `get_regression_facts(...)` enforces the check.
- **`output_diff` lives at TOP level** of the persisted JSON, NOT per-transition. The per-transition keys are 9 — no `output_diff` key inside each `test_transitions[i]`. If a future consumer expects per-transition output_diff, that is the wrong shape — refer them to decision §4 and the persisted JSON.
- **No CLI surface yet.** `novetest regression compare`, `novetest regression latest`, `novetest compare`, `inspect` Regression section wiring all land in the next cycle. The engine layer is fully testable directly via the Python API exercised in steps 2–5 above.

## Notes that weren't obvious during merge

- **WORKLOG.md conflict during rebase.** Resolved by keeping both 2026-05-26 entries, regression on top (it landed second after the rebase, per the "newest commit on top" convention also used in the 2026-05-21 conflict). No content lost. Markers fully removed; verified post-rebase.
- **No new contract surfaces beyond decision `2026-05-26-regression-facts-json-layout.md`.** No new `REASON_*` constant, no new `TRANSITION_CATEGORIES` value, no new `warnings` code outside the three pinned in §5.2 (`engine-version-drift`, `target-type-drift`, `unknown-outcome:<engine>:<raw>`).
- **`get_regression_facts` does NOT call `retrieve_run_evidence`** — it is a pure cache read. Memory resolution + tombstone validation lives at `compare_runs`, not at the retrieval seam. This deviates from Coverage's `get_coverage_facts` precedent (which does resolve Memory). PM has been informed via the handoff's "Open items / surprises" section.
- **Pre-cycle test baseline drift.** The regression-team handoff said `345` baseline + 70 = 415; memory-team handoff said `348` baseline + 8 = 353. The actual baseline on `e80e3cf` was **348**, and the post-merge gate landed at **423** (= 348 + 75). The 75 vs 78 expected delta is consistent with the regression team having measured against a stale 345-baseline assumption; no test was actually lost — both slices are fully in place. The +5 mypy source-file delta (52 → 57) matches the regression engine 5-file count exactly.

## DoD bullets to check (PM-tracked, not for Manual Test to tick)

**None close from this slice alone.** Per the handoff:
- `delivery-phasing.md` Phase 3 DoD bullets fire when the CLI verbs ship and Manual Test fields the `regression_outcome` / `regression_delta` envelope shapes. Decision §C.2 freezes those envelope shapes in companion decisions AFTER Manual Test fields them on the next-cycle CLI slice — same ship→field-test→freeze cadence the two Coverage envelope decisions followed.
- `resolve_latest_baseline` / `derive_latest_regression` / `check_regression_availability` are explicit follow-ups for the next-cycle CLI slice.
