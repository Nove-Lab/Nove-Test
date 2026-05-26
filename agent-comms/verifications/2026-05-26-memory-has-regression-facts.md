---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-26
slug: memory-has-regression-facts
related:
  - agent-comms/handoffs/memory-team-2026-05-26-has-regression-facts.md
  - agent-comms/tasks/memory-team-2026-05-26-has-regression-facts.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
---

# Verification: Memory `_availability_flags` — `has_regression_facts` probe pinned with 8 dedicated test cases

## Merged commit

- Commit: `2de7bea` `test(memory): pin has_regression_facts probe with 8 dedicated cases`
- Parent: `e80e3cf`
- Merge mode: clean fast-forward (no conflict at this point — the WORKLOG conflict happened on the *next* rebase, not this one)
- Files touched:
  - `tests/unit/memory/test_store.py` — +8 new test cases (`# --- has_regression_facts` section)
  - `WORKLOG.md` — new top entry
  - `agent-comms/handoffs/memory-team-2026-05-26-has-regression-facts.md` — handoff doc
- **No `src/` change** — the probe implementation (`_any_regression_pair_exists` + the `"has_regression_facts"` key in `_availability_flags`) was already on `main` from the find-runs-for-target slice (`4964e3a`). This slice nails the contract with tests.

## Source handoff

`agent-comms/handoffs/memory-team-2026-05-26-has-regression-facts.md`

## What changed

Eight new test cases in `tests/unit/memory/test_store.py` exercise the Memory probe that flips `MemoryEntry.has_regression_facts` based on filesystem state under `<store>/regression/pairs/`. Cases enumerate:

1. **Cold store** — no `<store>/regression/pairs/` dir → `False` (plus sanity: `regression/pairs/` is NOT pre-materialized at init; `regression/` itself is, but the deeper `pairs/` subdir is born only when Regression writes its first pair).
2. **Empty `pairs/` dir** → `False`.
3. **Run is baseline (left)** of `run_<rid>__run_<other>/` → `True`.
4. **Run is target (right)** of `run_<other>__run_<rid>/` → `True` (positionally agnostic).
5. **Run in three pairs** (mix left/right positions) → `True`, idempotent.
6. **Pair dir without `regression_facts.json`** → `False`. The "file is the truth, directory is the index" guard (simulates crashed mid-write or hand-deleted file).
7. **Pairs exist for other runs only** → `False`. Confirms the `run_<rid>` substring needle does NOT accidentally match unrelated pair names.
8. **Tombstoned run with a stale matching pair file** → `True`. Per decision §C.1, Memory reflects what's on disk; tombstone fail-hard is Regression's territory (availability ≠ usability).

All test stubs use `{"schema_version": 1}` — the probe checks file *existence* only, never parses. Private helper `_write_stub_regression_facts(pair_dir)` lives in the test module.

## Verification steps for Manual Test

### 1. Test gate is green on merged main

```bash
git -C /home/yjshin/dev/aispace/Nove-Test fetch origin
git -C /home/yjshin/dev/aispace/Nove-Test checkout main
uv run pytest -q tests/unit/memory/test_store.py
# expect: 33 passed (was 25 before this slice; +8 new)
```

### 2. Probe behavior end-to-end (manual smoke)

The probe runs every time you read a `MemoryEntry` (via `list_run_history` or any code path that calls `_availability_flags`). Easiest exercise:

```bash
mkdir -p /tmp/novetest-verify-memory-hrf && cd /tmp/novetest-verify-memory-hrf
uv --project /home/yjshin/dev/aispace/Nove-Test run python3 <<'PY'
import tempfile, json
from pathlib import Path
from novetest.memory.project_store import create_project_store, get_project_store_state
from novetest.memory.store import store_run_evidence, list_run_history
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult

ws = Path(tempfile.mkdtemp()) / "ws"; ws.mkdir()
store_init = create_project_store(ws)
store = get_project_store_state(store_init.path)

ref = RunReference(run_id="a"*32, created_at=1748246400)
rec = RunRecord(
    run_reference=ref, target_expression="tests/", target_type="dir",
    engine_name="pytest", engine_version="8.2.0", ecosystem="python",
    status="passed", started_at=1748246400, completed_at=1748246401,
    test_results=(TestResult(node_id="t::x", outcome="passed", duration_ms=10),),
    artifact_paths={},
)
store_run_evidence(store, rec)

entries = list_run_history(store)
print("before pair:", entries[0].has_regression_facts)  # expect False

# Now manually plant a pair dir with the run in BASELINE position
pair_dir = store.path / "regression" / "pairs" / f"run_{ref.run_id}__run_{'b'*32}"
pair_dir.mkdir(parents=True)
(pair_dir / "regression_facts.json").write_text('{"schema_version": 1}')

entries = list_run_history(store)
print("after pair:", entries[0].has_regression_facts)  # expect True
PY
```

Expect: `before pair: False`, then `after pair: True`. If both print `False`, the probe didn't pick up the planted pair (the probe substring-matches `run_<id>` anywhere in the pair directory name).

### 3. Negative cases worth probing

- **Pair dir exists but JSON missing** — `True` should flip to `False`:
  ```bash
  rm /tmp/novetest-verify-memory-hrf/ws/.novetest/regression/pairs/run_aaa.../regression_facts.json
  # Re-run list_run_history → has_regression_facts: False
  ```
- **Wrong run_id in pair name** — should NOT match:
  ```bash
  # Put a pair under run_ddd...__run_eee... (different IDs)
  # Re-run list_run_history for the "a"*32 run → has_regression_facts stays False
  ```

## Critical edge cases worth probing

- **Substring greediness**: `run_aaa...` should NOT match `run_aaaaa...` (longer ID). The probe uses literal `run_<rid>` substring; covered by test case 7 but worth eyeballing live if you suspect future drift.
- **Tombstone interaction**: per decision §C.1, Memory deliberately does NOT fail-hard on a tombstoned run with stale pair facts — it reports `True`. The Regression engine layer fails hard. If you call `compare_runs` on a tombstoned run and the cached pair file exists, you should still see `REASON_RUN_TOMBSTONED` (verified in the parallel verification doc for the regression-compare-runs-impl slice).
- **JSON content tolerance**: the probe never parses the JSON — `{"schema_version": 99999}` or even `{"garbage": true}` all flip the flag to `True`. The probe is existence-only. Schema validation lives one layer up in `get_regression_facts`.

## Notes that weren't obvious during merge

- **No merge conflict on this slice.** Clean fast-forward `e80e3cf → 2de7bea`. The WORKLOG conflict happened on the *subsequent* regression-compare-runs-impl rebase, not here.
- **Pre-slice test baseline drift.** The handoff brief mentioned `345` collected; actual baseline on `e80e3cf` was `348+3`. The +8 delta is what matters — the absolute number moved because of accumulated activation cycles. PM may want WORKLOG to reflect the absolute `353+3` post-slice.
- **No `src/` diff.** This slice is pure test surface. mypy delta = 0 (still 52 files post-merge of this slice; the `+5` happens on the next regression-engine slice).

## DoD bullets to check (PM-tracked, not for Manual Test to tick)

**None close from this slice alone.** Per the task brief, Phase 3 `delivery-phasing.md` DoD bullets close when CLI verbs ship (next cycle). This slice closes the Memory↔Regression availability loop on the test side so that once the engine writes real pairs, `memory show <run_id>` / `inspect <run_id>` envelopes reflect Regression activity through `has_regression_facts` correctly.
