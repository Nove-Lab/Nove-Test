---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-05-20
slug: jest-istanbul-parser
related:
  - tasks/run-team-2026-05-20-jest-coverage-wiring.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Task: Istanbul-JSON coverage parser for jest -> CoverageFactSet

## Scope / Mission

Add an Istanbul-`coverage-final.json` parsing path to the Coverage engine
so `novetest run --coverage` against a jest workspace produces a real
`CoverageFactSet` instead of `CoverageUnavailable`.

This is the **Coverage half** of the "make jest coverage real" slice. The
**Run half** (wiring the jest adapter to emit the Istanbul artifact) is a
parallel task — `tasks/run-team-2026-05-20-jest-coverage-wiring.md`. The
two teams work in disjoint files; the cross-team contract below is
**binding** — Run produces exactly this artifact.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-coverage-team.md`
2. `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
   the FROZEN `coverage_facts.json` on-disk shape. Your jest output MUST
   conform: `mapping_granularity` mandatory, `file_path` workspace-
   relative (constraint #6), `*_statements` summary names, branch pairs.
3. `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`
   — the `REASON_*` enum you own in `coverage/results.py`.
4. `src/novetest/coverage/parser.py` — the existing coverage.py parser;
   note `_infer_mapping_granularity` already branches on `engine_name`.
5. `src/novetest/coverage/derive.py` — `derive_coverage_facts` reads
   `record.artifact_paths["coverage_json"]` then calls
   `parse_coverage_json`. THIS is where engine dispatch belongs.
6. `tasks/run-team-2026-05-20-jest-coverage-wiring.md` — the Run half;
   read its "Data contract" section.

## Files to write / modify

- `src/novetest/coverage/parser.py` and/or a new sibling module
  (e.g. `coverage/istanbul_parser.py`) — your call; keep the coverage.py
  parser and the Istanbul parser cleanly separated.
- `src/novetest/coverage/derive.py` — dispatch: for `engine_name ==
  "jest"`, route the `coverage_json` artifact through the Istanbul
  parser; `pytest` keeps the existing path. Keep the dispatch small and
  obvious.
- `tests/unit/coverage/` — unit tests for the Istanbul parser against a
  pinned inline `coverage-final.json` sample (no Node needed).
- `tests/integration/` — an end-to-end test (`novetest run --coverage`
  on the jest fixture -> `CoverageFactSet`). Guard it with the SAME skip
  pattern as `tests/integration/run/test_jest_basic.py`
  (`shutil.which("node")` + fixture `node_modules` present). It consumes
  the fixture `tests/fixtures/projects/jest-basic-coverage/` created by
  the parallel Run slice — pin that path; it will exist post-merge.

## Files NOT to touch

- `src/novetest/run/**` — the Run team wires the jest adapter.
- `src/novetest/orchestration/**`, `src/novetest/cli/**`,
  `src/novetest/memory/**`, `src/novetest/models/**` (consume
  `CoverageFactSet` etc. read-only; the model is frozen).
- `.github/workflows/**`, `pyproject.toml`, `agent-comms/decisions/**`.

## Data contract (PINNED — what Run hands you)

The jest adapter registers, when `collect_coverage=True`:
- artifact key **`coverage_json`** in the Run Record `artifact_paths`
- pointing at an **Istanbul `coverage-final.json`** file.

Istanbul `coverage-final.json` shape — a JSON object keyed by **absolute
file path**, each value:
```jsonc
{
  "path": "/abs/path/to/file.js",
  "statementMap": { "0": { "start": {"line": L, "column": C}, "end": {...} }, ... },
  "fnMap":        { "0": { "name": "...", "decl": {...}, "loc": {...} }, ... },
  "branchMap":    { "0": { "type": "...", "locations": [ {...}, ... ] }, ... },
  "s": { "0": <hitCount>, ... },   // statement hit counts
  "f": { "0": <hitCount>, ... },   // function hit counts
  "b": { "0": [<hit>, <hit>], ... } // branch hit counts (per location)
}
```

Conformance requirements when building the `CoverageFactSet`:
- **`file_path` MUST be workspace-relative** (decision 2026-05-15
  constraint #6). Istanbul paths are ABSOLUTE — convert them. The
  workspace root is reachable from the Run Record (the run's test
  target / workspace path); `derive.py` already has the record.
- **`mapping_granularity`**: jest's default `--coverage` does NOT
  attribute coverage to individual tests — it merges per-run. Pick the
  granularity that honestly reflects this (`aggregate`, or
  `per-test-file` if you can defensibly justify it from jest's behavior)
  and document the choice + reasoning in the handoff. `line_contexts`
  stays empty for any granularity coarser than `per-test` (constraint
  #5). If you are unsure which value is correct, raise a `questions/`
  file rather than guessing.
- **Statements**: Istanbul tracks statements, not coverage.py "lines".
  Map Istanbul statement hits onto the `executed_lines` / `missing_lines`
  / summary `*_statements` fields as faithfully as the format allows;
  derive line numbers from `statementMap[].start.line`.
- **Branches**: map `branchMap` + `b` onto `executed_branches` /
  `missing_branches` `[from_line, to_line]` pairs where the format
  permits; where Istanbul's branch model does not cleanly map, treat as
  zero branches rather than fabricating arcs — document the limitation.
- `percent_covered` — compute from Istanbul counts; document the formula.
- The resulting `coverage_facts.json` is read back by `get_coverage_facts`
  and projected to the frozen `coverage_outcome` envelope by Orchestration
  — so it MUST round-trip through the frozen on-disk schema.

If the Istanbul -> frozen-schema mapping forces a `schema_version` bump or
a new `mapping_granularity` value, STOP and raise a `questions/` file —
that requires a decision update, not a unilateral change.

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green (Node-dependent integration test skips
  cleanly without Node).
- `uv run mypy` — clean.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code. You may recruit specialists for Istanbul-format research.

## Reporting

Write `agent-comms/handoffs/coverage-team-2026-05-20-jest-istanbul-parser.md`.
Append a `WORKLOG.md` entry (this slice touches `src/` + `tests/`), run
`python3 tools/regen_comms_index.py`, stage `WORKLOG.md` + comms +
`INDEX.md` with source.

**DoD bullets believed closed:** none — this is Phase 2.5 infra, not a
`delivery-phasing.md` DoD bullet. State "none" explicitly. In the handoff,
document your `mapping_granularity` choice for jest and any Istanbul ->
frozen-schema mapping limitations.
