---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-20
slug: jest-istanbul-parser
related:
  - tasks/coverage-team-2026-05-20-jest-istanbul-parser.md
  - tasks/run-team-2026-05-20-jest-coverage-wiring.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Handoff: Istanbul-JSON coverage parser for jest → CoverageFactSet

## Summary

Added an Istanbul `coverage-final.json` parsing path to the Coverage
engine. `novetest run --coverage` against a jest workspace now produces a
real `CoverageFactSet` instead of `CoverageUnavailable`. This is the
**Coverage half** of the "make jest coverage real" slice; the Run half
(`run-team-2026-05-20-jest-coverage-wiring`) is parallel and disjoint.

No `agent-comms/questions/` round was needed — the Istanbul → frozen-schema
mapping fit within the existing `schema_version: 1` and the existing
`mapping_granularity` enum (no schema bump, no new enum value).

## Worktree

- Branch: `coverage-jest-istanbul-parser`
- Path: `/home/yjshin/dev/novetest-jest-istanbul-parser`
- Base: `main` @ `215a941`

## Files

New:
- `src/novetest/coverage/istanbul_parser.py` — `parse_istanbul_json(...)`,
  sibling to the coverage.py `parser.py`, cleanly separated.
- `tests/unit/coverage/test_istanbul_parser.py` — 19 cases, pinned inline
  `coverage-final.json` samples (no Node needed).
- `tests/integration/coverage/__init__.py`
- `tests/integration/coverage/test_jest_coverage.py` — end-to-end
  `run_target_in_store(..., collect_coverage=True)` on the
  `jest-basic-coverage` fixture; Node-guarded skip.

Modified:
- `src/novetest/coverage/derive.py` — small `engine_name == "jest"`
  dispatch routing the `coverage_json` artifact through the Istanbul
  parser; pytest keeps the existing path.
- `tests/unit/coverage/test_derive.py` — +3 jest-path cases.
- `WORKLOG.md`, `agent-comms/` (this handoff + regenerated `INDEX.md`).

`src/novetest/coverage/parser.py`, `models/coverage_fact_set.py`,
`persistence.py` — untouched. The CoverageFactSet model is frozen and
unchanged.

## Verification

- `uv run pytest -q` → **319 passed, 2 skipped**. The 2 skips are the
  Node-dependent integration tests (`test_jest_basic` + the new
  `test_jest_coverage`) — expected with no Node.js on the dev box; they
  skip cleanly.
- `uv run mypy` → **clean**, 51 source files (`--strict`; +1 over baseline
  for `istanbul_parser.py`).

## mapping_granularity choice for jest

**`aggregate`.** jest's default `--coverage` instruments the whole run and
merges per-file coverage with no attribution to individual tests — there
is no per-test, per-test-class, or even per-test-file breakdown in
`coverage-final.json`. `aggregate` is the only honest value. Consequently
`line_contexts` is empty for every file (decision 2026-05-15
constraint #5: empty for any granularity coarser than `per-test`).
`per-test-file` was considered and rejected — jest's default reporter
gives no per-test-file partition of the coverage map, so claiming that
granularity would be unfounded.

## Istanbul → frozen-schema mapping limitations (documented)

1. **Branches are reported as ZERO.** Istanbul's branch model is a branch
   *point* with N path *locations*, each a line/column span — not a
   `[from_line, to_line]` control-flow arc like coverage.py emits. There is
   no faithful conversion without fabricating edges. Per the task's
   explicit escape hatch ("treat as zero branches rather than fabricating
   arcs"), the jest path emits `executed_branches=()`,
   `missing_branches=()`, and summary `num_branches/covered_branches/
   missing_branches = 0`. Fabricated arcs would feed misleading Code
   Locations to Localization (Phase 4), so zero is the safe choice. A
   future slice could revisit if a defensible arc model is designed — that
   would need a `decisions/` update.
2. **`percent_covered` is COMPUTED, not engine-reported.** Istanbul
   `coverage-final.json` carries no summary/totals block, so unlike the
   coverage.py path we cannot echo an engine-reported value (decision
   2026-05-15 constraint #8 assumes coverage.py's summary). Formula:
   `100.0` when there are no statements, else
   `covered_statements / num_statements * 100`, rounded to 2 decimals
   (matching jest's own `% Stmts` text-table convention). Applied
   identically at file and aggregate level.
3. **Statements vs lines.** Istanbul tracks *statements*. The `*_statements`
   summary counters count statements (`num_statements = len(statementMap)`,
   `covered = count of s[idx] > 0`); `executed_lines` / `missing_lines`
   list *line numbers* derived from `statementMap[].start.line`. A line is
   executed when ANY statement starting on it was hit, missing when it
   carries statements but none were hit. This is the same dual-resolution
   coverage.py already has — consistent with the frozen schema.
4. **`excluded_lines` is always empty** — Istanbul `coverage-final.json`
   carries no exclusion data.
5. **`file_path` workspace-relativization.** Istanbul paths are ABSOLUTE.
   `_workspace_relative` relativizes against the Run's workspace root
   (`store.path.parent`, available in `derive.py`); for a file outside the
   workspace it falls back to `os.path.relpath` (a `../`-prefixed relative
   path) so an absolute path is never persisted (constraint #6). Output
   uses POSIX separators for cross-platform determinism.

## Contract-shape surprises

- The Istanbul payload has **no `files`/`totals` wrapper** — the whole JSON
  object *is* the file map, keyed by absolute path. `derive.py` already
  validates `isinstance(payload, dict)`, which covers it. An empty `{}` is
  treated as a valid zero-file report (not corrupt); a value that is not an
  object, or a file entry missing `statementMap`/`s`, raises
  `CoverageJsonParseError` → surfaces as `native-payload-corrupt`.
- The Run-side data contract was honored exactly: artifact key
  `coverage_json` → Istanbul `coverage-final.json`. Engine-format dispatch
  is Coverage-side on `engine_name == "jest"`, as pinned.

## Cross-team dependency note for Main Branch

The integration test `tests/integration/coverage/test_jest_coverage.py`
consumes `tests/fixtures/projects/jest-basic-coverage/`, created by the
parallel Run slice (`run-team-2026-05-20-jest-coverage-wiring`). Until that
fixture merges, the test skips cleanly (its skip guard checks for the
fixture's `node_modules/.bin/jest`, absent when the fixture does not
exist). **Recommend merging both slices together**, or this one after the
Run slice. The two slices touch disjoint files — no merge conflict
expected.

## DoD bullets believed closed

None — this is Phase 2.5 entry infrastructure, not a
`delivery-phasing.md` Phase-2 DoD bullet.
