---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-07-04
slug: coverage-compare-engine-guard
related:
  - agent-comms/handoffs/coverage-team-2026-07-03-coverage-compare-engine-guard.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
---

# Verification: coverage-compare-engine-guard (D5 Finding A — Wave 2, 1/3)

## Merged commit

- **`17a61f8`** `coverage: refuse cross-engine pairs in compare_coverage_facts (D5 guard)`
  (rebase of worktree commit `d687bfc` off `7c6ece6` onto main `bbbeafd`; clean rebase, zero conflicts)
- Wave-2 cohort tip (all 3 slices): **`76a4ffb`**

## Source handoff

- `agent-comms/handoffs/coverage-team-2026-07-03-coverage-compare-engine-guard.md`

## Merge gate (combined Wave-2 tip `76a4ffb`, equipped host)

- `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` → **1511 passed / 5 skipped / 0 failed**, 49 snapshots passed (toolchain shim equipped: dotnet 8.0.421 — the chronic dotnet host failure the teams reported does NOT reproduce on an equipped host)
- `env -u PYTHONPATH uv run mypy` → **Success: no issues found in 116 source files**

## What changed (behavior)

`compare_coverage_facts` now refuses cross-engine pairs with a
`kind: "unavailable"` outcome, reason **`"engine-mismatch"`** (same wire
string as Regression's guard). Previously `novetest coverage diff
<pytest_run> <cargo_run>` emitted a silently-meaningless `CoverageDelta`.
Zero CLI changes (JSON + TEXT renderers are reason-generic). Envelope
decision 2026-05-16 amended additively (PM pre-authorized).

## Empirical envelope anchor (dry-run at merged tip — copy-paste observed)

Cross-engine `coverage diff` (real pytest `--coverage` run + in-process
seeded cargo-test facts, exact commands in §Steps):

```
exit code: 0
ok: true
data.coverage_delta: {
 "detail": "baseline engine_name='pytest' != target engine_name='cargo-test'",
 "kind": "unavailable",
 "reason": "engine-mismatch",
 "run_reference": {
  "created_at": 1783094677132,
  "run_id": "<BASELINE pytest run_id>",
  "schema_version": 1
 }
}
```

Pinned facts: exit **0** + `ok: true` (unavailable is NOT a CLI error —
2026-05-16 constraint #3); `run_reference` names the **baseline** side;
`detail` carries BOTH engine names; NO delta fields leak.

## Verification steps for Manual Test

1. **Cross-engine refusal E2E** (mirrors the new integration test):
   ```bash
   REPO=/home/yjshin/dev/Nove-Test; PY=$REPO/.venv/bin/python
   rm -rf /tmp/mt-cov && cp -r $REPO/tests/fixtures/projects/pytest-coverage /tmp/mt-cov
   cd /tmp/mt-cov && $PY -m novetest init && $PY -m novetest run --coverage tests/ > /tmp/mt-run.json
   RUNID=$($PY -c "import json;print(json.load(open('/tmp/mt-run.json'))['data']['memory_entry']['run_record']['run_reference']['run_id'])")
   ```
   Seed a cargo-test fact set in-process (copy the helper from
   `tests/integration/orchestration/test_coverage_cli.py::_seed_cargo_fact_set`,
   pointing `get_project_store_state` at `/tmp/mt-cov/.novetest`), then:
   ```bash
   $PY -m novetest coverage diff $RUNID 01HCARGO00000000000000FACT
   ```
   Expect the envelope anchor above (`data.coverage_delta.reason ==
   "engine-mismatch"`, exit 0, `ok: true`).
2. **Same-engine regression check**: run `--coverage` twice in the same
   workspace, `coverage diff <run1> <run2>` → a normal `CoverageDelta`
   (kind NOT "unavailable"); confirms the guard keys on inequality, not a
   privileged engine.
3. **TEXT mode**: repeat step 1 with `--output text` → renderer shows
   `unavailable (engine-mismatch)` style line, no crash (reason-generic
   rendering claim).
4. **Targeted suite**: `env -u PYTHONPATH uv run pytest -q
   tests/unit/coverage/ tests/integration/orchestration/test_coverage_cli.py`
   → 158+ passed.

## Critical edge cases worth probing

- **Argument-order symmetry**: swap the two run_ids — `detail` should
  follow argument order (baseline first), `run_reference` should follow
  the new baseline (the cargo side).
- **Single-side-missing precedence**: `coverage diff <cross-engine pair
  where one side has no facts>` — the missing side's OWN reason must
  surface BEFORE the engine guard fires (ordering pinned by unit test;
  worth one E2E probe).
- **Top-level `compare` verb**: its `coverage_delta` half shares
  `compare_coverage_facts` → should surface the same refusal; its
  `regression_outcome` half already refused via Regression's own guard —
  both halves of the `compare` envelope should now AGREE on cross-engine
  pairs.

## Notes from merge

- Zero conflicts; slice touches only `coverage/`, coverage tests, and the
  coverage envelope decision — no overlap with the two sibling Wave-2 slices.
- Handoff acceptance bullet #3 (CI matrix 10/10) is post-merge: the
  session gh identity is dispatch-restricted (2026-06-22 gotcha). One
  command for anyone with rights: `gh workflow run ci.yml --ref main`.
