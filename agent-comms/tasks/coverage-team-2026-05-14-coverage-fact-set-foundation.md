---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-05-14
slug: coverage-fact-set-foundation
related: [run-team-2026-05-14-pytest-coverage-emission.md]
---

# Task: Coverage engine foundation — CoverageFactSet model + derive/get/compare/check

## Scope / Mission

Phase 2 (Coverage Structuring) entry. Build the Coverage engine's foundation:
the persisted `CoverageFactSet` model and the four internal interfaces from
`design/interace-contract/coverage.md` — `derive_coverage_facts`,
`get_coverage_facts`, `compare_coverage_facts`, `check_coverage_availability`.
You consume the native coverage payload that Run Team's parallel slice produces
(`run-team-2026-05-14-pytest-coverage-emission`); the input shape is pinned
below so you can build and unit-test **in parallel** with Run.

The external `novetest coverage show|diff` CLI verbs are Orchestration's later
slice — do not wire CLI here. Produce facts only; never decide whether a gap is
acceptable.

## Pre-flight reading

1. `CLAUDE.md` + your charter (`.claude/agents/novetest-coverage-team.md`)
2. `design/interace-contract/coverage.md` — the four interfaces in scope
3. `design/workflows/coverage.md` — workflow sequences (note: `derive`/`get`
   read evidence via `memory/retrieve_run_evidence`; `compare` calls
   `get_coverage_facts` on both sides)
4. `design/implementation-plan/engine-adapters.md` §"Cross-Cutting: Per-Test
   Coverage Attribution" — the `mapping_granularity` tiers — and §1 coverage.py
   JSON shape
5. `design/implementation-plan/delivery-phasing.md` Phase 2
6. `src/novetest/memory/store.py` — `retrieve_run_evidence` and
   `_availability_flags` (the canonical coverage-facts path/filename — see Data
   contracts; the live code is the source of truth)
7. `src/novetest/models/run_record.py` and `memory_entry.py` — `artifact_paths`
   is `dict[str, str]`, name → Project-Store-relative path

## Files to write / modify

- `src/novetest/models/coverage_fact_set.py` — the persisted `CoverageFactSet` entity
- `src/novetest/coverage/` — `derive_coverage_facts`, `get_coverage_facts`,
  `compare_coverage_facts`, `check_coverage_availability` + `__init__.py` re-exports
- `tests/unit/coverage/**` — mirror the `src/novetest/coverage/` tree
- `tests/unit/models/test_coverage_fact_set.py`

## Files NOT to touch

- `src/novetest/run/**`, `memory/**`, `cli/**`, `orchestration/**`,
  `regression/**`, `localization/**`, `replay/**`
- `src/novetest/models/run_record.py`, `run_reference.py`, `test_result.py`,
  `memory_entry.py` — Memory Team territory
- `tests/fixtures/projects/pytest-coverage/` — **Run Team owns and creates this
  fixture in their parallel slice.** Do not create it yourself. For your unit
  tests, check in a small static sample coverage.py JSON payload under
  `tests/unit/coverage/` as a parser fixture instead.
- `design/implementation-plan/*` — PM / Run Team

## Data contracts (pinned verbatim)

**Input — native coverage payload from Run Team.** A run produced with coverage
enabled has these keys in `RunRecord.artifact_paths` (store-relative strings):
- `"coverage_json"` -> `run/artifacts/run_<ulid>/native/coverage.json` (coverage.py JSON)
- `"coverage_xml"` -> `run/artifacts/run_<ulid>/native/coverage.xml` (Cobertura, interop only — your parser uses the JSON)

The `coverage.json` is the coverage.py 7.x JSON report with **per-line
`contexts`** enabled (`show_contexts`). Relevant shape per file entry:
`executed_lines`, `missing_lines`, `excluded_lines`, `summary` (with
`num_statements`, `covered_lines`, `missing_lines`, `num_branches`,
`covered_branches`, `missing_branches`, `percent_covered`), and `contexts` — a
map of `"<line>"` -> list of test nodeid context strings that executed that line.
Resolve `coverage_json` against the Project Store root, exactly as Memory
resolves any `artifact_paths` entry.

**Output — persisted facts path/filename (LOAD-BEARING).** Write to
`<store>/coverage/facts/run_<ulid>/coverage_facts.json`. The filename is
**`coverage_facts.json`** — this is what Memory's `_availability_flags` probes to
auto-flip `MemoryEntry.has_coverage_facts`. Do not invent a different name.
(Note: `delivery-phasing.md` Phase 2 currently says `coverage_fact_set.json`;
that doc wording is being corrected by PM — the live `_availability_flags` code
and your charter both say `coverage_facts.json`, so use `coverage_facts.json`.)

**`mapping_granularity`** field is mandatory on every `CoverageFactSet`, values
`per-test` | `per-test-class` | `per-test-file` | `aggregate`. For the pytest
path with `contexts` present, it is `per-test`.

**Model conventions:** `@dataclass(slots=True, frozen=True)`,
`CURRENT_SCHEMA_VERSION: ClassVar[int]` = 1, `to_dict()` / `from_dict(cls, d) -> Self`,
`_require_keys` helper — mirror `src/novetest/models/run_record.py` exactly.
Every Coverage Fact / delta entry preserves traceability to its originating Run
Reference and Code Location (NFR-COV-001).

## Design freedom + a deliverable for PM

The full `CoverageFactSet` field layout (how you model per-file line/branch
coverage, the test-to-code mapping, uncovered Code Locations, and the
`compare_coverage_facts` delta entity) is **yours to design** — it is not frozen
yet. In your handoff, include the proposed `coverage_facts.json` JSON layout
(top-level keys + nested shapes) as a clearly-marked section. PM will review it
with the CEO and promote it to `agent-comms/decisions/` so downstream teams
(Regression, Localization, Orchestration) can treat the field names as a
contract. Until then, treat it as stable-within-this-slice.

`check_coverage_availability` is pure filesystem/record probing (workflow doc:
no further interface call) — it must agree with Memory's `has_coverage_facts`
flag without importing Memory's private helpers.

`derive` must treat missing/absent native coverage inputs as an **explicit
unavailable outcome** (REQ-COV-004), not an exception.

## Verification commands (must pass before handoff)

- `uv run pytest -q tests/unit` (your new unit tests + model test)
- `uv run mypy` (must stay `--strict` clean)
- The end-to-end integration test that exercises `has_coverage_facts`
  auto-flipping needs Run Team's `pytest-coverage` fixture + coverage-enabled
  run path. If that has not merged yet, defer the integration test under
  `tests/integration/orchestration/` to a follow-up and say so in your handoff —
  unit coverage against the checked-in sample payload is sufficient for this
  slice.

## Reporting

Write `agent-comms/handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md`
with the standard sections. Include the **proposed `coverage_facts.json` layout**
section described above. In **"DoD bullets believed closed"**: assess honestly —
the Phase 2 DoD bullets (`novetest test --coverage`, `novetest coverage diff`,
`inspect` populated) all also need Orchestration's CLI wiring, so this slice
likely closes none of them outright. List any coverage.py JSON quirks (esp.
`contexts` / `show_contexts` behavior) under "Open items / surprises".
