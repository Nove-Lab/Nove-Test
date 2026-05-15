---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-15
slug: pytest-coverage-emission
related: [run-team-2026-05-14-pytest-coverage-emission.md, coverage-team-2026-05-14-coverage-fact-set-foundation.md]
---

# Handoff: pytest adapter — per-test coverage emission

## Worktree

- Branch: `worktree-phase2-pytest-coverage-emission`
- Path: `/home/yjshin/dev/aispace/Nove-Test.worktrees/phase2-pytest-coverage-emission`
- Base commit: `fe28479` (main, `docs: resolve OQ#15 — install script hosting URL`)

## Scope delivered

Phase 2 entry, Run-side slice. Adds opt-in **per-test native coverage
emission** to the pytest adapter: when `collect_coverage=True`, the
`NativeResult` carries `coverage_json` (coverage.py JSON report with
per-line `contexts` map) and `coverage_xml` (Cobertura XML) under
`<artifact_dir>/native/`. This is the raw payload the Coverage engine's
`coverage-fact-set-foundation` slice will consume. CLI / Orchestration
wiring is **not** part of this slice (per task spec).

## Files written / modified

**Modified**
- `src/novetest/run/adapters/pytest_adapter.py` — `run_pytest` gains
  `collect_coverage: bool = False`; new constants `COVERAGE_JSON_FILENAME`,
  `COVERAGE_XML_FILENAME`, `COVERAGE_RC_FILENAME`; helper
  `_write_coverage_rc` emits the per-run `.coveragerc` into `artifact_dir`.
- `pyproject.toml` — dev deps grow `pytest-cov>=5.0` and
  `coverage[toml]>=7.0`. **Run/Release shared territory; flagged here so
  Main Branch & Release are not surprised.**
- `tests/unit/run/conftest.py` — adds `coverage_workspace` fixture.
- `tests/unit/run/adapters/test_pytest_adapter.py` — new tests
  `test_coverage_emission_produces_contexts_and_missing_branches`,
  `test_coverage_missing_plugin_raises_missing_plugin`; existing happy
  path tightened to assert the new keys are absent by default.
- `WORKLOG.md` — top entry appended.
- `uv.lock` — updated by `uv sync` to lock the two new dev deps and
  pull in their transitive deps (coverage 7.x).

**New**
- `tests/fixtures/projects/pytest-coverage/` (`pyproject.toml`,
  `README.md`, `pytest_coverage/__init__.py`,
  `pytest_coverage/classifier.py`, `tests/test_classifier.py`). Three
  branches, `value < 0` deliberately uncovered; 2 passing tests cover 2
  of 3 branches. README documents the contract.

## Data contracts (verbatim — Coverage Team depends on these)

**Native artifact filenames** under `<artifact_dir>/native/`:
- `coverage.json` (coverage.py JSON report)
- `coverage.xml` (Cobertura XML)

**`NativeResult.artifact_paths` new keys** (absolute `Path` at the
adapter layer; Memory rewrites to store-relative strings):
- `"coverage_json"` → `<artifact_dir>/native/coverage.json`
- `"coverage_xml"` → `<artifact_dir>/native/coverage.xml`

The existing keys (`pytest_json_report`, `stdout`, `stderr`) are
preserved unchanged. Default-off behavior is unchanged for Phase 1
callers.

**Per-line contexts map shape** (proven on the fixture):
```json
"contexts": {
  "11": ["tests/test_classifier.py::test_classify_positive|run",
         "tests/test_classifier.py::test_classify_zero|run"],
  "12": ["tests/test_classifier.py::test_classify_positive|run"],
  ...
}
```
Context keys are coverage.py's `<nodeid>|<phase>` (typically `|run`).
Coverage Team should parse permissively: split on `|` and take the
left side as the test nodeid.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **187 passed** (+1
  syrupy snapshot). +3 over the 2026-05-13 baseline of 184 (two new
  coverage tests + the no-default-coverage assertion added to the
  existing happy-path test pulls in one extra success per run).
- `uv run mypy` → **Success: no issues found in 41 source files**
  (under `--strict`).
