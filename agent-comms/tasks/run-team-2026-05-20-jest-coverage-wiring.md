---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-20
slug: jest-coverage-wiring
related:
  - tasks/coverage-team-2026-05-20-jest-istanbul-parser.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Task: wire the jest adapter's `--coverage` path + emit the Istanbul artifact

## Scope / Mission

Turn the jest adapter's `collect_coverage` kwarg from the current no-op
into a real coverage run. When `collect_coverage=True`, jest must produce
an Istanbul `coverage-final.json` and the adapter must register it as a
native artifact so the Coverage engine can derive Coverage Facts from it.

This is the **Run half** of the "make jest coverage real" slice. The
**Coverage half** (the Istanbul-JSON parser) is a parallel task —
`tasks/coverage-team-2026-05-20-jest-istanbul-parser.md`. The two teams
work in disjoint files; the cross-team contract is pinned below and is
**binding** — do not deviate without a `questions/` round.

Companion to last cycle's jest adapter execution slice (commit `e0acce6`).

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-run-team.md`
2. `src/novetest/run/adapters/jest_adapter.py` — the current adapter;
   note `del collect_coverage  # intentionally unwired` (line ~66) and
   the docstring's anticipated `--coverage --coverageReporters=json` plan
3. `src/novetest/run/adapters/pytest_adapter.py` — how the pytest adapter
   registers its `coverage_json` artifact key (the key you must match)
4. `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
   constraint #6: adapters MUST emit workspace-relative `file_path`s
5. `tests/fixtures/projects/jest-basic/` — the existing jest fixture you
   built last cycle; the new coverage fixture mirrors its layout

## Files to write / modify

- `src/novetest/run/adapters/jest_adapter.py` — wire `collect_coverage`.
- `tests/fixtures/projects/jest-basic-coverage/` — NEW jest SuT fixture
  (per `delivery-phasing.md` Phase 2 fixture list: "`jest-basic-coverage/`
  (per-file degraded)"). A small `package.json` declaring jest in
  devDependencies, one or two source files, and tests that exercise them
  so Istanbul produces non-trivial coverage. Deterministic, isolated, no
  `novetest` imports. Apply the same `node_modules` gitignore hygiene as
  `jest-basic/`.
- `tests/unit/run/adapters/test_jest_adapter.py` (or the existing jest
  adapter test module) — cover the coverage-on path. Guard any test that
  needs Node with the same skip pattern as
  `tests/integration/run/test_jest_basic.py` (`shutil.which("node")`).

## Files NOT to touch

- `src/novetest/coverage/**` — the Coverage team owns the parser.
- `src/novetest/orchestration/**`, `src/novetest/cli/**`,
  `src/novetest/memory/**`.
- `.github/workflows/**` — the CI Node.js cell is a parallel Release task
  (`tasks/release-team-2026-05-20-ci-node-cell.md`).
- `pyproject.toml`, `agent-comms/decisions/**`.

## Data contract (PINNED — binding cross-team with Coverage)

When `collect_coverage=True`, the jest adapter MUST:

1. **Add jest coverage flags** to `argv`:
   `--coverage --coverageReporters=json`
   plus `--coverageDirectory=<native_dir>/coverage` so the report lands
   under the per-run artifact directory (NOT the workspace's default
   `<rootDir>/coverage`). Use only the `json` reporter — that is the one
   that produces `coverage-final.json`. Do not add `lcov`/`text`.
2. **Resulting file:** `<native_dir>/coverage/coverage-final.json`
   (jest's `json` coverage reporter always names it `coverage-final.json`).
3. **Register the artifact** in `NativeResult.artifact_paths` under the
   key **`coverage_json`** — the SAME key the pytest adapter uses. The
   Coverage engine's `derive_coverage_facts` looks up
   `record.artifact_paths["coverage_json"]` uniformly; engine-specific
   format dispatch happens Coverage-side on `engine_name`. Only register
   the key when `collect_coverage=True` AND the file was produced.
4. When `collect_coverage=False` (default): behavior is unchanged — no
   coverage flags, no `coverage_json` key. Preserve byte-equivalence of
   the non-coverage path.

**Note on the artifact format:** jest's `json` coverage reporter emits
the *Istanbul* `coverage-final.json` shape (a map keyed by absolute file
path -> per-file `statementMap` / `fnMap` / `branchMap` / `s` / `f` / `b`).
This is a DIFFERENT format from coverage.py's JSON. The Coverage team's
parser dispatches on `engine_name == "jest"` to handle it — you do not
need to transform it; just register the raw file. **Istanbul paths are
absolute**; the Coverage parser converts them to workspace-relative. You
do not need `relative_files`-style config (jest has no equivalent).

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green (Node-dependent tests skip cleanly when
  Node is absent, like `test_jest_basic.py`).
- `uv run mypy` — clean.
- If you have Node locally: `(cd tests/fixtures/projects/jest-basic-coverage
  && npm install --no-audit --no-fund)` then run the adapter with
  `collect_coverage=True` and confirm
  `<native_dir>/coverage/coverage-final.json` is produced and registered.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code.

## Reporting

Write `agent-comms/handoffs/run-team-2026-05-20-jest-coverage-wiring.md`.
Append a `WORKLOG.md` entry (this slice touches `src/` + `tests/`), run
`python3 tools/regen_comms_index.py`, stage `WORKLOG.md` + comms +
`INDEX.md` with source.

**DoD bullets believed closed:** none — this is Phase 2.5 entry infra,
not a `delivery-phasing.md` DoD bullet. State "none" explicitly.

In the handoff, confirm the pinned artifact contract (key `coverage_json`,
file `coverage-final.json`, Istanbul format) so the Coverage team's
parallel slice can rely on it.
