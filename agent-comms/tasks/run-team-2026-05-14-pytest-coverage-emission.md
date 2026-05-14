---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-14
slug: pytest-coverage-emission
related: [coverage-team-2026-05-14-coverage-fact-set-foundation.md]
---

# Task: pytest adapter — per-test coverage emission

## Scope / Mission

Phase 2 (Coverage Structuring) entry. Extend the pytest adapter so a run can
emit **per-test native coverage artifacts** (`coverage.json` with the per-line
`contexts` map, plus Cobertura XML for interop) into the run's `native/`
artifact directory, and register those paths in `NativeResult.artifact_paths`.
This is the raw payload the Coverage engine consumes — your slice produces the
*capability*; Coverage's parallel slice consumes it; Orchestration's later slice
wires the `--coverage` CLI flag. Do **not** touch CLI or orchestration here.

You also own the new `pytest-coverage/` fixture project.

## Pre-flight reading

1. `CLAUDE.md` + your charter (`.claude/agents/novetest-run-team.md`)
2. `design/implementation-plan/engine-adapters.md` §1 "Python + pytest" — esp. the **Coverage emission** subsection (canonical flags) and **Edge cases** (`show_contexts`, version skew, Windows path normalization)
3. `design/implementation-plan/delivery-phasing.md` Phase 2
4. `src/novetest/run/adapters/pytest_adapter.py` — current `run_pytest`
5. `src/novetest/run/normalizer.py` — how `artifact_paths` flows into `RunRecord`
6. `src/novetest/models/run_record.py` — `artifact_paths` is `dict[str, str]`, name → Project-Store-relative path

## Files to write / modify

- `src/novetest/run/adapters/pytest_adapter.py` — add coverage emission
- `tests/unit/run/` — adapter unit tests for the new behavior
- `tests/fixtures/projects/pytest-coverage/` — new fixture (see Data contracts)
- `pyproject.toml` — add `pytest-cov` and `coverage[toml]>=7.0` to **dev deps**, minor-pinned (Phase 1 precedent: Run added `pytest-json-report`; PM treats `pyproject.toml` as Run/Release shared territory). Flag this addition prominently in your handoff so Main Branch and Release are not surprised.

## Files NOT to touch

- `src/novetest/coverage/**`, `src/novetest/models/coverage_fact_set.py` — Coverage Team
- `src/novetest/cli/**`, `src/novetest/orchestration/**` — Orchestration Team
- `src/novetest/memory/**`, `src/novetest/models/run_record.py` — Memory Team
- `.github/workflows/**`, `scripts/install.sh` — Release Team
- `tests/fixtures/projects/pytest-basic|pytest-failing|empty-no-engine/` — leave as-is

## Data contracts (pinned — Coverage Team depends on these verbatim)

**Native artifact filenames**, written under `<artifact_dir>/native/`:
- `coverage.json` — coverage.py JSON report
- `coverage.xml` — Cobertura XML (interop safety net)

**`NativeResult.artifact_paths` new keys** (absolute `Path` at the adapter layer;
Memory rewrites to store-relative strings, exactly as for the existing keys):
- `"coverage_json"` -> `<artifact_dir>/native/coverage.json`
- `"coverage_xml"` -> `<artifact_dir>/native/coverage.xml`

Keep the existing keys (`pytest_json_report`, `stdout`, `stderr`) unchanged.

**Coverage emission flags** (per engine-adapters.md §1): invoke pytest with
`--cov=<scope>`, `--cov-branch`, `--cov-context=test`,
`--cov-report=json:<...>/native/coverage.json`,
`--cov-report=xml:<...>/native/coverage.xml`.

**Load-bearing quirk — the emitted `coverage.json` MUST contain the per-line
`contexts` map.** coverage.py only writes `contexts` into the JSON report when
`show_contexts` is enabled. `--cov-context=test` alone is not sufficient. The
robust, non-invasive mechanism: generate a `.coveragerc` (e.g. in the artifact
dir) with `[json] show_contexts = True` and `[run] relative_files = True`, and
pass it via `--cov-config=<path>`. Do **not** modify the target project's own
config. Recruit `python-pro` / `debugger` if coverage.py behavior surprises you.

**`pytest-coverage/` fixture requirements:** deterministic, small, isolated,
self-contained, never imports `novetest`. It MUST contain at least one function
with a branch the test suite **deliberately leaves uncovered**, so Coverage's
`missing_lines` / `missing_branches` extraction is exercised end-to-end. Fixture
plugins run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` — load `pytest_jsonreport`
and `pytest_cov` explicitly via `-p` as the current adapter already does for
json-report.

## Scope boundaries

- Coverage emission should be **opt-in at the function-argument level** (e.g. a
  `collect_coverage: bool` parameter on `run_pytest` / the engine entrypoint),
  defaulting off so existing Phase 1 runs are unchanged. The CLI `--coverage`
  flag is Orchestration's later slice — do not add it.
- If coverage is requested but `pytest-cov` is missing from the resolved
  interpreter, raise `AdapterInvocationError` with `kind="missing-plugin"` and a
  text `install_hint`, consistent with the existing json-report handling.
- pytest-xdist merge handling (`--cov` + xdist) is **out of scope** — note it as
  an open item if you see the seam, do not solve it now.

## Verification commands (must pass before handoff)

- `uv run pytest -q tests/unit tests/integration`
- `uv run mypy` (must stay `--strict` clean)
- Manual smoke: run the adapter against `tests/fixtures/projects/pytest-coverage/`
  with coverage enabled; confirm `native/coverage.json` exists and that at least
  one file entry carries a non-empty `contexts` map keyed by test nodeid, and
  that the deliberately-uncovered branch shows up in `missing_branches`.

## Reporting

Write `agent-comms/handoffs/run-team-2026-05-14-pytest-coverage-emission.md`
with the standard sections. In **"DoD bullets believed closed"**: expect this
slice closes **none** of the Phase 2 DoD bullets on its own (they all also need
Coverage's engine slice and/or Orchestration's `--coverage` wiring) — say so
explicitly. Call out the `pyproject.toml` dev-dep additions and any coverage.py
`show_contexts` quirks under "Open items / surprises". If you hit anything that
needs a `coverage.json` shape change Coverage should know about, note it so PM
can fold it into the data-contract decision.
