---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-16
slug: coverage-cli-wiring
---

# Task: Wire `--coverage` through `novetest run` end-to-end

## Scope / Mission

Add the `--coverage` boolean flag to the `novetest run` CLI command and
thread it through `orchestration/workflows/run.run_target_in_store` →
`run/engine.execute` → `run_pytest(collect_coverage=True)`. After a
successful coverage-enabled run, call
`coverage.derive_coverage_facts(store, run_reference)` so the resulting
`coverage_facts.json` lands on disk at the contract-frozen path
(`<store>/coverage/facts/run_<id>/coverage_facts.json`) and Memory's
`has_coverage_facts` flag automatically flips to True on subsequent
reads.

This slice closes **Phase 2 DoD #1** (per-test coverage emission with
`mapping_granularity: per-test` against the `pytest-coverage` fixture).
It does NOT close DoD #2 (`coverage diff` verb), #3 (`inspect` Coverage
section), or #4 (NFR-COV-002 50k-location perf) — those are separate
follow-up slices.

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
   binding `coverage_facts.json` v1 layout (you do NOT touch this file
   itself; you trigger Coverage's derive function which writes it)
4. `agent-comms/tasks/orchestration-team-2026-05-16-coverage-cli-wiring.md`
   (this file)
5. `WORKLOG.md` top 3 entries — Run team's pytest-coverage-emission slice
   (`6ff91c5`) and Coverage team's foundation slice (`dee3252`) are the
   immediate upstream
6. `design/interace-contract/orchestration.md` — your authority on the CLI
   surface and envelope schema
7. `design/interace-contract/coverage.md` — read-only; tells you the
   `derive_coverage_facts` contract
8. `design/interace-contract/run.md` — read-only; tells you the
   `run/execute` contract you are extending
9. `design/workflows/orchestration.md` §1 (run-and-persist) and
   `design/workflows/coverage.md` (the derive sequence you are wiring)
10. `design/implementation-plan/delivery-phasing.md` Phase 2 DoD

## Pinned data contracts (do not improvise)

### `derive_coverage_facts` signature (Coverage engine, READ-ONLY)

```python
# src/novetest/coverage/derive.py
def derive_coverage_facts(
    store: ProjectStore,
    run_reference: RunReference,
) -> CoverageFactSet | CoverageUnavailable: ...
```

- Returns `CoverageFactSet` on success; `CoverageUnavailable` (with a
  `reason` field) when the native payload is missing/corrupt/etc.
- `CoverageUnavailable` is **not an exception**. It is a value. Check
  with `isinstance(result, CoverageUnavailable)`.
- Side effect: writes
  `<store>/coverage/facts/run_<id>/coverage_facts.json` on success.
- The artifact-key it reads is `record.artifact_paths["coverage_json"]`
  (constant `COVERAGE_JSON_ARTIFACT_KEY` in `coverage/derive.py`).

### `run_pytest` collect_coverage (Run engine, READ-ONLY)

```python
# src/novetest/run/adapters/pytest_adapter.py
async def run_pytest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult: ...
```

When `collect_coverage=True` and the run succeeds, `NativeResult.artifact_paths`
has the keys `pytest_json_report`, `stdout`, `stderr`, `coverage_json`,
`coverage_xml` — all absolute `Path`s. (The orchestration layer rewrites
these to Project-Store-relative strings before persisting, which it
already does in `run_target_in_store`.)

### `engine.execute` (Run engine, you MAY extend signature)

```python
# src/novetest/run/engine.py — CURRENT signature
async def execute(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    run_id: str | None = None,
    timeout: float | None = 600.0,
) -> RunRecord: ...
```

Run team's `execute` and `execute_with_engine_context` do not currently
accept `collect_coverage`. You need to plumb the kwarg through both.

**This is the one cross-team edit boundary.** `src/novetest/run/engine.py`
belongs to Run team's charter, not yours. Two options — pick one and
document the choice in your handoff:

- **Option A (recommended):** Make the minimal edit in `run/engine.py` to
  add `collect_coverage: bool = False` to both `execute` and
  `execute_with_engine_context`, default False (so all existing callers
  are byte-equivalent), pass-through to `run_pytest`. Treat this as a
  "narrow cross-charter touch in service of wiring," document it in the
  handoff, and PM will smooth it over with Run team. Add one Run-side
  unit test under `tests/unit/run/test_engine.py` asserting the kwarg
  threads through.
- **Option B (charter-strict):** Write a `questions/` file to PM asking
  Run team to land the signature extension first as a tiny prep slice.
  This serializes the work — the wiring task waits a cycle. Pick only
  if you are uncomfortable touching `run/engine.py`.

PM authorizes **Option A** for this task — Run's `run_pytest` already
exposes the kwarg, so threading it through two adjacent layers is a
mechanical extension of an established contract, not a new design
decision. Do the work; PM owns the charter coordination.

## Files to write / modify

- `src/novetest/cli/app.py` — add `coverage: bool = False` parameter (with
  Cyclopts CLI annotation `--coverage / -c`) to the `run_cmd` handler;
  pass it through to `run_target_in_store(..., collect_coverage=coverage)`.
- `src/novetest/orchestration/workflows/run.py` — add `collect_coverage:
  bool = False` to `run_target_in_store`; pass through to `execute`. On
  successful run (i.e. after `store_run_evidence`), if
  `collect_coverage=True`, call
  `derive_coverage_facts(store, persisted_record.run_reference)`.
  - Handle the `CoverageUnavailable` return value: log/include in the
    returned `RunOutcome` (extend the dataclass with an optional
    `coverage_outcome: CoverageFactSet | CoverageUnavailable | None`
    field, defaulting to None when coverage was not requested).
  - The CLI handler is responsible for formatting the coverage outcome
    into the envelope (see "Envelope shape" below).
- `src/novetest/run/engine.py` — Option A: add `collect_coverage` kwarg
  through `execute` and `execute_with_engine_context`. Defaults to
  False; pass-through to `run_pytest`.
- `tests/unit/run/test_engine.py` — add one assertion (or new test) that
  `execute(..., collect_coverage=True)` invokes `run_pytest` with the
  kwarg. Mock or stub `run_pytest` to verify; do not actually run
  pytest.
- `tests/unit/orchestration/workflows/test_run.py` (create if missing) —
  unit test for `run_target_in_store(..., collect_coverage=True)`:
  asserts `derive_coverage_facts` is called with the correct
  `RunReference`. Mock at the seam (`novetest.coverage.derive_coverage_facts`).
- `tests/unit/cli/test_run_cmd.py` (or wherever the existing run-cmd
  unit tests live; create if missing) — assert the `--coverage` flag
  parses and routes through.
- `tests/integration/orchestration/test_workflows.py` — add an
  integration test `test_run_with_coverage_against_pytest_coverage_fixture`
  that:
  1. Initializes a Project Store in a tmp_path-copy of
     `tests/fixtures/projects/pytest-coverage/`.
  2. Calls `await run_target_in_store("tests/", store, collect_coverage=True)`.
  3. Asserts `outcome.memory_entry.has_coverage_facts is True`.
  4. Asserts
     `(<store>/coverage/facts/run_<id>/coverage_facts.json).is_file()`.
  5. Loads the file via `get_coverage_facts`; asserts
     `fact_set.mapping_granularity == "per-test"`.
  6. Asserts the fixture's deliberately-uncovered line (line 16 in
     `pytest_coverage/classifier.py` — confirm by reading the fixture
     README) is in the per-file `missing_statements` list.