- Manual smoke against `tests/fixtures/projects/pytest-coverage/` with
  `collect_coverage=True`:
  - `returncode=0`, `artifact_paths` has the 5 expected keys.
  - `coverage.json` `files` map contains `pytest_coverage/classifier.py`.
  - `classifier.py.contexts` is non-empty, keyed by test nodeid.
  - `classifier.py.missing_lines = [16]`,
    `missing_branches = [[13, 16]]` (the deliberate `return "negative"`
    line and its incoming branch).
  - `summary.percent_covered = 80.0`.

## DoD bullets believed closed

**None.** This slice closes **zero** Phase 2 DoD bullets on its own —
the task spec explicitly anticipated this. Each Phase 2 DoD bullet
requires either Coverage Team's engine slice (DoD 1, 2, 3) or
Orchestration's `--coverage` CLI wiring (DoD 1). This slice produces
the *capability* the rest of Phase 2 builds on.

## Open items / surprises

- **`show_contexts` is mandatory, not optional.** `--cov-context=test`
  by itself does NOT emit the per-line `contexts` map into the JSON
  report; you also need `[json] show_contexts = True` in the rc file.
  Locked via the generated `.coveragerc`. Documented in the adapter's
  `_write_coverage_rc` docstring.
- **Plugin name is `pytest_cov`, not `pytest-cov`.** Under
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` both `pytest_jsonreport` and
  `pytest_cov` must be loaded explicitly via `-p`.
- **`--cov=.` measures everything under cwd**, including `tests/`. The
  Coverage engine is the right place to filter / scope. Adapter stays
  ecosystem-neutral; no auto-detection of source packages.
- **pytest-xdist + `--cov` merge handling is deferred.** The
  engine-adapters doc flags it; the task asked us not to solve it
  here. Noted as an open seam.
- **`pyproject.toml` dev-dep additions** (`pytest-cov>=5.0`,
  `coverage[toml]>=7.0`) — Phase 1 precedent (Run added
  `pytest-json-report`). PM treats `pyproject.toml` as Run/Release
  shared territory. Resolved transitive: `coverage` 7.x and
  `pytest-metadata` 3.x pulled in via `uv sync`.
- **Run engine entrypoints (`engine.execute`, `engine.execute_with_engine_context`)
  do NOT yet plumb `collect_coverage` through.** That is deliberate —
  Orchestration owns when/how to enable coverage; their later slice
  will add the kwarg pass-through. Adapter-layer plumbing is the
  smallest correct increment for this task.
- **`coverage.json` paths are workspace-relative** thanks to
  `relative_files = True` in the generated rc. Memory / Coverage do
  not have to strip absolute build prefixes.
- **coverage.py's intermediate `.coverage` SQLite cache** defaults to
  cwd (= the SuT workspace) and would pollute the user's repo.
  Pinned via `[run] data_file = <artifact_dir>/.coverage` in the
  generated rc; test asserts the workspace stays clean. Caught
  during commit prep, not during initial implementation — flag for
  the polyglot adapters: every coverage backend likely has a similar
  "intermediate file in cwd" footgun.
- **No `coverage_facts.json` shape change is needed** based on what
  this slice emits. If Coverage Team finds a friction point with the
  raw `contexts` key format (`<nodeid>|<phase>`), flag it to PM and
  we'll iterate.

## Worklog entry (paste)

```
## 2026-05-15 — phase2 / pytest-coverage-emission

