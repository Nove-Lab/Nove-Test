---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-20
slug: jest-coverage-real
related:
  - handoffs/run-team-2026-05-20-jest-coverage-wiring.md
  - handoffs/coverage-team-2026-05-20-jest-istanbul-parser.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Verification: jest `--coverage` made real (Run wiring + Istanbul parser)

## Merged commits

Two disjoint slices that together make `novetest run --coverage` against a
jest workspace produce a real `CoverageFactSet`:

- `91bfa29` — `feat(run): wire jest adapter --coverage path + Istanbul artifact`
  (Run half — emits the Istanbul `coverage-final.json` artifact).
- `e01df3c` — `coverage: add Istanbul JSON parser for jest -> CoverageFactSet`
  (Coverage half — parses it).

main HEAD after this cycle's full merge: `88da33a`.

## Source handoffs consumed

- `handoffs/run-team-2026-05-20-jest-coverage-wiring.md`
- `handoffs/coverage-team-2026-05-20-jest-istanbul-parser.md`

## Merge notes

- Both slices rebased + fast-forwarded onto main. One WORKLOG.md conflict
  (the Coverage slice rebased over the Run slice's WORKLOG entry) resolved
  surgically — newest-on-top ordering only, no code touched.
- The two slices touch disjoint files (Run owns `run/adapters/` + the new
  `jest-basic-coverage` fixture; Coverage owns `coverage/`); no source
  conflict.
- Post-merge full gate on the combined tree: `uv run pytest -q` -> **334
  passed, 3 skipped**; `uv run mypy` -> **clean, 52 source files**.

## Contract confirmed against merged source

- Run adapter: `collect_coverage=True` -> jest invoked with
  `--coverage --coverageReporters=json --coverageDirectory=<native>/coverage`;
  the resulting `coverage-final.json` registered in
  `artifact_paths["coverage_json"]`. `collect_coverage=False` (default) is
  byte-identical to before — no flags, no artifact key.
- Coverage `derive.py`: `record.engine_name == "jest"` routes through
  `parse_istanbul_json`; **pytest keeps `parse_coverage_json`**.
- jest `mapping_granularity` is `aggregate` (jest's default `--coverage`
  has no per-test attribution); branches reported as **zero** (Istanbul's
  branch model does not map onto control-flow arcs); `percent_covered`
  is computed (Istanbul JSON carries no summary block).

## IMPORTANT — Node.js dependency

The jest end-to-end path needs Node.js + `npm install` in the fixture.
This dev box has **no Node.js**, so the two jest coverage integration
tests (`tests/integration/run/test_jest_coverage.py` and
`tests/integration/coverage/test_jest_coverage.py`) **skip** — they are 2
of the 3 skips in the gate above. The full jest-coverage E2E in CI is
covered by the parallel `ci-node-cell` slice (commit `68a4dcb`) and will
be confirmed via GHA observation owned by the Release team post-merge —
see `verifications/2026-05-20-ci-node-cell.md`.

## Verification steps for Manual Test

### A. pytest-coverage NOT regressed (no Node needed — DO THIS)

The new `engine_name == "jest"` dispatch in `derive.py` must not disturb
the pytest path. Confirm a pytest coverage run still yields real facts:

```sh
cp -r tests/fixtures/projects/pytest-coverage/. /tmp/nv-jestcov-smoke/
cd /tmp/nv-jestcov-smoke
novetest init
novetest run --coverage tests/        # run_id at data.memory_entry.entry_id
novetest coverage show <run_id>
```

`coverage show` must return `data.coverage_outcome.kind == "fact-set"`
with `mapping_granularity == "per-test"` and `summary.num_statements > 0`.
(Main Branch already smoke-checked this on the merged tree — the pytest
path is intact — but please reconfirm.)

### B. jest coverage E2E (ONLY if Node.js is available)

If your environment has `node` + `npx` on PATH:

```sh
cp -r tests/fixtures/projects/jest-basic-coverage/. /tmp/nv-jest-smoke/
cd /tmp/nv-jest-smoke
npm install --no-audit --no-fund        # fixture carries no lockfile
novetest init
novetest run --coverage .               # run_id at data.memory_entry.entry_id
novetest coverage show <run_id>
novetest inspect <run_id>
```

Expected for the jest run, `data.coverage_outcome`:
- `kind == "fact-set"`
- `mapping_granularity == "aggregate"` (NOT `per-test` — jest has no
  per-test attribution)
- `summary.num_branches == 0`, `summary.covered_branches == 0`,
  `summary.missing_branches == 0` (jest branches deliberately reported as
  zero — documented limitation, not a bug)
- `summary.num_statements > 0` with `percent_covered` < 100 (the fixture's
  `src/classifier.js` `value < 0` branch is deliberately uncovered)

If you have **no** Node.js: report section B as "skipped — no Node",
matching this box. That is an acceptable `partial` verdict; the CI cell
will cover it.

## Critical edge cases worth probing

- **`collect_coverage=False` path unchanged** — a plain `novetest run`
  against a jest workspace (no `--coverage`) must behave exactly as
  before: no `coverage_json` artifact, `coverage show` -> `unavailable`
  / `missing-derived-facts`.
- **Missing coverage report** — if jest is asked for coverage but the
  `coverage-final.json` does not land, the adapter raises a typed
  `unparseable-output` error (not a silent empty fact-set). Hard to force
  manually; flagged for awareness.
- **Absolute paths** — Istanbul reports absolute source paths; the parser
  relativizes them against the workspace root. In `coverage show` output
  for a jest run, confirm no absolute filesystem path is persisted in any
  `file_path` field.

## Reporting

Write findings to `agent-comms/findings/manual-test-team-2026-05-20-jest-coverage-real.md`.