- `tests/integration/cli/test_cli_lifecycle.py` — add a subprocess
  scenario: `novetest run --coverage tests/` against the same fixture,
  assert exit code 0, JSON envelope `data.coverage_outcome` populated
  with `mapping_granularity: per-test`.

## Files NOT to touch

- `src/novetest/coverage/**` — Coverage team's territory. You consume
  `derive_coverage_facts` and the `CoverageFactSet` / `CoverageUnavailable`
  types; you do not edit them.
- `src/novetest/memory/**`, `src/novetest/models/**` — Memory team's
  territory. `MemoryEntry.has_coverage_facts` already auto-flips based
  on filesystem probe; you trigger the file creation by calling
  `derive_coverage_facts`, then re-read the entry to observe the True.
- `src/novetest/run/adapters/pytest_adapter.py` — Run team's territory.
  The `collect_coverage` kwarg is already there.
- `tests/fixtures/projects/pytest-coverage/**` — Run team's fixture. Use
  as-is via tmp_path copy.
- `agent-comms/decisions/**`, `history/**` — PM only.
- `pyproject.toml` — no new deps needed; `pytest-cov` and `coverage[toml]`
  already landed with the Run slice.

## Envelope shape (CLI handler)

The `novetest run --coverage` JSON envelope `data` field carries (extend
the existing shape, do not break it):

```json
{
  "memory_entry": { ... existing MemoryEntry to_dict ... },
  "coverage_outcome": {
    "kind": "fact-set",                    // or "unavailable"
    "run_reference": { ... },              // present in both kinds
    "mapping_granularity": "per-test",     // only when kind == "fact-set"
    "summary": { ... CoverageSummary ... } // only when kind == "fact-set"
    // OR
    "reason": "missing-native-payload",    // only when kind == "unavailable"
    "detail": "..."                        // only when kind == "unavailable"
  }
}
```

