---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-20
slug: jest-coverage-wiring
related:
  - tasks/run-team-2026-05-20-jest-coverage-wiring.md
  - tasks/coverage-team-2026-05-20-jest-istanbul-parser.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Handoff: wire the jest adapter's `--coverage` path + emit the Istanbul artifact

## Summary

The jest adapter's `collect_coverage` kwarg is now a real coverage run.
When `collect_coverage=True`, jest is invoked with
`--coverage --coverageReporters=json --coverageDirectory=<...>/native/coverage`,
and the resulting Istanbul `coverage-final.json` is registered in
`NativeResult.artifact_paths` under the `coverage_json` key. When
`collect_coverage=False` (default) the path is byte-identical to before.

This is the **Run half** of the "make jest coverage real" slice; the
Coverage half (`tasks/coverage-team-2026-05-20-jest-istanbul-parser.md`)
is a parallel task in disjoint files.

## Worktree

- **Path:** `/home/yjshin/dev/novetest-jest-coverage-wiring`
- **Branch:** `worktree-run-team-jest-coverage-wiring`
- **Base commit:** `215a941` (main)

## Files written / modified

### Modified
- `src/novetest/run/adapters/jest_adapter.py` — removed `del collect_coverage`;
  added `COVERAGE_DIR_NAME` / `COVERAGE_FINAL_FILENAME` constants; `argv`
  extended with the three jest coverage flags when `collect_coverage=True`;
  post-run guard raises `AdapterInvocationError(kind="unparseable-output")`
  when coverage was requested but `coverage-final.json` did not land;
  `artifact_paths` built as a dict and gets the `coverage_json` key only
  when coverage was requested AND the file exists. Module + function
  docstrings updated. `__all__` extended.
- `tests/unit/run/adapters/test_jest_adapter.py` — `_make_stub_subprocess`
  grew a `write_coverage` param; new `_sample_istanbul_payload()` helper;
  obsolete `test_collect_coverage_kwarg_is_silently_no_op_this_slice`
  replaced by 3 cases (off-path adds no flags / on-path adds flags +
  registers artifact / missing coverage file → unparseable-output).
- `tests/unit/run/conftest.py` — new `jest_basic_coverage_workspace` fixture.

### New
- `tests/fixtures/projects/jest-basic-coverage/` — `package.json`,
  `src/classifier.js` (3 branches, `value < 0` deliberately uncovered),
  `__tests__/classifier.test.js` (2 passing tests, 2 of 3 branches),
  `README.md`, `.gitignore` (excludes `node_modules/`).
- `tests/integration/run/test_jest_coverage.py` — real `npx jest --coverage`
  against the new fixture; skips when Node / fixture `node_modules` absent.

## Pinned artifact contract (confirmed for the Coverage team)

The Run side delivers exactly what `tasks/...-jest-coverage-wiring.md`
pinned — the Coverage team's parallel slice can rely on this:

- **Key:** `coverage_json` in `NativeResult.artifact_paths` (same key the
  pytest adapter uses).
- **File:** `<native_dir>/coverage/coverage-final.json`.
- **Format:** Istanbul raw JSON — a map keyed by **absolute** source file
  path → per-file `statementMap` / `fnMap` / `branchMap` / `s` / `f` / `b`.
  The adapter registers the raw file untouched; absolute→workspace-relative
  conversion is Coverage-side.
- **Reporter:** `json` only — no `lcov`/`cobertura` (per the pinned task).
- The key is registered **only** when `collect_coverage=True` AND the file
  was produced; absent file → typed `unparseable-output` error.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **300 passed, 2 skipped**
  (the 2 skips are `test_jest_basic` + `test_jest_coverage`, both
  Node-dependent — expected to skip with no Node.js locally or in CI).
- `uv run mypy` → **clean** (50 source files, `--strict`).
- Real `npx jest --coverage` smoke: not run locally (no Node.js on the
  dev box) — the integration test's skip guard is the deliberate fallback.

## Worklog entry

Appended to `WORKLOG.md` top — `2026-05-20 — phase2.5 / jest-coverage-wiring`.

## DoD bullets believed closed

**None.** This is Phase 2.5 entry infra, not a `delivery-phasing.md` DoD
bullet (the task states "none" explicitly). It unblocks the Coverage
team's `jest-istanbul-parser` slice.

## Open items / surprises

- jest's `--coverage` defaults to `<rootDir>/coverage` inside the SuT
  workspace; `--coverageDirectory` is mandatory to keep the report under
  the per-run artifact dir. Handled.
- `engine-adapters.md` §2's jest coverage snippet lists `cobertura` + `lcov`
  reporters too; this slice ships **only `json`** per the task's pinned
  contract. If a later slice wants the portable fallbacks, that is an
  additive change (extra `--coverageReporters=` flags + extra artifact keys).
- Merge-conflict surface: disjoint from the parallel Coverage / Release /
  Orchestration slices this cycle — Run owns `run/adapters/`, `tests/.../run/`,
  and the new fixture dir; no shared files.
