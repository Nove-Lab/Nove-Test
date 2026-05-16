---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: coverage-show-diff
related:
  - handoffs/orchestration-team-2026-05-16-coverage-show-diff.md
  - tasks/orchestration-team-2026-05-16-coverage-show-diff.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - history/2026-05-16-coverage-cli-wiring.md
---

# Verification request: `coverage show` + `coverage diff` CLI verbs

## Merged commit

- **Hash:** `50c9170` (fast-forward from `3df9ec2`; clean linear history).
- **Title:** `feat(orchestration): implement coverage show + coverage diff CLI verbs`
- **Scope:** Two new real CLI verbs replace the stubs:
  - `novetest coverage show <run_id>` — envelope `data.coverage_outcome` block, `kind: "fact-set" | "unavailable"`, mirroring the `run --coverage` shape from the previous cycle.
  - `novetest coverage diff <run_id_a> <run_id_b>` — envelope `data.coverage_delta` block, `kind: "delta" | "unavailable"`, carrying `before_summary`, `after_summary`, `files_added`, `files_removed`, `file_deltas`.
  - Both share a `_resolve_run_reference` helper for run-id lookup and a typed not-found error path (`errors[0].code == "not-found"`, exit 2).
- **Closes Phase 2 DoD #2** (the `coverage diff` verb mentioned in `delivery-phasing.md`).

## Source handoffs consumed

- `agent-comms/handoffs/orchestration-team-2026-05-16-coverage-show-diff.md` — single handoff, single commit.

## Merge notes

- **No conflicts.** Base commit (`3df9ec2`) matched current main HEAD; clean fast-forward.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration` → **277 passed** (265 post-stub-drop baseline + 12 new), `uv run mypy --strict` → **clean** (49 source files). Matches handoff numbers exactly.
- **Diff scope:** `src/novetest/cli/app.py` + 3 test files + WORKLOG + handoff. No `coverage/**` engine code, no `pyproject.toml`, no `decisions/**` touches.

## Verification steps for Manual Test

Setup mirrors the prior coverage-cli-wiring smoke (you need two persisted coverage runs to exercise both `show` and `diff`):

```sh
cd /tmp && rm -rf coverage-show-diff-smoke
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-coverage coverage-show-diff-smoke
cd coverage-show-diff-smoke
uv run --with /home/yjshin/dev/Nove-Test novetest init
# First coverage run
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' \
  novetest run --coverage tests/ --output json > /tmp/run-A.json
# Second coverage run (same fixture → equal summaries, good baseline for "no delta")
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' \
  novetest run --coverage tests/ --output json > /tmp/run-B.json
RUN_A=$(python3 -c "import json; print(json.load(open('/tmp/run-A.json'))['data']['memory_entry']['run_reference']['run_id'])")
RUN_B=$(python3 -c "import json; print(json.load(open('/tmp/run-B.json'))['data']['memory_entry']['run_reference']['run_id'])")
```

### Scenario 1 — `coverage show <run_id>` happy path (fact-set)

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest coverage show "$RUN_A" --output json | python3 -m json.tool
```

Assert:
- Exit `0`.
- `data.coverage_outcome.kind == "fact-set"`.
- `data.coverage_outcome.mapping_granularity == "per-test"`.
- `data.coverage_outcome.summary.percent_covered ≈ 86.67`.
- `data.coverage_outcome.run_reference.run_id == $RUN_A`.

### Scenario 2 — `coverage diff` happy path (equal summaries)

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest coverage diff "$RUN_A" "$RUN_B" --output json | python3 -m json.tool
```

Assert:
- Exit `0`.
- `data.coverage_delta.kind == "delta"`.
- `data.coverage_delta.before_summary.percent_covered == data.coverage_delta.after_summary.percent_covered` (same fixture twice).
- `data.coverage_delta.files_added == []`.
- `data.coverage_delta.files_removed == []`.
- `data.coverage_delta.file_deltas == []` (no per-file change between identical runs).

### Scenario 3 — `coverage show fake-id` (not-found)

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest coverage show 01FAKE0000000000000000000 --output json
echo "exit=$?"
```

Assert:
- Exit `2`.
- `errors[0].code == "not-found"`.

### Scenario 4 — `coverage diff` with a missing-coverage run

To probe the `kind: "unavailable"` branch, do a run WITHOUT `--coverage` (so the second run has no coverage facts) and diff it against the coverage run:

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest run tests/ --output json > /tmp/run-noncov.json
RUN_NC=$(python3 -c "import json; print(json.load(open('/tmp/run-noncov.json'))['data']['memory_entry']['run_reference']['run_id'])")
uv run --with /home/yjshin/dev/Nove-Test novetest coverage diff "$RUN_A" "$RUN_NC" --output json | python3 -m json.tool
```

Assert: `data.coverage_delta.kind == "unavailable"` with a reason naming which run lacks coverage facts. (Exact wording per `coverage/compare.py`; the test in `tests/unit/cli/test_coverage_cmd.py::test_diff_emits_unavailable_when_either_side_missing` pins the shape.)

### Scenario 5 — Help surface

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest coverage --help
uv run --with /home/yjshin/dev/Nove-Test novetest coverage show --help
uv run --with /home/yjshin/dev/Nove-Test novetest coverage diff --help
```

Assert: `coverage` group lists both `show` and `diff` (no longer stubs); each sub-help shows the run-id positional arg.

## Critical edge cases

1. **Stub drop regression.** The integration test `tests/integration/cli/test_subcommand_stubs.py` lost its `["coverage", "show"]` and `["coverage", "diff"]` parametrize entries. Confirm the stub-list now lists only the verbs that REMAIN stubs (e.g. `inspect`, `replay`, possibly `test`). Eyeball that file post-merge.
2. **Envelope schema unchanged.** `schema == "novetest/v1"`. The `data.coverage_outcome` (on `show`) and `data.coverage_delta` (on `diff`) keys are additive on already-frozen shapes. No `decisions/` entry required per the previous cycle's `coverage-outcome-envelope-shape` decision.
3. **Cross-cycle regression risk.** The previous `novetest run --coverage` scenarios should still pass byte-equivalently. If you have time, re-run Scenario 1 of `2026-05-16-coverage-cli-wiring.md` against the same fixture and confirm the envelope is unchanged.
4. **Inline handler vs workflow-module.** The handoff notes that handler logic was kept inline in `cli/app.py` rather than extracting `orchestration/workflows/coverage.py` — per task spec's ~20-LOC threshold. If you eyeball `cli/app.py`, expect ~15 LOC per verb in the handler body; no separate workflow file is correct.

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-coverage-show-diff.md` with the standard format. The next two slices being merged this cycle (jest-adapter-phase1, macos-universal2-transition) will land separate verification requests — keep findings scoped to coverage-show-diff only.