When `--coverage` was NOT passed, omit `coverage_outcome` entirely (do
not emit `null` — omit the key) so the Phase 1 envelope is byte-equivalent
for non-coverage runs.

## Verification commands

All must pass before writing the handoff. Run from the worktree root.

```sh
# Unit tests
uv run pytest -q tests/unit -k 'coverage or run_cmd or test_engine or workflows.test_run'

# Full unit + integration suite (baseline: 256 + new tests)
uv run pytest -q tests/unit tests/integration

# Strict mypy
uv run mypy

# Manual smoke (against your worktree)
cd /tmp && rm -rf pytest-coverage-smoke && cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-coverage pytest-coverage-smoke && cd pytest-coverage-smoke
uv run --with /home/yjshin/dev/Nove-Test novetest init
uv run --with /home/yjshin/dev/Nove-Test novetest run --coverage tests/
ls .novetest/coverage/facts/run_*/coverage_facts.json
cat .novetest/coverage/facts/run_*/coverage_facts.json | python3 -m json.tool | head -40
uv run --with /home/yjshin/dev/Nove-Test novetest memory show <run_id> --output json | python3 -m json.tool | grep has_coverage_facts
```

The manual smoke confirms:
1. `--coverage` flag is accepted at the CLI surface (no Cyclopts error).
2. `coverage_facts.json` lands at the contract-frozen path.
3. `has_coverage_facts: true` shows up on the next `memory show` (i.e.
   Memory's auto-flip works without any code changes to Memory).
4. `mapping_granularity: per-test` is present in the persisted facts.

## DoD bullets you should claim closed

In your handoff's "DoD bullets believed closed" list, name exactly:

- **Phase 2, bullet #1** — "`novetest test --coverage` against
  pytest-coverage emits per-test coverage with `mapping_granularity:
  per-test`."

  Caveat for PM: the DoD text mentions `novetest test --coverage`, but
  this slice only wires `novetest run --coverage`. The `test` verb
  remains a stub. PM will decide during cycle cleanup whether to (a) tick
  with a `delivery-phasing.md` text adjustment ("run --coverage" wording),
  or (b) leave unticked pending a follow-up slice that promotes
  `test` from stub to a real handler. Document your slice's actual scope
  honestly in the handoff and let PM judge.

Do NOT claim DoD #2, #3, or #4 — none of them close from this slice.

## Reporting (handoff)

Write `agent-comms/handoffs/orchestration-team-2026-05-16-coverage-cli-wiring.md`
with the standard handoff body sections:

- Worktree path + branch + base commit.
- Files written/modified (final list).
- pytest counts (new total) + mypy result.
- WORKLOG entry text (paste the entry you appended).
- DoD bullets believed closed (see above).
- Open items / surprises:
  - Note the Option A `run/engine.py` cross-charter touch with rationale.
  - Note that `novetest test --coverage` is still a stub.
  - Anything else worth flagging.

Append your WORKLOG entry per `WORKLOG.md`'s format. Run
`python3 tools/regen_comms_index.py` after writing the handoff. Stage
WORKLOG + handoff + INDEX alongside source per the post-flight protocol.

## Out of scope (do NOT do these in this task)

- Implement `novetest test` handler (still a stub after this slice). The
  follow-up slice that promotes `test` from stub to real handler is a
  separate task, sized to combine recommendation-synthesis placeholder
  + the `test` ↔ `run --coverage` wiring.
- Implement `novetest coverage show <run_id>` or `coverage diff <id1> <id2>`
  CLI verbs. Those are Phase 2 DoD #2's slice.
- Implement `novetest inspect` Coverage section. Phase 2 DoD #3's slice.
- 50k-location perf fixture. Phase 2 DoD #4's slice; needs a perf-fixture
  proposal first (PM will recruit `performance-engineer` for that scoping).
- Modify the `coverage_facts.json` schema. Frozen in
  `decisions/2026-05-15-coverage-facts-json-layout.md`.
- Touch `pyproject.toml`. No new deps needed.

## Why this task exists

Run team's `6ff91c5` and Coverage team's `dee3252` landed back-to-back but
deliberately left the wiring layer open — that's Orchestration territory.
Until `--coverage` is exposed on the CLI surface and the auto-derive hook
fires after a successful run, the engine library is shippable but the
user-facing feature ("`novetest run --coverage` actually works") is not.
This slice connects the two and is the natural first cut at Phase 2 DoD.