- Landed: `src/novetest/run/adapters/pytest_adapter.py` grows a `collect_coverage: bool = False` opt-in. When True, `run_pytest` writes a per-run `.coveragerc` into `artifact_dir` (`[run] relative_files = True`, `branch = True`; `[json] show_contexts = True`, `pretty_print = True`) and appends the canonical pytest-cov flags to argv: `-p pytest_cov`, `--cov=.`, `--cov-branch`, `--cov-context=test`, `--cov-config=<rc>`, `--cov-report=json:<...>/native/coverage.json`, `--cov-report=xml:<...>/native/coverage.xml`. The returned `NativeResult.artifact_paths` adds `coverage_json` and `coverage_xml` keys (absolute `Path`s, exactly as the existing `pytest_json_report` / `stdout` / `stderr` keys; Memory will rewrite to store-relative on persist). Missing-plugin path: when `collect_coverage=True` AND pytest aborts before writing the JSON report AND the stderr mentions `pytest_cov`, the adapter raises `AdapterInvocationError(kind="missing-plugin", install_hint="pip install pytest-cov")`. Missing post-condition: when `collect_coverage=True` AND the JSON report exists but `coverage.json` does not, the adapter raises `AdapterInvocationError(kind="unparseable-output")` rather than returning a half-populated `NativeResult`. New fixture `tests/fixtures/projects/pytest-coverage/` with `pytest_coverage/classifier.py` (three branches; `value < 0` deliberately uncovered) + 2 passing tests, plus README documenting the contract. `pyproject.toml` dev deps grow `pytest-cov>=5.0` and `coverage[toml]>=7.0`. Tests: `tests/unit/run/conftest.py` gains `coverage_workspace`; `tests/unit/run/adapters/test_pytest_adapter.py` gains `test_coverage_emission_produces_contexts_and_missing_branches` (asserts `coverage_json`/`coverage_xml` artifacts land on disk, `.coveragerc` lives in `artifact_dir` and NOT in the workspace, the per-line `contexts` map is non-empty and references the fixture's test nodeids, and the deliberate gap shows up in `missing_lines` or `missing_branches`) plus `test_coverage_missing_plugin_raises_missing_plugin` (stubs `pytest_cov` on `PYTHONPATH` to raise on import; asserts the typed error surfaces). The Phase 1 happy-path test was tightened to assert the new keys are *absent* by default.
- Verified: `uv run pytest -q tests/unit tests/integration` → 187 passed (+1 syrupy snapshot, +3 over the 2026-05-13 baseline of 184: two new coverage tests plus the no-prior-test inline assertion gain). `uv run mypy` → clean (41 source files, `--strict`). Manual smoke against `tests/fixtures/projects/pytest-coverage/` confirmed:  `returncode=0`; `artifact_paths={pytest_json_report, stdout, stderr, coverage_json, coverage_xml}`; `coverage.json` `files` contains `pytest_coverage/classifier.py` with `contexts = {"11": ["tests/test_classifier.py::test_classify_positive|run", "tests/test_classifier.py::test_classify_zero|run"], ...}`, `missing_lines=[16]`, `missing_branches=[[13, 16]]`, summary `percent_covered=80.0`.
- Left open: **No Phase 2 DoD bullet in `delivery-phasing.md` closes on this slice alone** — DoD 1 (`novetest test --coverage` emits per-test coverage) also needs Coverage Team's `derive_coverage_facts` slice and Orchestration's `--coverage` CLI wiring; DoD 2/3 (coverage diff, inspect coverage section) are downstream of those. This slice produces the *raw native payload* that those slices consume. pytest-xdist + `--cov` merge handling is intentionally out of scope per the task spec — noted as an open seam.
- Gotcha: `--cov-context=test` ALONE is insufficient — coverage.py only writes the per-line `contexts` map into `coverage.json` when `show_contexts = True` is in the JSON-report section of the rc file. We generate the rc under `artifact_dir`, never inside the SuT workspace, so users' own coverage config is never mutated. The plugin name for `-p` is `pytest_cov` (module name), not `pytest-cov` (package name). With `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` we must load both `pytest_jsonreport` AND `pytest_cov` explicitly. With `--cov=.` we measure cwd-relative everything; that picks up the fixture's own `tests/` too — downstream Coverage filtering is the Coverage engine's concern, not the adapter's. `pyproject.toml` dev-deps grew two new entries (`pytest-cov>=5.0`, `coverage[toml]>=7.0`); PM treats `pyproject.toml` as Run/Release shared territory — flagging for Main Branch & Release.
- Next: Coverage Team's `coverage-fact-set-foundation` slice can consume `artifact_paths['coverage_json']` directly from a persisted Run Record. Orchestration's later slice adds the `--coverage` CLI flag and threads `collect_coverage=True` through `run/execute` (currently only `run_pytest` exposes it; `run/engine.execute` does not yet plumb the flag — that's deliberate, Orchestration owns when/how to enable coverage and will add the kwarg pass-through then).
```
