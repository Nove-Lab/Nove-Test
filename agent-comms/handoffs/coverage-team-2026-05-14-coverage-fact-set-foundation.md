---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-15
slug: coverage-fact-set-foundation
related: [coverage-team-2026-05-14-coverage-fact-set-foundation.md, run-team-2026-05-14-pytest-coverage-emission.md]
---

# Handoff: Coverage engine foundation — CoverageFactSet model + four internal interfaces

## Worktree

- Path: `../Nove-Test.coverage`
- Branch: `worktree-phase2-coverage-foundation`
- Base commit: `fe28479` (main, `docs: resolve OQ#15 — install script hosting URL`)

## Files written / modified

### Source
- `src/novetest/models/coverage_fact_set.py` — new (persisted entity: `CoverageFactSet` + `CoverageSummary` + `FileCoverage`, `@dataclass(slots=True, frozen=True)`, v1 `schema_version`, hand-rolled `to_dict`/`from_dict`, `_require_keys` helper, mirrors Memory Team's model style).
- `src/novetest/models/__init__.py` — re-exports the three new dataclasses alongside the existing four.
- `src/novetest/coverage/__init__.py` — public engine API re-exports.
- `src/novetest/coverage/results.py` — new (`CoverageUnavailable` discriminator + reason-code constants).
- `src/novetest/coverage/persistence.py` — new (load-bearing path helpers + `write_coverage_facts` / `read_coverage_facts`).
- `src/novetest/coverage/parser.py` — new (coverage.py 7.x JSON → `CoverageFactSet`; `CoverageJsonParseError`).
- `src/novetest/coverage/derive.py` — new (`derive_coverage_facts`).
- `src/novetest/coverage/retrieval.py` — new (`get_coverage_facts`).
- `src/novetest/coverage/compare.py` — new (`compare_coverage_facts` + `CoverageDelta` + `FileCoverageDelta`).
- `src/novetest/coverage/availability.py` — new (`check_coverage_availability` + `CoverageAvailability`).

### Tests
- `tests/unit/models/test_coverage_fact_set.py` — 17 cases (round-trip, granularity validation, frozen, schema-version policing).
- `tests/unit/coverage/conftest.py` — fixtures (`initialized_store`, `sample_coverage_payload`, `sample_run_reference`, `make_run_record`, `seed_run_with_coverage`, `seed_fact_set`).
- `tests/unit/coverage/fixtures/sample_coverage.json` — checked-in parser fixture (coverage.py 7.x payload with `show_contexts=True`, two files, one deliberately-uncovered branch).
- `tests/unit/coverage/test_parser.py` — 16 cases.
- `tests/unit/coverage/test_persistence.py` — 7 cases (load-bearing path + round-trip + overwrite + JSON shape).
- `tests/unit/coverage/test_derive.py` — 9 cases (success + every unavailable path + idempotency).
- `tests/unit/coverage/test_retrieval.py` — 4 cases (cache hit / missing facts / missing run / no auto-derive).
- `tests/unit/coverage/test_compare.py` — 10 cases (per-file diff + file set diff + granularity carriage + unavailable propagation + delta entity round-trip).
- `tests/unit/coverage/test_availability.py` — 7 cases including the Memory-flag-lockstep test across the three meaningful states.
- `tests/unit/coverage/.gitkeep` — removed.

### Comms / log
- `WORKLOG.md` — phase2 / coverage-engine-foundation entry appended.
- `agent-comms/handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md` — this file.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **256 passed** (185 prior + 71 new + 1 syrupy snapshot).
- `uv run mypy` → **clean**, 49 source files under `--strict`.

## Worklog entry text

(See `WORKLOG.md` top entry — `2026-05-15 — phase2 / coverage-engine-foundation`.)

## DoD bullets believed closed

**None.** The four Phase 2 DoD bullets in `design/implementation-plan/delivery-phasing.md` are:

- `novetest test --coverage` against `pytest-coverage` emits per-test coverage — needs Run Team's adapter slice AND Orchestration's `--coverage` flag wiring.
- `novetest coverage diff` returns structured deltas — needs Orchestration's `coverage diff` CLI verb.
- `inspect` returns the Coverage section populated — needs Orchestration's `inspect` integration.
- NFR-COV-002 (50k covered locations) — pending the perf harness; this slice did not run it.

This slice produces the *engine library* the next three DoD bullets sit on top of. The fourth (NFR-COV-002) is a performance verification owed once a realistic fixture exists; recruit `performance-engineer` then.

## Proposed `coverage_facts.json` layout (for PM review → `decisions/`)

The persisted shape — what `CoverageFactSet.to_dict()` produces — is yours-truly's first cut. Field names below are load-bearing if PM promotes this; downstream Regression / Localization / Orchestration will rely on them.

```jsonc
{
  "schema_version": 1,
  "run_reference": {
    "schema_version": 1,
    "run_id": "01HCOV...",
    "created_at": 1700000000000
  },
  "engine_name": "pytest",
  "ecosystem": "python",
  "mapping_granularity": "per-test",    // enum: per-test | per-test-class | per-test-file | aggregate
  "summary": {
    "num_statements": 100,
    "covered_statements": 80,
    "missing_statements": 20,
    "excluded_statements": 0,
    "num_branches": 30,
    "covered_branches": 25,
    "missing_branches": 5,
    "percent_covered": 80.0
  },
  "files": [
    {
      "file_path": "src/pkg/calc.py",
      "executed_lines": [1, 2, 3, 5, 6, 8],
      "missing_lines": [10, 11],
      "excluded_lines": [],
      "executed_branches": [[3, 5], [5, 6]],   // pairs of [from_line, to_line]
      "missing_branches": [[3, 10]],
      "summary": { /* same shape as top-level summary */ },
      "line_contexts": {                       // line# → sorted nodeids; empty when granularity != per-test
        "2": ["tests/test_calc.py::test_add"],
        "3": ["tests/test_calc.py::test_add", "tests/test_calc.py::test_sub"]
      }
    }
  ],
  "derived_at": 1700000001000,
  "metadata": {
    "coverage_py_version": "7.6.0",
    "show_contexts": true,
    "branch_coverage": true
  }
}
```

Key decisions baked into this shape:

1. **`covered_statements` (not `covered_lines`) at the summary level.** coverage.py overloads the name `missing_lines` between "count" (integer in `summary`) and "line numbers" (list in file entry). Renaming the counts to `*_statements` removes that overload.
2. **`line_contexts: dict[str, list[str]]`** keys are stringified line numbers on the wire (JSON object keys must be strings) and stripped of coverage.py's `|<phase>` suffix at parse time. Empty-string contexts (module-import scope) are dropped.
3. **File-level `executed_branches` and `missing_branches`** are pairs `[from_line, to_line]` matching coverage.py's native shape. Localization (Phase 4) can use these directly as Code Locations.
4. **`mapping_granularity` is mandatory** and validated in `__post_init__` against the four-tier enum.
5. **`metadata` is open-ended** — engine-specific debug info goes here. It is *not* part of the wire contract for cross-tool consumers.

Compare-side shape (`CoverageDelta`) and `CoverageAvailability` shape are documented in the source dataclasses; they are operation-result types, not persisted, so PM may want to scope the `decisions/` entry to the persisted `coverage_facts.json` only.

## Open items / surprises

1. **coverage.py `show_contexts` is required for `mapping_granularity: per-test`.** Run Team's `pytest-coverage-emission` task already documents this (`.coveragerc` with `[json] show_contexts = True`), so the contract is consistent across both slices. Without it, the parser falls back to `mapping_granularity: aggregate` cleanly.
2. **Coverage.py contexts carry phase suffixes.** Same nodeid appears as `"...|setup"`, `"...|run"`, `"...|teardown"` for any line the test touches. We collapse to one nodeid per line. If Localization (Phase 4) ever wants phase-resolution attribution, the parser's `_clean_context_nodeids` is the seam.
3. **Empty `""` context is dropped.** It represents non-test execution (module imports, generator initialization). There's no test to attribute it to, and including it would pollute the test-to-code map. If a future workflow genuinely needs "lines executed at import time," it would have to come back through a separate path.
4. **`compare_coverage_facts` does NOT short-circuit on granularity mismatch.** A `per-test` baseline vs `aggregate` target still produces a useful per-Code-Location delta (lines/branches resolve regardless of test attribution). Both sides' granularity are carried on the result so callers decide. If PM wants strict same-granularity comparison, the policy lives in Orchestration's stage-eligibility, not here.
5. **`check_coverage_availability` reports four fields** (`available` / `facts_persisted` / `native_payload_present` / `run_exists` + `reason`). Memory's `has_coverage_facts` corresponds exactly to `facts_persisted`, validated by `test_availability_agrees_with_memorys_has_coverage_facts_flag`. The richer signal (separate `native_payload_present`) is for Orchestration's eligibility evaluator to decide whether to call `derive_coverage_facts` to populate facts on demand.
6. **Integration test deferred.** End-to-end exercise of `has_coverage_facts` auto-flipping needs the Run Team's `pytest-coverage-emission` slice to land first (so a coverage-enabled `novetest run` produces a real coverage.json on disk). Task explicitly allows this deferral — see Verification commands in the original task. The unit-level proof that derive writes the load-bearing path is in `test_derive_persists_facts_at_load_bearing_path`.
7. **No pyproject.toml changes** from this slice. Run Team's parallel slice adds `pytest-cov` / `coverage[toml]>=7.0` to dev deps; Coverage does not depend on them at runtime (we parse the JSON the adapter already wrote).
8. **No private Memory imports.** Confirmed by inspection — `store.py`'s public surface (`retrieve_run_evidence`, `RunEvidenceNotFoundError`, `get_memory_entry_availability`) is sufficient. The path constant for the load-bearing file is duplicated intentionally in `coverage/persistence.py` so the two surfaces stay independently verifiable (a test asserts the two paths match).
